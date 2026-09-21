"""OI-057 reports must distinguish physical evidence, transport and unknown safety."""

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox, QAbstractButton

from core.diagnostic_messages import build_diagnostic_report
from driver.smu_driver import HardwareCommunicationError
from gui.diagnostic_dialog import create_diagnostic_dialog
from gui.channel_setting_dialog import ChannelSettingDialog
from gui.config_tabs.chamber_tab import ChamberTab
from gui.config_tabs.relay_tab import RelayTab


def test_cleanup_unknown_is_never_displayed_as_safe():
    """A primary timeout must still expose failed safety cleanup."""
    report = build_diagnostic_report(HardwareCommunicationError("timeout", code="smu_timeout"),
        stage="smu_setup", facts={"cleanup_attempted": True, "smu_off_confirmed": False,
                                  "relay_off_confirmed": True, "output_attempted": False})
    assert report["summary"].startswith("安全提醒")
    assert "SMU OFF：未確認" in report["summary"]
    assert "Relay 全關：已確認" in report["summary"]


def test_dialog_plain_language_details_and_copy(qapp):
    """The actual Qt renderer preserves full evidence behind expandable details."""
    report = build_diagnostic_report(HardwareCommunicationError("VI_ERROR_TMO", command=":SOUR:CURR?", code="smu_timeout"), stage="smu_setup")
    dialog = create_diagnostic_dialog(None, report)
    assert "SMU" in dialog.text()
    assert "建議處理" in dialog.informativeText()
    assert ":SOUR:CURR?" in dialog.detailedText()
    details = next(button for button in dialog.findChildren(QAbstractButton) if button.text() == "顯示技術詳細資料")
    details.click()
    assert details.text() == "收合技術詳細資料"
    details.click()
    assert details.text() == "顯示技術詳細資料"
    button = next(button for button in dialog.buttons() if button.text() == "複製診斷資料")
    button.click()
    assert "VI_ERROR_TMO" in QApplication.clipboard().text()
    assert "建議處理" in QApplication.clipboard().text()
    dialog.deleteLater()


def test_progress_ignores_other_or_finished_requests():
    """A stale queued event cannot overwrite the current GUI request."""
    text = []
    dialog = SimpleNamespace(_pending_rline_request_id=2,
        action_widget=SimpleNamespace(btn_measure_rline=SimpleNamespace(setText=text.append)))
    ChannelSettingDialog._on_diagnostic_progress(dialog, {"request_id": 1, "message": "wrong"})
    ChannelSettingDialog._on_diagnostic_progress(dialog, {"request_id": 2, "message": "設定確認"})
    dialog._pending_rline_request_id = None
    ChannelSettingDialog._on_diagnostic_progress(dialog, {"request_id": None, "message": "stale"})
    assert text == ["設定確認…"]


@pytest.mark.parametrize("serial_ok", [False, True, "exception"])
def test_chamber_failure_explanation_matches_actual_open_state(qapp, monkeypatch, serial_ok):
    """A failed port open must not tell operators that COM was opened."""
    reports = []
    driver = SimpleNamespace(disconnect=lambda: None, connect=lambda *a, **k: serial_ok,
                             test_telemetry=lambda **k: (False, None, "TX @0801 RX none"),
                             last_error="Port unavailable")
    if serial_ok == "exception":
        def fail(*args, **kwargs):
            """Inject a serial-open exception before serial_ok can be assigned."""
            raise OSError("Port busy")
        driver.connect = fail
    dialog = SimpleNamespace(engine=SimpleNamespace(chamber_driver=driver),
        _get_selected_port=lambda: "COM1", chamber_id_spin=SimpleNamespace(value=lambda: 8),
        chamber_baud_combo=SimpleNamespace(currentText=lambda: "9600"),
        manual_log_output=SimpleNamespace(append=lambda text: None),
        _show_error_status=lambda: None, chamber_update_timer=SimpleNamespace(stop=lambda: None))
    monkeypatch.setattr("gui.config_tabs.chamber_tab.show_diagnostic_dialog", lambda parent, report: reports.append(report))
    ChamberTab._test_chamber_connection(dialog)
    assert reports[-1]["code"] == ("chamber_telemetry" if serial_ok is True else "chamber_open")
    assert reports[-1]["facts"]["port"] == "COM1"
    assert driver.station_id == "08"


def test_relay_failed_reset_does_not_clear_gui_or_claim_success(monkeypatch):
    """Failed controller acknowledgement must not produce a success dialog."""
    reports, cleared, success = [], [], []
    dialog = SimpleNamespace(relay_driver=SimpleNamespace(is_connected=True, reset_all=lambda: False),
                             relay_buttons={3: SimpleNamespace(setChecked=cleared.append)})
    monkeypatch.setattr("gui.config_tabs.relay_tab.show_diagnostic_dialog", lambda parent, report: reports.append(report))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: success.append(args))
    RelayTab._reset_all_relays(dialog)
    assert reports[-1]["code"] == "relay"
    assert not cleared and not success
