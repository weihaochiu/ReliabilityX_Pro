"""In-memory relay double with physical path-state recording."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from tests.mocks.mock_smu import CallRecorder


class MockRelay:
    """Mock a relay controller without importing or opening serial ports."""

    def __init__(self, recorder: CallRecorder | None = None) -> None:
        self.recorder = recorder or CallRecorder()
        self.calls: list[dict[str, Any]] = []
        self.is_connected = True
        self.ser = SimpleNamespace(is_open=True)
        self.relay_state: set[int] = set()
        self.fail_switch = False
        self.fail_reset = False

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        """Record a local and shared call entry."""
        entry = self.recorder.record("relay", method, *args, **kwargs)
        self.calls.append(entry)

    def auto_scan(self) -> bool:
        """Mark the mock connected without serial enumeration."""
        self.is_connected = True
        self.ser.is_open = True
        self._record("auto_scan")
        return True

    def prepare_for_measurement(self) -> None:
        """Apply the mock all-off preparation state."""
        self._record("prepare_for_measurement")
        if not self.reset_all():
            raise IOError("Mock relay reset failure")

    def reset_all(self) -> bool:
        """Clear all in-memory relay channels."""
        self._record("reset_all")
        if self.fail_reset:
            return False
        self.relay_state.clear()
        return True

    def switch_on(self, channel: int) -> bool:
        """Close one in-memory relay channel."""
        self._record("switch_on", int(channel))
        if self.fail_switch:
            return False
        self.relay_state.add(int(channel))
        return True

    def switch_off(self, channel: int) -> bool:
        """Open one in-memory relay channel."""
        self._record("switch_off", int(channel))
        self.relay_state.discard(int(channel))
        return True

    def close(self) -> None:
        """Clear state and close the mock connection."""
        self.relay_state.clear()
        self.is_connected = False
        self.ser.is_open = False
        self._record("close")

    def verify_state(self, channels):
        """Compare expected channels with the in-memory controller mask."""
        self._record("verify_state", set(channels))
        return self.relay_state == set(channels)
