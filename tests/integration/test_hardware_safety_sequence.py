"""Cold-switching and exception-cleanup safety regressions."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

import core.measure_engine as measure_engine_module
from driver.smu_driver import HardwareReadError
from tests.mocks.mock_relay import MockRelay
from tests.mocks.mock_smu import CallRecorder, MockSMU
from tests.pipeline_support import build_offline_engine, make_channel


def _assert_no_relay_action_while_energized(calls: list[dict]) -> None:
    """Assert the shared call log never switches relays under SMU output."""
    energized = False
    for call in calls:
        if call["device"] == "smu" and call["method"] == "output_control":
            energized = call["args"][0] == "ON"
        if call["device"] == "relay" and call["method"] in {"reset_all", "switch_on", "switch_off"}:
            assert energized is False, f"Relay action while energized: {call}"


@pytest.mark.offline
def test_cold_switch_start_and_cleanup_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Require relay switching only while SMU is off and cleanup OFF then reset."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    engine.start_scan_cycle([make_channel()])
    _assert_no_relay_action_while_energized(recorder.calls)
    assert smu.output_state is False
    assert relay.relay_state == set()
    last_off = max(
        call["sequence"]
        for call in recorder.calls
        if call["device"] == "smu" and call["method"] == "output_control" and call["args"] == ("OFF",)
    )
    last_reset = max(
        call["sequence"]
        for call in recorder.calls
        if call["device"] == "relay" and call["method"] == "reset_all"
    )
    assert last_off < last_reset


@pytest.mark.offline
@pytest.mark.parametrize(
    "failure_mode",
    [
        "smu_timeout",
        "smu_read_exception",
        "smu_compliance",
        "relay_failure",
        "analysis_exception",
        "logger_exception",
        "user_stop",
    ],
)
def test_exception_paths_always_cleanup_smu_and_relay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_mode: str
) -> None:
    """All requested failure classes converge on the production safe cleanup."""
    recorder = CallRecorder()
    smu = MockSMU(recorder)
    relay = MockRelay(recorder)
    engine, smu, relay, recorder = build_offline_engine(
        tmp_path, monkeypatch, smu=smu, relay=relay, recorder=recorder
    )
    engine.load_configs()
    engine.is_running = True

    if failure_mode == "smu_timeout":
        smu.read_exception = HardwareReadError("mock timeout")
    elif failure_mode == "smu_read_exception":
        smu.read_exception = HardwareReadError("mock malformed response")
    elif failure_mode == "smu_compliance":
        smu.read_exception = RuntimeError("mock compliance limit")
    elif failure_mode == "relay_failure":
        relay.fail_switch = True
    elif failure_mode == "analysis_exception":
        monkeypatch.setattr(measure_engine_module, "calculate_iv_parameters", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("mock analysis failure")))
    elif failure_mode == "logger_exception":
        monkeypatch.setattr(engine.iv_curve_logger, "save_iv_curve", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("mock logger failure")))
    elif failure_mode == "user_stop":
        engine.stop_requested = True

    engine.measure_single_channel(make_channel(), dt.datetime.now())
    assert smu.output_state is False
    assert relay.relay_state == set()
    _assert_no_relay_action_while_energized(recorder.calls)


@pytest.mark.offline
def test_emergency_shutdown_forces_off_then_relay_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Emergency shutdown uses the documented SMU-OFF then relay-reset order."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    smu.output_state = True
    relay.relay_state = {1, 2}
    engine.is_running = True
    engine.emergency_shutdown()
    assert smu.output_state is False
    assert relay.relay_state == set()
    actions = [(call["device"], call["method"], call["args"]) for call in recorder.calls]
    off_index = actions.index(("smu", "output_control", ("OFF",)))
    reset_index = next(index for index, action in enumerate(actions) if action[:2] == ("relay", "reset_all"))
    assert off_index < reset_index
