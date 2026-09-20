"""Offline multi-channel cadence and live pause/resume acceptance tests."""

import datetime as dt
from types import SimpleNamespace

import pytest

import core.measure_engine as engine_module
import core.measurement_scheduler as scheduler_module
from tests.pipeline_support import build_offline_engine, make_channel
from tests.integration.test_hardware_safety_sequence import _assert_no_relay_action_while_energized


def channels():
    """Return independent logical devices and relay pairs."""
    return [make_channel(ch_id=i, channel_label=f"CH{i:02d}", device_name=f"device{i}",
                         experiment_uid=f"EXP{i}", relay_pos=i * 2 - 1, relay_neg=i * 2)
            for i in range(1, 5)]


def install_calibrations(engine):
    """Provide traceable calibration for every mock relay pair."""
    original = engine.load_configs

    def load():
        """Load complete mock calibrations without disk/hardware IO."""
        original()
        engine.cal_settings["line_resistance_map"] = {
            f"{i * 2 - 1}_{i * 2}": {"value": 0.0, "time": dt.datetime.now().isoformat()}
            for i in range(1, 5)
        }
        return True

    engine.load_configs = load


@pytest.mark.offline
def test_four_channel_one_shot_data_and_paths(tmp_path, monkeypatch):
    """All devices receive separate files and only their own relay pair."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    install_calibrations(engine)
    final = []
    engine.channel_measurement_finished.connect(final.append)
    engine.start_scan_cycle(channels())
    assert [result["ch_id"] for result in final] == [1, 2, 3, 4]
    assert engine.completed_channel_count == 4
    assert engine.failed_channel_count == 0
    assert len(list(tmp_path.rglob("*IV curve.csv"))) == 4
    assert len(list(tmp_path.rglob("Summary_report.csv"))) == 4
    assert [c["args"][0] for c in recorder.calls if c["method"] == "switch_on"] == list(range(1, 9))
    _assert_no_relay_action_while_energized(recorder.calls)
    assert smu.output_state is False and relay.relay_state == set()


@pytest.mark.offline
def test_pause_current_and_waiting_channels_then_resume_and_join(tmp_path, monkeypatch):
    """Toggles cannot interrupt a scan; paused queued channels do not run."""
    engine, _, _, recorder = build_offline_engine(tmp_path, monkeypatch)
    install_calibrations(engine)
    data = channels()
    final, points = [], []

    def on_point(point):
        """Queue pause during the first channel's active forward scan."""
        points.append(point)
        if len(points) == 1:
            assert engine.queue_channel_enabled(data[0], False)
            assert engine.queue_channel_enabled(data[1], False)

    def on_finish(result):
        """Resume a waiting channel and add one excluded at global startup."""
        final.append(result["ch_id"])
        if result["ch_id"] == 3:
            engine.queue_channel_enabled(data[1], True)
            engine.queue_channel_enabled(data[3], True)
        if result["ch_id"] == 4:
            engine.queue_graceful_stop()

    engine.point_measured.connect(on_point)
    engine.channel_measurement_finished.connect(on_finish)
    engine.start_scan_cycle(data[:3])
    assert final == [1, 3, 2, 4]
    assert len([p for p in points if p["ch_id"] == 1]) == 10
    assert engine.last_finish_reason == "stopped_after_current_channel"
    _assert_no_relay_action_while_energized(recorder.calls)


@pytest.mark.offline
def test_all_paused_remains_available_for_individual_resume(tmp_path, monkeypatch):
    """An all-paused scheduler waits without ending or spinning through scans."""
    engine, _, _, _ = build_offline_engine(tmp_path, monkeypatch)
    channel = make_channel(interval_min=1)
    finished, waits = [], []

    def on_finish(result):
        """Pause after first scan, stop gracefully after the resumed scan."""
        finished.append(result)
        if len(finished) == 1:
            engine.queue_channel_enabled(channel, False)
        else:
            engine.queue_graceful_stop()

    def sleep(seconds):
        """Resume after observing the all-paused wait, without real delay."""
        if seconds == 0.2 and len(finished) == 1:
            waits.append(seconds)
            engine.queue_channel_enabled(channel, True)

    engine._interruptible_sleep = sleep
    engine.channel_measurement_finished.connect(on_finish)
    engine.start_scan_cycle([channel])
    assert len(finished) == 2 and len(waits) == 1
    assert engine.last_finish_reason == "stopped_after_current_channel"


@pytest.mark.offline
def test_independent_intervals_repeat_without_real_wait(tmp_path, monkeypatch):
    """Advance a virtual clock to prove per-channel cadence through multiple rounds."""
    engine, _, _, recorder = build_offline_engine(tmp_path, monkeypatch)
    install_calibrations(engine)
    real_datetime = dt.datetime

    class Clock(real_datetime):
        """Deterministic wall clock used only by production scheduler/engine."""
        current = real_datetime.now()

        @classmethod
        def now(cls, tz=None):
            """Return virtual time."""
            return cls.current

    clock_module = SimpleNamespace(datetime=Clock, timedelta=dt.timedelta)
    monkeypatch.setattr(engine_module, "datetime", clock_module)
    monkeypatch.setattr(scheduler_module, "_dt", clock_module)
    ticks = []

    def sleep(seconds):
        """Advance clock and impose a bound against accidental infinite loops."""
        ticks.append(seconds)
        assert len(ticks) < 200
        Clock.current += dt.timedelta(seconds=seconds)

    engine._interruptible_sleep = sleep
    data = channels()[:2]
    data[0]["interval_min"], data[1]["interval_min"] = 0.1, 0.2
    final = []

    def on_finish(result):
        """Stop once both channels have demonstrated repeated scheduling."""
        final.append(result)
        if len(final) == 5:
            engine.queue_graceful_stop()

    engine.channel_measurement_finished.connect(on_finish)
    engine.start_scan_cycle(data)
    for ch_id, count, interval in ((1, 3, 6), (2, 2, 12)):
        due = [r["scheduled_time"] for r in final if r["ch_id"] == ch_id]
        assert len(due) == count
        assert all((b - a).total_seconds() == interval for a, b in zip(due, due[1:]))
    assert len({r["run_session_id"] for r in final}) == 1
    _assert_no_relay_action_while_energized(recorder.calls)
