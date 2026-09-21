"""Controller validation and persistence tests without real instruments or files."""

from types import SimpleNamespace

import pytest

import config
from gui.channel_setting_dialog import ChannelSettingDialog
from gui.system_config_dialog import SystemConfigDialog
from gui.config_tabs.relay_tab import RelayTab
from PyQt6.QtWidgets import QMessageBox


def test_overlap_validation_keeps_dialog_open_and_writes_nothing(monkeypatch):
    """Use the real range validator and catch its error before any writes."""
    messages, writes = [], []
    relay = SimpleNamespace(environment_profiles_editor={"instances": {
        "ENV_A_CLIMATE": {"smu_plus_start": 0, "smu_plus_end": 8, "smu_minus_start": 32, "smu_minus_end": 40},
        "ENV_B_INDOOR": {"smu_plus_start": 8, "smu_plus_end": 16, "smu_minus_start": 41, "smu_minus_end": 50},
    }})
    relay.get_settings = lambda: RelayTab._validate_environment_ranges(relay)
    page = SimpleNamespace(get_settings=lambda: {})
    dialog = SimpleNamespace(tab_personnel=page, tab_smu=page, tab_relay=relay)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(config, "save_personnel_settings", lambda *args: writes.append(args))
    SystemConfigDialog.save_all_settings(dialog)
    assert writes == []
    assert "relay 8" in messages[0]
    assert "ENV_A_CLIMATE" in messages[0] and "ENV_B_INDOOR" in messages[0]


@pytest.mark.parametrize("case", ["worker_failure", "legacy", "disk_failure", "success"])
def test_rline_persistence_requires_worker_qualification_and_io_success(monkeypatch, case):
    """No success popup/history after unqualified results or a failed JSON write."""
    writes, history, success, errors = [], [], [], []
    button = SimpleNamespace(setEnabled=lambda state: None, setText=lambda text: None)
    dialog = SimpleNamespace(
        _pending_rline_request_id=1, _loaded_channel_label="CH01", ch_id=1, log_mgr=None,
        action_widget=SimpleNamespace(btn_measure_rline=button, show_rline_error=lambda text: None),
        info_widget=SimpleNamespace(get_data=lambda: {}),
        environment_widget=SimpleNamespace(get_data=lambda: {}),
        _append_rline_history_csv=history.append,
        update_rline_from_selected_relays=lambda: None,
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[2]))
    monkeypatch.setattr("gui.channel_setting_dialog.show_diagnostic_dialog", lambda parent, report: errors.append(report["summary"]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: success.append(args[2]))
    monkeypatch.setattr(config, "load_json_file", lambda *args: {})
    def save(path, payload):
        """Record persistence without filesystem writes."""
        writes.append(payload)
        return case != "disk_failure"
    monkeypatch.setattr(config, "save_json_file", save)
    result = {"request_id": 1, "ok": case != "worker_failure", "pos_pin": 3, "neg_pin": 57,
              "resistance": 1.0, "measured_voltage_V": .01, "measured_current_A": .01,
              "source_current_A": .01, "voltage_limit_V": 1.5,
              "voltage_compliance": False, "validation_version": 1 if case == "legacy" else 2}
    ChannelSettingDialog._on_rline_measurement_result(dialog, result)
    if case == "success":
        assert len(success) == len(history) == len(writes) == 1
        assert writes[0]["line_resistance_map"]["3_57"]["validation_version"] == 2
    else:
        assert errors and not success and not history
        if case != "disk_failure":
            assert writes == []


def test_raw_plot_prefers_measured_voltage(qapp):
    """The live raw curve agrees with measured-voltage analysis and CSV export."""
    from gui.widgets.iv_plot_widget import IVPlotWidget
    widget = IVPlotWidget()
    widget.update_plot({"direction": "fwd", "v_src": 1.2, "v_msd": 1.0,
                        "i_msd": -.01, "v_corr": 1.01, "i_corr": -.01, "area": 1})
    assert widget.data_store["fwd_raw"][-1] == (1.0, -.01)
    widget.deleteLater()
    qapp.processEvents()
