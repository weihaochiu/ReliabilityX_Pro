"""In-memory environment-controller double for offline orchestration tests."""

from __future__ import annotations

from typing import Any

from tests.mocks.mock_smu import CallRecorder


class MockEnvironment:
    """Record environment commands without serial, LAN, or physical actions."""

    def __init__(self, recorder: CallRecorder | None = None) -> None:
        self.recorder = recorder or CallRecorder()
        self.calls: list[dict[str, Any]] = []
        self.connected = True
        self.output_state = False
        self.temperature = 25.0
        self.humidity = 50.0

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        """Record one mock environment call."""
        entry = self.recorder.record("environment", method, *args, **kwargs)
        self.calls.append(entry)

    def is_connected(self) -> bool:
        """Return the mock connection state."""
        self._record("is_connected")
        return self.connected

    def read_status(self) -> dict[str, float]:
        """Return deterministic synthetic telemetry."""
        self._record("read_status")
        return {"temp_pv": self.temperature, "hum_pv": self.humidity}

    def set_environment(self, *, temperature: float, humidity: float) -> None:
        """Record synthetic setpoints without controlling equipment."""
        self.temperature = float(temperature)
        self.humidity = float(humidity)
        self._record("set_environment", temperature=temperature, humidity=humidity)

    def output_control(self, state: Any) -> None:
        """Record an in-memory environment output transition."""
        self.output_state = state in (True, "ON", 1)
        self._record("output_control", "ON" if self.output_state else "OFF")

    def close(self) -> None:
        """Close the mock environment controller."""
        self.output_state = False
        self.connected = False
        self._record("close")
