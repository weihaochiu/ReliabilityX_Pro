"""In-memory SMU double with ordered call and output-state recording."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CallRecorder:
    """Record calls from multiple mock devices in one total order."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    _sequence: int = 0

    def record(self, device: str, method: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Append one timestamped call.

        Args:
            device: Mock device name.
            method: Method or action name.
            *args: Positional call arguments.
            **kwargs: Keyword call arguments.

        Returns:
            The appended call dictionary.
        """
        self._sequence += 1
        entry = {
            "sequence": self._sequence,
            "timestamp": time.monotonic(),
            "device": device,
            "method": method,
            "args": args,
            "kwargs": kwargs,
        }
        self.calls.append(entry)
        return entry


class MockSMU:
    """Mock an SMU without importing or opening VISA resources.

    Args:
        recorder: Optional recorder shared with relay/environment mocks.
        measurement: Optional callable receiving the configured voltage and
            returning ``(measured_voltage, measured_current)``.
    """

    def __init__(
        self,
        recorder: CallRecorder | None = None,
        measurement: Callable[[float], tuple[float, float]] | None = None,
    ) -> None:
        self.recorder = recorder or CallRecorder()
        self.calls: list[dict[str, Any]] = []
        self.is_connected = True
        self.output_state = False
        self.configured_voltage = 0.0
        self.configured_current_limit = 0.0
        self.configured_current = 0.0
        self.configured_voltage_limit = 0.0
        self.read_exception: Exception | None = None
        self._measurement = measurement or (lambda voltage: (float(voltage), -0.02 + (0.02 * float(voltage))))

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        """Record a local and shared call entry."""
        entry = self.recorder.record("smu", method, *args, **kwargs)
        self.calls.append(entry)

    def get_idn(self) -> str:
        """Return a deterministic non-hardware identity."""
        self._record("get_idn")
        return "MOCK,SMU,OFFLINE,1"

    def connect(self) -> bool:
        """Mark the mock connected without external IO."""
        self.is_connected = True
        self._record("connect")
        return True

    def configure_source(self, voltage: float, current_limit: float) -> None:
        """Record voltage-source configuration."""
        self.configured_voltage = float(voltage)
        self.configured_current_limit = float(current_limit)
        self._record("configure_source", voltage, current_limit=current_limit)

    def configure_source_curr(self, current: float, v_limit: float) -> None:
        """Record current-source configuration."""
        self.configured_current = float(current)
        self.configured_voltage_limit = float(v_limit)
        self._record("configure_source_curr", current, v_limit=v_limit)

    def output_control(self, state: Any) -> None:
        """Record output state transitions."""
        self.output_state = state in (True, "ON", 1)
        self._record("output_control", "ON" if self.output_state else "OFF")

    def set_voltage(self, voltage: float) -> None:
        """Record a source-voltage point."""
        self.configured_voltage = float(voltage)
        self._record("set_voltage", voltage)

    def read_vi(self) -> tuple[float, float]:
        """Return a synthetic point or raise the configured exception."""
        self._record("read_vi", self.configured_voltage)
        if self.read_exception is not None:
            raise self.read_exception
        return self._measurement(self.configured_voltage)

    def is_output_on(self) -> bool:
        """Return the in-memory output state."""
        self._record("is_output_on")
        return self.output_state

    def set_output_verified(self, enabled):
        """Simulate verified output through the recorded mock transition."""
        self.output_control(enabled)

    def configure_current_source_verified(self, current, v_limit):
        """Simulate current-source verification without hardware."""
        self.configure_source_curr(current, v_limit)

    def configure_voltage_source_verified(self, voltage, current_limit):
        """Simulate voltage-source verification without hardware."""
        self.configure_source(voltage, current_limit)

    def set_voltage_verified(self, voltage):
        """Simulate a verified source step."""
        self.set_voltage(voltage)

    def read_voltage_compliance(self):
        """Return the configurable synthetic voltage-compliance flag."""
        return getattr(self, "voltage_compliance", False)

    def read_current_compliance(self):
        """Return the configurable synthetic current-compliance flag."""
        return getattr(self, "current_compliance", False)

    def close(self) -> None:
        """Force mock output off and mark the connection closed."""
        self.output_state = False
        self.is_connected = False
        self._record("close")
