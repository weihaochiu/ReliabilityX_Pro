"""Offline tests for Numato Relay connection diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest
import serial
import serial.tools.list_ports

from driver.relay_driver import RelayDriver


ORIGINAL_AUTO_SCAN = RelayDriver.auto_scan


@dataclass
class FakePort:
    """Minimal pyserial port metadata used by offline tests."""

    device: str
    description: str = "USB Serial Port"
    hwid: str = "USB VID:PID=2A19:0C02"
    manufacturer: str = "Numato Lab"
    vid: Optional[int] = 0x2A19
    pid: Optional[int] = 0x0C02


class FakeSerial:
    """In-memory serial probe that never reaches physical hardware."""

    response = b""

    def __init__(self, port, baudrate, timeout, write_timeout):
        """Record the requested serial settings.

        Args:
            port: Requested COM port.
            baudrate: Requested baud rate.
            timeout: Read timeout.
            write_timeout: Write timeout.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.writes = []
        self.closed = False
        self.is_open = True

    def reset_input_buffer(self):
        """Model a successful input-buffer reset."""

    def reset_output_buffer(self):
        """Model a successful output-buffer reset."""

    def write(self, payload):
        """Record an outgoing probe without touching hardware."""
        self.writes.append(payload)

    def read(self, _size):
        """Return the class-configured in-memory response."""
        return self.response

    def close(self):
        """Record that the fake serial handle was closed."""
        self.closed = True
        self.is_open = False


def _driver_with_logs(monkeypatch):
    """Create a RelayDriver whose logs are captured in memory.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        tuple: Relay driver and captured ``(level, message)`` records.
    """
    driver = RelayDriver()
    records = []
    monkeypatch.setattr(driver, "_log", lambda level, message: records.append((level, message)))
    return driver, records


def _messages(records):
    """Join captured log messages for concise assertions."""
    return "\n".join(message for _level, message in records)


def test_auto_scan_reports_when_windows_has_no_serial_ports(monkeypatch):
    """An empty COM list must produce an actionable failure reason."""
    driver, records = _driver_with_logs(monkeypatch)
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [])

    assert ORIGINAL_AUTO_SCAN(driver) is False

    messages = _messages(records)
    assert "未列舉到任何 COM Port" in messages
    assert "reason=no_serial_ports" in messages
    assert "attempted_ports=0" in messages
    assert "裝置管理員" in messages


def test_auto_scan_logs_open_exception_type_and_traceback(monkeypatch):
    """A busy or inaccessible COM port must retain exception evidence."""
    driver, records = _driver_with_logs(monkeypatch)
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [FakePort("COM7")])

    def raise_access_denied(*_args, **_kwargs):
        """Model Windows rejecting an occupied COM port."""
        raise serial.SerialException("Access is denied")

    monkeypatch.setattr(serial, "Serial", raise_access_denied)

    assert ORIGINAL_AUTO_SCAN(driver) is False

    messages = _messages(records)
    assert "device=COM7" in messages
    assert "SerialException: Access is denied" in messages
    assert "Traceback:" in messages
    assert "COM7: SerialException" in messages


@pytest.mark.parametrize(
    ("response", "expected_reason"),
    [
        (b"", "timeout_or_no_response"),
        (b"Other Device v1.0\r\n>", "identifier_mismatch"),
    ],
)
def test_auto_scan_distinguishes_no_response_from_identifier_mismatch(
    monkeypatch,
    response,
    expected_reason,
):
    """Probe logs must distinguish timeout from an unexpected device reply."""
    driver, records = _driver_with_logs(monkeypatch)
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [FakePort("COM8")])
    FakeSerial.response = response
    monkeypatch.setattr(serial, "Serial", FakeSerial)

    assert ORIGINAL_AUTO_SCAN(driver) is False

    messages = _messages(records)
    assert "TX_ASCII=ver\\r" in messages
    assert "TX_HEX=76 65 72 0D" in messages
    assert f"reason={expected_reason}" in messages
    assert "RX_ASCII=" in messages
    assert "RX_HEX=" in messages


def test_auto_scan_logs_valid_numato_response_and_connects(monkeypatch):
    """A recognized reply must preserve detailed success evidence."""
    driver, records = _driver_with_logs(monkeypatch)
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [FakePort("COM9")])
    FakeSerial.response = b"Numato Lab 64 Channel USB Relay\r\n>"
    monkeypatch.setattr(serial, "Serial", FakeSerial)
    monkeypatch.setattr(driver, "reset_all", lambda: True)

    assert ORIGINAL_AUTO_SCAN(driver) is True
    assert driver.is_connected is True
    assert driver.ser is not None

    messages = _messages(records)
    assert "Relay probe 回覆有效" in messages
    assert "validation=configured_identifier_matched" in messages
    assert "成功連線至 Relay 板: COM9" in messages
