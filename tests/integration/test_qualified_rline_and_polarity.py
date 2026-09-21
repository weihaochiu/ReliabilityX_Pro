"""OI-054 end-to-end qualification gates; all hardware is injected mock-only."""

import datetime as dt

import pytest

from core.IV_parameter_analysis_utils import calculate_iv_parameters
from tests.pipeline_support import build_offline_engine, make_channel
from tests.integration.test_hardware_safety_sequence import _assert_no_relay_action_while_energized


@pytest.mark.parametrize("failure", ["open149", "open0", "compliance", "reset", "switch", "mask", "cleanup", "off_cleanup", "config"])
def test_rline_failure_never_emits_success(tmp_path, monkeypatch, failure):
    """Invalid samples and every safety-stage failure suppress calibration output."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    smu._measurement = lambda voltage: (.01, .01)
    if failure.startswith("open"):
        smu._measurement = lambda voltage: (1.499 if failure == "open149" else 0, 5e-9)
    elif failure == "compliance":
        smu.voltage_compliance = True
    elif failure == "reset":
        relay.fail_reset = True
    elif failure == "switch":
        relay.fail_switch = True
    elif failure == "mask":
        relay.verify_state = lambda selected: False
    elif failure == "cleanup":
        original = relay.reset_all
        count = 0
        def reset():
            """Fail only after sampling succeeds."""
            nonlocal count
            count += 1
            return original() if count == 1 else False
        relay.reset_all = reset
    elif failure == "off_cleanup":
        original = smu.set_output_verified
        def output(enabled):
            """Simulate a safe OFF write with an unavailable acknowledgement."""
            was_on = smu.output_state
            original(enabled)
            if not enabled and was_on:
                raise IOError("OFF state readback lost")
        smu.set_output_verified = output
    elif failure == "config":
        def configure(**kwargs):
            """Inject strict setting failure before output ON."""
            raise IOError("current source setting mismatch")
        smu.configure_current_source_verified = configure
    results = []
    engine.line_resistance_result.connect(results.append)
    engine.request_line_resistance_measurement(1, 3, 57)
    assert results[-1]["ok"] is False
    assert results[-1]["error"]
    assert results[-1].get("resistance") is None
    assert smu.output_state is False
    assert engine.is_running is False
    assert not list(tmp_path.rglob("*.csv"))
    _assert_no_relay_action_while_energized(recorder.calls)


def test_valid_rline_success_only_after_cleanup(tmp_path, monkeypatch):
    """Return actual V/I only after verified output OFF and an empty relay mask."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    smu._measurement = lambda voltage: (.01, .01005)
    result = engine.measure_line_resistance(3, 57)
    assert result["resistance"] == pytest.approx(.01 / .01005)
    assert result["validation_version"] == 2
    assert smu.output_state is False and relay.relay_state == set()
    _assert_no_relay_action_while_energized(recorder.calls)


@pytest.mark.parametrize("voltage,current,trip", [(0, .02, False), (0, 5e-9, False),
                                                (0, -.02, True), (.1, -.02, False),
                                                (0, float("nan"), False)])
def test_polarity_failure_blocks_sweeps_and_next_channel(tmp_path, monkeypatch, voltage, current, trip):
    """Each formal attempt must pass polarity; failure writes no curve or summary."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    smu._measurement = lambda setpoint: (voltage, current)
    smu.current_compliance = trip
    points, completed = [], []
    engine.point_measured.connect(points.append)
    engine.channel_measurement_finished.connect(completed.append)
    engine.start_scan_cycle([make_channel(), make_channel(ch_id=2)])
    assert engine.last_channel_failure["status"] == "polarity_failure"
    assert engine.completed_channel_count == 0
    assert points == completed == []
    assert not list(tmp_path.rglob("*.csv"))
    assert smu.output_state is False and relay.relay_state == set()
    _assert_no_relay_action_while_energized(recorder.calls)


def test_formal_scan_compliance_after_polarity_is_failure(tmp_path, monkeypatch):
    """A normal precheck cannot authorize later current-limited IV points."""
    engine, smu, _, _ = build_offline_engine(tmp_path, monkeypatch)
    flags = iter([False, True])
    smu.read_current_compliance = lambda: next(flags)
    engine.start_scan_cycle([make_channel()])
    assert engine.last_channel_failure["status"] == "failed_read"
    assert engine.completed_channel_count == 0
    assert not list(tmp_path.rglob("*.csv"))


def test_measured_raw_voltage_used_in_analysis_and_logger(tmp_path, monkeypatch):
    """Setpoint differs deliberately; analysis and exported raw voltage use readback."""
    engine, _, _, _ = build_offline_engine(tmp_path, monkeypatch)
    points = [{"v_src": v * 2, "v_msd": v, "i_msd": -.02 + .02*v,
               "v_corr": v, "i_corr": -.02 + .02*v} for v in [0, .25, .5, .75, 1]]
    result = calculate_iv_parameters(points, list(reversed(points)), .5)
    assert result["Voc_F_Raw"] == pytest.approx(1)
    assert engine.iv_curve_logger._extract_point(points[1])[0] == pytest.approx(.25)


def test_polarity_runs_again_for_each_channel_and_is_saved(tmp_path, monkeypatch):
    """A prior successful check does not exempt the next scheduled device."""
    engine, smu, _, _ = build_offline_engine(tmp_path, monkeypatch)
    completed = []
    engine.channel_measurement_finished.connect(completed.append)
    engine.start_scan_cycle([make_channel(), make_channel(ch_id=2, device_name="second")])
    assert len(completed) == 2
    assert all(item["polarity_check"]["classification"] == "normal" for item in completed)
    assert sum(call["method"] == "read_vi" for call in smu.calls) == 22  # 2 * (precheck + 10 IV points)
    for path in tmp_path.rglob("*IV curve.csv"):
        text = path.read_text(encoding="utf-8-sig")
        assert "# Polarity_Check:" in text and "normal" in text
        assert "# Rline_Validation_Version:,2" in text
