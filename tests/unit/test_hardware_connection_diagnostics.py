"""Offline diagnostics tests for SMU and chamber connection failures."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import serial
import serial.tools.list_ports

from driver.chamber_driver import ChamberDriver
from driver.smu_driver import SMUDriver
from gui.config_tabs.smu_tab import SMUTab


class FakeVisaResource:
    """In-memory VISA resource used without network or instrument access."""

    def __init__(self, idn_response="GWInstek,GSM-20H10,TEST,V1.00"):
        """Initialize a fake VISA instrument.

        Args:
            idn_response: Response returned for ``*IDN?``.
        """
        self.idn_response = idn_response
        self.timeout = None
        self.read_termination = None
        self.write_termination = None
        self.commands = []
        self.closed = False

    def clear(self):
        """Model a successful VISA clear operation."""

    def query(self, command):
        """Return the configured identity response."""
        self.commands.append(command)
        return self.idn_response

    def write(self, command):
        """Record an outgoing SCPI command."""
        self.commands.append(command)

    def close(self):
        """Record resource closure."""
        self.closed = True


class FakeVisaManager:
    """In-memory VISA manager for deterministic connection tests."""

    def __init__(self, resource=None, open_error=None):
        """Configure the resource or exception returned by ``open_resource``."""
        self.resource = resource
        self.open_error = open_error

    def list_resources(self):
        """Return one representative LAN resource."""
        return ("TCPIP0::192.0.2.10::inst0::INSTR",)

    def open_resource(self, _name):
        """Return the fake resource or raise the configured exception."""
        if self.open_error:
            raise self.open_error
        return self.resource


@dataclass
class FakePort:
    """Minimal serial port metadata for chamber tests."""

    device: str
    description: str = "USB-RS485"
    hwid: str = "USB VID:PID=1234:5678"


def _smu_driver_with_logs(monkeypatch, manager):
    """Build an SMU driver without constructing a real VISA backend."""
    driver = object.__new__(SMUDriver)
    driver.log_mgr = None
    driver.visa_backend = "test-backend"
    driver.rm = manager
    driver.device = None
    driver.is_connected = False
    driver.last_config = {}
    driver.idn = None
    driver.command_timeout_ms = 3000
    records = []
    monkeypatch.setattr(driver, "_log", lambda level, message: records.append((level, message)))
    return driver, records


def _chamber_driver_with_logs(monkeypatch):
    """Build a chamber driver whose log methods write to an in-memory list."""
    driver = ChamberDriver()
    records = []
    monkeypatch.setattr(driver, "_log_info", lambda message: records.append(("INFO", message)))
    monkeypatch.setattr(driver, "_log_warning", lambda message: records.append(("WARNING", message)))
    monkeypatch.setattr(driver, "_log_error", lambda message: records.append(("ERROR", message)))
    return driver, records


def _messages(records):
    """Join captured driver messages for assertions."""
    return "\n".join(message for _level, message in records)


def test_smu_connect_reports_open_stage_resource_and_traceback(monkeypatch):
    """SMU open failures must identify the failed stage and VISA resource."""
    manager = FakeVisaManager(open_error=RuntimeError("connection refused"))
    driver, records = _smu_driver_with_logs(monkeypatch, manager)

    assert driver.connect({"INTERFACE_TYPE": "LAN", "VISA_ADDRESS": "192.0.2.10"}) is False

    messages = _messages(records)
    assert "stage=open_resource" in messages
    assert "TCPIP0::192.0.2.10::inst0::INSTR" in messages
    assert "RuntimeError: connection refused" in messages
    assert "Traceback:" in messages
    assert "resource was not opened" in messages


def test_smu_connect_rejects_empty_idn_and_records_safety_action(monkeypatch):
    """An empty *IDN? reply must not be reported as a valid connection."""
    resource = FakeVisaResource(idn_response="")
    driver, records = _smu_driver_with_logs(monkeypatch, FakeVisaManager(resource=resource))

    assert driver.connect({"INTERFACE_TYPE": "LAN", "VISA_ADDRESS": "192.0.2.10"}) is False

    messages = _messages(records)
    assert "stage=query_idn" in messages
    assert "*IDN? returned an empty response" in messages
    assert "SMU output OFF command sent" in messages
    assert resource.closed is True


def test_smu_connect_logs_resources_and_identity_on_success(monkeypatch):
    """Successful SMU connection logs VISA inventory and IDN evidence."""
    resource = FakeVisaResource()
    driver, records = _smu_driver_with_logs(monkeypatch, FakeVisaManager(resource=resource))

    assert driver.connect({"INTERFACE_TYPE": "LAN", "VISA_ADDRESS": "192.0.2.10"}) is True

    messages = _messages(records)
    assert "VISA resources" in messages
    assert "TX=*IDN?" in messages
    assert "RX=GWInstek,GSM-20H10,TEST,V1.00" in messages
    assert "validation=non_empty_idn" in messages


def test_chamber_connect_reports_missing_port_without_opening_serial(monkeypatch):
    """An empty chamber port must fail before any serial operation."""
    driver, records = _chamber_driver_with_logs(monkeypatch)

    assert driver.connect("") is False

    messages = _messages(records)
    assert "reason=missing_com_port" in messages
    assert "未傳送任何 Chamber 指令" in messages


def test_chamber_connect_reports_port_inventory_and_access_error(monkeypatch):
    """A busy chamber COM port must log inventory, classification, and traceback."""
    driver, records = _chamber_driver_with_logs(monkeypatch)
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [FakePort("COM8")])

    def raise_access_denied(*_args, **_kwargs):
        """Model another process holding the configured serial port."""
        raise serial.SerialException("Access is denied")

    monkeypatch.setattr(serial, "Serial", raise_access_denied)

    assert driver.connect("COM8", 9600) is False

    messages = _messages(records)
    assert "device=COM8" in messages
    assert "reason=port_busy_or_permission_denied" in messages
    assert "SerialException: Access is denied" in messages
    assert "Traceback:" in messages


def test_chamber_telemetry_report_classifies_all_mode_timeout(monkeypatch):
    """Telemetry diagnostics must summarize a complete no-response condition."""
    driver, records = _chamber_driver_with_logs(monkeypatch)
    driver.port = "COM8"
    driver.ser = type("OpenSerial", (), {"is_open": True})()

    trials = [
        {
            "mode": mode,
            "mode_label": label,
            "tx_ascii": "@010140*\\r\\n",
            "tx_hex": "40 30 31",
            "rx_ascii": "",
            "rx_hex": "",
            "response": "",
            "timeout": True,
            "fcs_valid": False,
            "error": "No Response / Timeout",
        }
        for mode, label in zip(driver.FCS_MODES, [driver.FCS_LABELS[item] for item in driver.FCS_MODES])
    ]
    monkeypatch.setattr(
        driver,
        "diagnose_signal",
        lambda _signal: {"ok": False, "selected_mode": driver.fcs_mode, "trials": trials, "ok_trial": None},
    )

    ok, status, report = driver.test_telemetry(probe_all=True)

    assert ok is False
    assert status is None
    assert "reason=all_fcs_modes_timeout_no_rx" in report
    assert "Timeout : True" in report
    assert "reason=all_fcs_modes_timeout_no_rx" in _messages(records)


def test_smu_tab_restores_saved_address_after_interface_hint_update(qapp):
    """Loading settings must not clear the persisted LAN/VISA address."""
    tab = SMUTab(engine=None)
    settings = {
        "SMU_CONFIG": {
            "INTERFACE_TYPE": "LAN",
            "VISA_ADDRESS": "169.254.6.183",
            "DEFAULT_NPLC": 1.0,
        }
    }

    tab.load_settings(settings)

    assert tab.smu_interface_combo.currentText() == "LAN"
    assert tab.smu_addr_combo.currentText() == "169.254.6.183"
    assert tab.get_settings() == settings["SMU_CONFIG"]
    tab.deleteLater()
    qapp.processEvents()


def test_smu_tab_falls_back_to_active_connection_when_saved_address_is_blank(qapp):
    """An active SMU address remains visible when the saved field is absent."""
    smu = SimpleNamespace(
        last_config={
            "INTERFACE_TYPE": "LAN",
            "VISA_ADDRESS": "169.254.6.183",
            "DEFAULT_NPLC": 0.1,
        },
        is_connected=True,
    )
    tab = SMUTab(engine=SimpleNamespace(smu=smu))

    tab.load_settings({"SMU_CONFIG": {"INTERFACE_TYPE": "LAN", "VISA_ADDRESS": ""}})

    assert tab.smu_addr_combo.currentText() == "169.254.6.183"
    assert tab.combo_nplc.currentText() == "1.0"
    tab.deleteLater()
    qapp.processEvents()
