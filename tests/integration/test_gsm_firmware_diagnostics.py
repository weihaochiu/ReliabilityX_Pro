"""OI-057 integration with a strict, in-memory GSM protocol emulator (no hardware)."""

from types import MethodType

import pyvisa
import pytest

from driver.smu_driver import SMUDriver
from tests.pipeline_support import build_offline_engine, make_channel

ORIGINAL_OUTPUT = SMUDriver.set_output_verified


class FirmwareResource:
    """Reject legacy source-LEVel queries just like the supplied V1.22 log."""

    resource_name = "MOCK::GSM20H10"

    def __init__(self, *, open_clips=False, timeout_query=None):
        """Initialize only memory state, never a VISA resource manager."""
        self.open_clips = open_clips
        self.timeout_query = timeout_query
        self.commands = []
        self.output = False
        self.source = "VOLT"
        self.current = .01
        self.voltage = 0.0
        self.voltage_limit = 1.5
        self.current_limit = .1

    def write(self, command):
        """Apply explicitly supported writes to in-memory state."""
        self.commands.append(command)
        key, value = command.split(" ", 1)
        if key == ":OUTP":
            self.output = value == "ON"
        elif key == ":SOUR:FUNC":
            self.source = value
        elif key == ":SOUR:CURR:LEV":
            self.current = float(value)
        elif key == ":SOUR:VOLT:LEV":
            self.voltage = float(value)
        elif key == ":SENS:VOLT:PROT:LEV":
            self.voltage_limit = float(value)
        elif key == ":SENS:CURR:PROT:LEV":
            self.current_limit = float(value)
        elif key not in {":SOUR:CURR:MODE", ":SOUR:VOLT:MODE"}:
            raise AssertionError(f"Unmodelled write: {command}")

    def query(self, command):
        """Return a documented reply or inject the recorded VISA timeout."""
        self.commands.append(command)
        if command in {":SOUR:CURR:LEV?", ":SOUR:VOLT:LEV?", self.timeout_query}:
            raise pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_timeout)
        responses = {
            ":OUTP:STAT?": str(int(self.output)), ":SOUR:FUNC?": self.source,
            ":SOUR:CURR:MODE?": "FIXed", ":SOUR:VOLT:MODE?": "FIXed",
            ":SOUR:CURR?": str(self.current), ":SOUR:VOLT?": str(self.voltage),
            ":SENS:VOLT:PROT:LEV?": str(self.voltage_limit),
            ":SENS:CURR:PROT:LEV?": str(self.current_limit),
            ":SENS:VOLT:PROT:TRIP?": "1" if self.open_clips else "0",
            ":SENS:CURR:PROT:TRIP?": "0",
        }
        if command == ":READ?":
            assert self.output, "Sampling must follow verified ON"
            if self.source == "CURR":
                return "1.499,5e-9" if self.open_clips else "0.01,0.01"
            return f"{self.voltage},{-.02 + .02 * self.voltage}"
        return responses[command]


def injected_smu(resource):
    """Bind actual driver methods exclusively to our memory resource."""
    smu = object.__new__(SMUDriver)
    smu.device = resource
    smu.is_connected = True
    smu.idn = "MOCK,GSM-20H10,OFFLINE,V1.22"
    smu.log_mgr = None
    smu.last_config = {}
    smu.set_output_verified = MethodType(ORIGINAL_OUTPUT, smu)
    return smu


@pytest.mark.parametrize("open_clips", [False, True])
def test_documented_queries_reach_output_and_sample(tmp_path, monkeypatch, open_clips):
    """Short/open branches both reach sampling; only a valid short can qualify."""
    resource = FirmwareResource(open_clips=open_clips)
    engine, _, relay, _ = build_offline_engine(tmp_path, monkeypatch, smu=injected_smu(resource))
    results, progress = [], []
    engine.line_resistance_result.connect(results.append)
    engine.diagnostic_progress.connect(progress.append)
    engine.request_line_resistance_measurement(123, 3, 57)
    assert ":SOUR:CURR?" in resource.commands
    assert ":SOUR:CURR:LEV?" not in resource.commands
    assert ":OUTP ON" in resource.commands and ":READ?" in resource.commands
    assert resource.commands.index(":SOUR:CURR?") < resource.commands.index(":OUTP ON") < resource.commands.index(":READ?")
    assert not resource.output and not relay.relay_state
    assert all(item["request_id"] == 123 for item in progress)
    assert progress[-1]["stage"] == "cleanup"
    if open_clips:
        report = results[-1]["diagnostic"]
        assert report["code"] == "rline_open"
        assert report["facts"]["sample_acquired"] is True
        assert "兩夾分開" in report["summary"]
        assert results[-1]["ok"] is False
    else:
        assert results[-1]["ok"] is True
        assert results[-1]["resistance"] == pytest.approx(1)


@pytest.mark.parametrize("query", [":SOUR:CURR?", ":SENS:VOLT:PROT:LEV?"])
def test_remaining_timeout_reports_exact_stage_and_never_enables_output(tmp_path, monkeypatch, query):
    """New spelling is not a bypass: unconfirmed settings still fail safely."""
    resource = FirmwareResource(timeout_query=query)
    engine, _, relay, _ = build_offline_engine(tmp_path, monkeypatch, smu=injected_smu(resource))
    results = []
    engine.line_resistance_result.connect(results.append)
    engine.request_line_resistance_measurement(5, 3, 57)
    report = results[-1]["diagnostic"]
    assert report["stage"] == "smu_setup" and report["code"] == "smu_timeout"
    assert report["command"] == query and report["response"] is None
    assert report["facts"]["relay_pair_confirmed"] is True
    assert report["facts"]["output_attempted"] is False
    assert report["facts"]["smu_off_confirmed"] is report["facts"]["relay_off_confirmed"] is True
    assert "尚未送出 ON" in report["summary"]
    assert "不能據此判定夾子開路" in report["summary"]
    assert ":OUTP ON" not in resource.commands and ":READ?" not in resource.commands
    assert not relay.relay_state


def test_voltage_query_used_by_polarity_and_formal_scan(tmp_path, monkeypatch):
    """The sibling VOLT:LEV? failure must not remain in the formal path."""
    resource = FirmwareResource()
    engine, _, _, _ = build_offline_engine(tmp_path, monkeypatch, smu=injected_smu(resource))
    engine.start_scan_cycle([make_channel()])
    assert engine.completed_channel_count == 1
    assert ":SOUR:VOLT?" in resource.commands
    assert ":SOUR:VOLT:LEV?" not in resource.commands
    assert not resource.output
