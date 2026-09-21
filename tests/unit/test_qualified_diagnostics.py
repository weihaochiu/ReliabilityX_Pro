"""OI-054 strict scientific, serial and VISA diagnostics with in-memory IO only."""

from types import SimpleNamespace

import pytest

import config
from core.IV_parameter_analysis_utils import calculate_line_resistance, classify_solar_polarity, build_voltage_sweep
from driver.relay_driver import RelayDriver
from driver.smu_driver import SMUDriver, HardwareCommunicationError
from tests.pipeline_support import make_calibration

ORIGINAL_SET_OUTPUT = SMUDriver.set_output_verified
ORIGINAL_RESET = RelayDriver.reset_all


def test_inactive_scaffold_cannot_bypass_qualification():
    """Legacy service entry rejects before any path or instrument access."""
    from core.diagnostics.diagnostics_service import DiagnosticsService
    service = DiagnosticsService(None, None)
    with pytest.raises(RuntimeError, match="disabled"):
        service.measure_line_resistance(3, 57, lambda seconds: None)


@pytest.mark.parametrize("voltage,current,compliance", [
    (1.499, 5e-9, False), (0.0, 5e-9, False), (1.499, 0.01, False),
    (0.01, 0.01, True), (0.01, 0.01, None), (float("nan"), 0.01, False),
    (0.01, float("inf"), False), (0.01, -0.01, False), (0.01, 0.009, False),
])
def test_invalid_rline_never_becomes_resistance(voltage, current, compliance):
    """Reject open, near-limit, unknown, nonfinite and off-setpoint samples."""
    with pytest.raises(ValueError):
        calculate_line_resistance(voltage, current, 0.01, 1.5, compliance)


@pytest.mark.parametrize("voltage,current", [(0.0, 0.01), (0.01, 0.01005), (-0.001, 0.01)])
def test_valid_rline_uses_actual_current(voltage, current):
    """Real zero resistance is allowed only with verified source current."""
    assert calculate_line_resistance(voltage, current, 0.01, 1.5, False) == pytest.approx(abs(voltage / current))


@pytest.mark.parametrize("voltage,current,offset,trip,expected", [
    (0, -.02, 0, False, "normal"), (0, .02, 0, False, "reversed"),
    (0, 5e-9, 0, False, "open_or_dark_or_low_current"),
    (0, -10e-6, 0, False, "open_or_dark_or_low_current"),
    (0, -.02, 0, True, "current_compliance_or_unknown"),
    (0, -.02, 0, None, "current_compliance_or_unknown"),
    (.1, -.02, 0, False, "zero_voltage_not_reached"),
    (float("nan"), -.02, 0, False, "invalid_reading"),
    (0, .001, .002, False, "normal"),
])
def test_solar_polarity_policy(voltage, current, offset, trip, expected):
    """Manual and mandatory checks share signed, offset-aware classification."""
    assert classify_solar_polarity(voltage, current, offset, trip) == expected


@pytest.mark.parametrize("stop,step", [(1, .26), (1, .3), (.3, .1), (1.0, .25)])
def test_sweep_never_overshoots_stop(stop, step):
    """Non-divisible steps must not exceed the user's safety voltage bound."""
    levels = build_voltage_sweep(0, stop, step)
    assert levels[-1] == stop
    assert all(0 <= value <= stop for value in levels)
    assert all(a < b for a, b in zip(levels, levels[1:]))


def test_smu_setting_readbacks_match_manual_commands():
    """Exercise complete current and voltage setup against explicit SCPI replies."""
    responses = {":SOUR:FUNC?": "CURR", ":SOUR:CURR:MODE?": "FIX",
                 ":SOUR:CURR:LEV?": "0.01", ":SENS:VOLT:PROT:LEV?": "1.5"}
    smu = smu_with_query(responses.__getitem__)
    smu.configure_current_source_verified(.01, 1.5)
    responses.update({":SOUR:FUNC?": "VOLT", ":SOUR:VOLT:MODE?": "FIX",
                      ":SOUR:VOLT:LEV?": "0", ":SENS:CURR:PROT:LEV?": ".1"})
    smu.configure_voltage_source_verified(0, .1)
    responses[":SOUR:VOLT:LEV?"] = ".5"
    with pytest.raises(HardwareCommunicationError):
        smu.set_voltage_verified(0)


class MemorySerial:
    """Respond to commands entirely in memory, with no serial constructor."""

    def __init__(self, responses):
        """Store queued raw responses."""
        self.responses = iter(responses)
        self.writes = []
        self.port = "MOCK"
        self.baudrate = 19200

    def reset_input_buffer(self):
        """No physical input buffer exists."""

    def write(self, payload):
        """Record a byte command."""
        self.writes.append(payload)

    def read_until(self, terminator):
        """Return the next scripted frame."""
        return next(self.responses)


def relay_with_frames(frames):
    """Inject a pure serial double without scanning ports."""
    relay = object.__new__(RelayDriver)
    relay.ser = MemorySerial(frames)
    relay.is_connected = True
    relay.total_channels = 64
    relay.command_retry_delay_sec = 0
    relay._log = lambda *args: None
    relay._refresh_runtime_config = lambda: None
    return relay


@pytest.mark.parametrize("frame,expected", [
    (b"relay on 57\r\nERROR\r\n>", False), (b">", False),
    (b"relay on 57\r\n", False), (b"relay on 03\r\n>", False),
    (b"relay on 57\r\n>", True),
])
def test_relay_echo_prompt_is_not_enough(frame, expected):
    """An error or stale/missing echo cannot acknowledge a write."""
    relay = relay_with_frames([frame])
    assert relay._send_command("relay on 57") is expected


@pytest.mark.parametrize("mask,expected", [
    (b"0200000000000008", True), (b"0200000000000009", False),
    (b"0000000000000000", False), (b"ERROR", False),
])
def test_full_readback_detects_extra_or_missing_relays(mask, expected):
    """Physical IDs 3/57 map to decimal bit positions, not hex channel names."""
    relay = relay_with_frames([b"relay readall\r\n" + mask + b"\r\n>"])
    assert relay.verify_state({3, 57}) is expected


def test_reset_requires_zero_readback(monkeypatch):
    """Even acknowledged all-off and fallback fail when mask remains nonzero."""
    relay = relay_with_frames([
        b"relay writeall 0000000000000000\r\n>",
        b"relay readall\r\n0000000000000001\r\n>",
        b"relay readall\r\n0000000000000001\r\n>",
    ])
    monkeypatch.setattr(relay, "switch_off", lambda channel: True)
    assert ORIGINAL_RESET(relay) is False


def smu_with_query(query):
    """Inject a resource double without initializing any VISA backend."""
    smu = object.__new__(SMUDriver)
    smu.is_connected = True
    smu.device = SimpleNamespace(write=lambda command: None, query=query)
    smu._log = lambda *args: None
    return smu


@pytest.mark.parametrize("raw", ["", "ERROR", "2"])
def test_smu_compliance_unknown_is_not_false(raw):
    """Reject malformed compliance responses instead of treating them as zero."""
    with pytest.raises(HardwareCommunicationError):
        smu_with_query(lambda command: raw).read_voltage_compliance()


def test_smu_output_readback_mismatch_raises():
    """Output-off cannot succeed on an on-state reply."""
    with pytest.raises(HardwareCommunicationError):
        ORIGINAL_SET_OUTPUT(smu_with_query(lambda command: "1"), False)


def test_smu_write_exception_not_swallowed():
    """Strict setup propagates resource-write failure."""
    smu = smu_with_query(lambda command: "0")
    def fail(command):
        """Inject transport failure."""
        raise OSError("mock IO failure")
    smu.device.write = fail
    with pytest.raises(HardwareCommunicationError):
        smu.configure_current_source_verified(.01, 1.5)


@pytest.mark.parametrize("change", [
    {"validation_version": 1}, {"measured_current_A": 5e-9},
    {"value": float("nan")}, {"value": -1}, {"value": 149},
    {"voltage_compliance": True},
])
def test_bad_saved_calibration_is_preserved_but_blocked(change):
    """Old or inconsistent records cannot enter formal correction."""
    record = make_calibration(1.0)
    record.update(change)
    payload = {"line_resistance_map": {"3_57": record}}
    status = config.evaluate_rline_calibration(3, 57, calibration_data=payload)
    assert status["value"] is None
    assert status["expired"] is True
    assert status["invalid_reason"]
    assert payload["line_resistance_map"]["3_57"] is record
