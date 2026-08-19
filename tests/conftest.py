"""Global offline safety gates and shared pytest fixtures."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest


def _blocked_hardware_call(*args: Any, **kwargs: Any) -> None:
    """Fail immediately if a test reaches a real hardware/network entrypoint."""
    del args, kwargs
    pytest.fail("Offline safety gate blocked a real hardware or network connection attempt")


@pytest.fixture(autouse=True)
def block_real_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block VISA, serial, socket, SMU-output, and relay physical operations.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    import pyvisa
    import serial
    import serial.tools.list_ports

    from driver.relay_driver import RelayDriver
    from driver.smu_driver import SMUDriver

    class GuardedSocket(socket.socket):
        """Socket subclass that fails before any outbound connection."""

        def connect(self, address: Any) -> None:
            """Reject all outbound socket connections."""
            del address
            _blocked_hardware_call()

        def connect_ex(self, address: Any) -> int:
            """Reject all outbound socket connections."""
            del address
            _blocked_hardware_call()
            return 1

    monkeypatch.setattr(pyvisa, "ResourceManager", _blocked_hardware_call)
    monkeypatch.setattr(serial, "Serial", _blocked_hardware_call)
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: [])
    monkeypatch.setattr(socket, "create_connection", _blocked_hardware_call)
    monkeypatch.setattr(socket, "socket", GuardedSocket)

    def guard_smu_output(self: SMUDriver, state: Any) -> None:
        """Fail before a production SMU driver can enable output."""
        del self
        if state in (True, "ON", 1):
            pytest.fail("Offline safety gate blocked production SMU output ON")

    monkeypatch.setattr(SMUDriver, "output_control", guard_smu_output)
    monkeypatch.setattr(RelayDriver, "auto_scan", _blocked_hardware_call)
    monkeypatch.setattr(RelayDriver, "switch_on", _blocked_hardware_call)
    monkeypatch.setattr(RelayDriver, "switch_off", _blocked_hardware_call)
    monkeypatch.setattr(RelayDriver, "reset_all", _blocked_hardware_call)


@pytest.fixture
def repository_root() -> Path:
    """Return the ReliabilityX Pro repository root."""
    return Path(__file__).resolve().parents[1]
