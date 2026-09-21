"""OI-050 failures must remain failures through the production scheduler."""

import datetime as dt

import pytest

import config
import core.measure_engine as engine_module
from driver.smu_driver import HardwareReadError
from tests.pipeline_support import build_offline_engine, make_channel


@pytest.mark.offline
@pytest.mark.parametrize("failure, expected", [
    ("read", "polarity_failure"), ("relay", "relay_failure"),
    ("analysis", "failed_analysis"), ("invalid_analysis", "failed_analysis"), ("curve", "failed_logger"),
    ("summary", "failed_logger"), ("mapping", "blocked_config"),
    ("calibration", "blocked_calibration"), ("expired", "blocked_calibration"),
    ("cleanup", "cleanup_failure"),
])
def test_failed_attempt_stops_queue_without_success(tmp_path, monkeypatch, failure, expected):
    """Inject faults and check finish signals, persistence, cleanup and next channel."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    channel = make_channel()
    finished, scans, statuses = [], [], []
    engine.channel_measurement_finished.connect(finished.append)
    engine.scan_finished.connect(scans.append)
    engine.channel_status_updated.connect(statuses.append)

    def fail(*args, **kwargs):
        """Inject an exception at the selected production stage."""
        raise OSError("injected stage failure")

    if failure == "read":
        smu.read_exception = HardwareReadError("injected timeout")
    elif failure == "relay":
        relay.fail_switch = True
    elif failure == "analysis":
        monkeypatch.setattr(engine_module, "calculate_iv_parameters", fail)
    elif failure == "invalid_analysis":
        monkeypatch.setattr(engine_module, "calculate_iv_parameters", lambda *args: {"valid_F_Raw": False})
    elif failure == "curve":
        monkeypatch.setattr(engine.iv_curve_logger, "save_iv_curve", fail)
    elif failure == "summary":
        monkeypatch.setattr(engine.summary_logger, "update_summary_report", fail)
    elif failure == "mapping":
        channel["relay_pos"] = None
    elif failure in {"calibration", "expired"}:
        original_load = engine.load_configs

        def load():
            """Set missing or stale R-line after normal mock configuration load."""
            original_load()
            if failure == "calibration":
                engine.cal_settings["line_resistance_map"] = {}
            else:
                engine.cal_settings["line_resistance_map"]["1_2"]["time"] = "2000-01-01 00:00:00"
            return True

        engine.load_configs = load
    elif failure == "cleanup":
        monkeypatch.setattr(engine, "_cleanup_channel_path", fail)

    state_path = tmp_path / "state.json"
    monkeypatch.setattr(config, "RUNTIME_SCHEDULE_STATE_FILE", state_path)
    engine._save_schedule_state = engine_module.MeasureEngine._save_schedule_state.__get__(engine)
    engine.start_scan_cycle([channel, make_channel(ch_id=2, device_name="second")])

    assert engine.last_finish_reason == "failed"
    assert engine.completed_channel_count == 0
    assert engine.failed_channel_count == 1
    assert scans[-1]["last_channel_failure"]["status"] == expected
    assert scans[-1]["remaining_channel_count"] == 2
    assert finished == []
    state = config.load_json_file(state_path)
    assert state["status"] == "failed"
    assert state["last_channel_failure"]["status"] == expected
    assert state["items"][0]["active"] is True  # one-shot failure was not consumed
    assert state["items"][1]["last_actual_start_time"] == ""
    assert smu.output_state is False
    assert relay.relay_state == set()
    assert not any(s["message"] == "已完成" for s in statuses)


@pytest.mark.offline
def test_partial_success_is_not_all_success(tmp_path, monkeypatch):
    """A later failing channel preserves earlier success and truthful totals."""
    engine, smu, _, _ = build_offline_engine(tmp_path, monkeypatch)
    engine.channel_measurement_finished.connect(
        lambda result: setattr(smu, "read_exception", HardwareReadError("second channel fault"))
    )
    engine.start_scan_cycle([make_channel(), make_channel(ch_id=2, device_name="second")])
    assert engine.completed_channel_count == 1
    assert engine.failed_channel_count == 1
    assert engine.last_finished_channel_id == 1
    assert engine.last_channel_failure["ch_id"] == 2
    assert engine.last_finish_reason == "failed"


@pytest.mark.offline
def test_immediate_abort_propagates_after_cleanup(tmp_path, monkeypatch):
    """Immediate abort remains distinct from a failed or successful attempt."""
    engine, smu, relay, _ = build_offline_engine(tmp_path, monkeypatch)
    smu.read_exception = engine_module.MeasurementInterrupted("test abort")
    engine.start_scan_cycle([make_channel()])
    assert engine.last_finish_reason == "interrupted_immediate"
    assert engine.completed_channel_count == 0
    assert smu.output_state is False
    assert relay.relay_state == set()


@pytest.mark.offline
@pytest.mark.parametrize("overrides", [
    {"v_step": 0}, {"v_step": -1}, {"v_stop": -1}, {"area": 0},
    {"v_start": float("nan")}, {"i_limit": 999}, {"v_stop": 999},
    {"relay_neg": 1}, {"relay_pos": 999}, {"interval_min": -1},
])
def test_invalid_channel_never_energizes_or_selects_path(tmp_path, monkeypatch, overrides):
    """Runtime-joined channels receive the same preflight as initial channels."""
    engine, _, _, recorder = build_offline_engine(tmp_path, monkeypatch)
    engine.start_scan_cycle([make_channel(**overrides)])
    assert engine.last_channel_failure["status"] == "blocked_config"
    assert engine.completed_channel_count == 0
    assert not any(call["method"] == "switch_on" for call in recorder.calls)
    assert not any(call["method"] == "output_control" and call["args"] == ("ON",) for call in recorder.calls)
