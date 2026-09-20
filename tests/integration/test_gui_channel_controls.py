"""Offscreen GUI startup, persistence and real worker-boundary controls."""

import time

import pytest

import config
from tests.pipeline_support import build_offline_engine, make_channel


def wait_until(qapp, predicate, timeout=5):
    """Pump Qt events with a bounded timeout for asynchronous GUI operations."""
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert predicate(), "Timed out waiting for GUI/worker operation"


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    """Construct the full real main window with isolated config and mock hardware."""
    from gui.main_window import MainWindow
    from gui.log_window import LogWindow

    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "CHANNEL_SETTINGS_FILE", tmp_path / "channels.json")
    monkeypatch.setattr(config, "CALIBRATION_SETTINGS_FILE", tmp_path / "calibration.json")
    monkeypatch.setattr(config, "load_notification_settings", lambda: {"TELEGRAM": {"enabled": False}})
    engine.load_configs()
    assert config.save_json_file(config.CALIBRATION_SETTINGS_FILE, engine.cal_settings)
    assert config.save_json_file(config.CHANNEL_SETTINGS_FILE, {
        "1": make_channel(interval_min=1),
        "2": make_channel(ch_id=2, device_name="second", interval_min=1),
    })
    log_window = LogWindow()
    window = MainWindow(engine, log_window)
    window.show()
    qapp.processEvents()
    try:
        yield window
    finally:
        engine.queue_graceful_stop()
        # The worker must finish before QObject destruction, even after assertion failure.
        wait_until(qapp, lambda: not engine.is_running)
        window.chamber_poll_timer.stop()
        window.notification_manager.stop()
        window.channel_settings_save_controller._pool.waitForDone()
        window.thread.quit()
        assert window.thread.wait(5000)
        window._allow_close = True
        for child in (window.iv_monitor, window.trend_chart, log_window):
            child.close()
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.offline
def test_full_gui_worker_pause_resume_and_stop(main_window, monkeypatch, qapp):
    """Real QThread accepts individual toggles and global stop during its scan loop."""
    from PyQt6.QtWidgets import QMessageBox

    window = main_window
    engine = window.engine
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    # Real short waits prevent a CPU spin while the GUI thread writes settings.
    engine._interruptible_sleep = lambda seconds: time.sleep(min(seconds, .01))
    final = []
    engine.channel_measurement_finished.connect(final.append)
    window.on_start_clicked()
    wait_until(qapp, lambda: len(final) == 2)
    assert len(window.cards_by_ch_id) == 2
    assert "10.00%" in window.cards_by_ch_id[1].lbl_status.text()

    window.cards_by_ch_id[1].chk_enabled.setChecked(False)
    window.cards_by_ch_id[2].chk_enabled.setChecked(False)
    wait_until(qapp, lambda: "全部通道已暫停" in window.control_panel.lbl_scheduler_status.text())
    assert engine.is_running
    assert len(final) == 2

    window.cards_by_ch_id[1].chk_enabled.setChecked(True)
    wait_until(qapp, lambda: len(final) == 3)
    assert final[-1]["ch_id"] == 1
    assert window.cards_by_ch_id[2].is_checked() is False
    window.on_stop_clicked()
    wait_until(qapp, lambda: not engine.is_running)
    assert engine.last_finish_reason == "stopped_after_current_channel"
    assert engine.completed_channel_count == 3


@pytest.mark.offline
def test_failed_save_rolls_back_all_toggles_without_worker_request(main_window, monkeypatch, qapp):
    """A coalesced multi-card write failure cannot apply an unpersisted start/pause."""
    from PyQt6.QtWidgets import QMessageBox

    window = main_window
    requests = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    monkeypatch.setattr(config, "save_json_file", lambda *args: False)
    monkeypatch.setattr(window.engine, "queue_channel_enabled", lambda *args: requests.append(args))
    window.cards_by_ch_id[1].chk_enabled.setChecked(False)
    window.cards_by_ch_id[2].chk_enabled.setChecked(False)
    wait_until(qapp, lambda: window._pending_channel_settings is None)
    assert all(card.is_checked() for card in window.cards)
    assert requests == []


@pytest.mark.offline
def test_earlier_success_latest_failure_keeps_saved_runtime_state(main_window, monkeypatch):
    """In-flight edits honor successful writes, ignore stale failures and deduplicate commands."""
    from PyQt6.QtWidgets import QMessageBox

    window = main_window
    calls = []
    monkeypatch.setattr(window.engine, "queue_channel_enabled", lambda channel, enabled: calls.append((channel["ch_id"], enabled)))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    first, second = make_channel(), make_channel(ch_id=2)
    window._channel_settings_save_token = 3
    window._channel_settings_rollback = {1: True, 2: True}
    window._channel_save_batches = {
        1: {1: (first, False)},
        2: {1: (first, False), 2: (second, False)},
        3: {1: (first, True), 2: (second, False)},
    }
    window._on_channel_settings_save_succeeded(str(config.CHANNEL_SETTINGS_FILE), 1)
    window._on_channel_settings_save_succeeded(str(config.CHANNEL_SETTINGS_FILE), 2)
    assert calls == [(1, False), (2, False)]
    assert config.save_json_file(config.CHANNEL_SETTINGS_FILE, {
        "1": dict(first, is_enabled=False), "2": dict(second, is_enabled=False),
    })
    window._on_channel_settings_save_failed(str(config.CHANNEL_SETTINGS_FILE), "latest write failed", 3)
    assert not any(card.is_checked() for card in window.cards)
    assert calls == [(1, False), (2, False)]
