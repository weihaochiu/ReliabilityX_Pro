"""Calibration schema and correction-equation regression tests."""

from __future__ import annotations

import datetime as dt

import pytest

import config
from core.measure_engine import MeasureEngine
from tests.mocks.mock_relay import MockRelay
from tests.mocks.mock_smu import MockSMU
from tests.pipeline_support import make_calibration


@pytest.mark.offline
def test_offset_and_rline_correction_equation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lock ADR-0043 current-offset then line-resistance correction order."""
    smu = MockSMU(measurement=lambda voltage: (1.2, 0.012))
    engine = MeasureEngine(smu_driver=smu, relay_driver=MockRelay())
    engine.cal_settings = {"offset_current": 0.002}
    engine.is_running = True
    monkeypatch.setattr(engine, "_interruptible_sleep", lambda seconds: None)

    point = engine.scan_sequence(1, [1.0], {"i_limit": 0.1, "delay_time": 0}, "fwd", 5.0)[0]
    assert point["i_msd"] == pytest.approx(0.012)
    assert point["i_corr"] == pytest.approx(0.010)
    assert point["v_corr"] == pytest.approx(1.15)


@pytest.mark.offline
@pytest.mark.parametrize("offset", [0.0, 0.002, -0.002])
@pytest.mark.parametrize("r_line", [0.0, 5.0])
@pytest.mark.parametrize("measured_current", [1e-9, 0.2])
def test_correction_matrix(
    monkeypatch: pytest.MonkeyPatch, offset: float, r_line: float, measured_current: float
) -> None:
    """Cover zero/positive/negative offset and zero/normal R-line currents."""
    smu = MockSMU(measurement=lambda voltage: (0.8, measured_current))
    engine = MeasureEngine(smu_driver=smu, relay_driver=MockRelay())
    engine.cal_settings = {"offset_current": offset}
    engine.is_running = True
    monkeypatch.setattr(engine, "_interruptible_sleep", lambda seconds: None)
    point = engine.scan_sequence(1, [0.8], {"i_limit": 0.5, "delay_time": 0}, "fwd", r_line)[0]
    expected_current = measured_current - offset
    assert point["i_corr"] == pytest.approx(expected_current, rel=1e-12, abs=1e-15)
    assert point["v_corr"] == pytest.approx(0.8 - expected_current * r_line, rel=1e-12, abs=1e-15)


@pytest.mark.offline
def test_calibration_record_freshness_and_missing_timestamp_policy() -> None:
    """Fresh records pass and untraceable legacy values are hard blockers."""
    now = dt.datetime.now().replace(microsecond=0)
    fresh = {
        "line_resistance_map": {
            "1_2": make_calibration(3.5, now.strftime("%Y-%m-%d %H:%M:%S")),
            "3_4": 2.0,
        }
    }
    valid = config.evaluate_rline_calibration(1, 2, calibration_data=fresh, max_age_days=30)
    legacy = config.evaluate_rline_calibration(3, 4, calibration_data=fresh, max_age_days=30)
    assert valid["exists"] is True
    assert valid["expired"] is False
    assert valid["value"] == pytest.approx(3.5)
    assert legacy["exists"] is True
    assert legacy["expired"] is True
