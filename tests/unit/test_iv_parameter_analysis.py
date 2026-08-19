"""Scientific regression tests for IV extraction and reporting units."""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.IV_parameter_analysis_utils import IVAnalysisUtils, calculate_iv_parameters
from core.measurement_schema import METRIC_UNIT_MAP


def _linear_curve(scale: float = 1.0, reverse: bool = False) -> list[dict[str, float]]:
    """Build hand-defined I(V) = scale * (-0.02 + 0.02 V) points.

    Args:
        scale: Current multiplier.
        reverse: Return points in reverse voltage order.

    Returns:
        Raw/corrected point dictionaries for the production analyzer.
    """
    voltages = [0.0, 0.25, 0.5, 0.75, 1.0]
    if reverse:
        voltages.reverse()
    return [
        {
            "v_src": voltage,
            "i_msd": scale * (-0.02 + 0.02 * voltage),
            "v_corr": voltage,
            "i_corr": 0.5 * scale * (-0.02 + 0.02 * voltage),
        }
        for voltage in voltages
    ]


@pytest.mark.offline
def test_forward_reverse_raw_corrected_scientific_parameters() -> None:
    """Lock analytical values for forward/reverse and raw/corrected curves."""
    results = calculate_iv_parameters(_linear_curve(), _linear_curve(reverse=True), area_cm2=0.5)

    for direction in ("F", "R"):
        assert results[f"Voc_{direction}_Raw"] == pytest.approx(1.0, abs=1e-12)
        assert results[f"Isc_{direction}_Raw"] == pytest.approx(20.0, rel=1e-12)
        assert results[f"Jsc_{direction}_Raw"] == pytest.approx(40.0, rel=1e-12)
        assert results[f"FF_{direction}_Raw"] == pytest.approx(25.0, rel=1e-12)
        assert results[f"PCE_{direction}_Raw"] == pytest.approx(10.0, rel=1e-12)
        assert results[f"Rs_{direction}_Raw"] == pytest.approx(50.0, rel=1e-12)
        assert results[f"Rsh_{direction}_Raw"] == pytest.approx(0.05, rel=1e-12)
        assert results[f"Pmpp_{direction}_Raw"] == pytest.approx(0.005, rel=1e-12)
        assert results[f"Vmpp_{direction}_Raw"] == pytest.approx(0.5, abs=1e-12)
        assert results[f"Impp_{direction}_Raw"] == pytest.approx(10.0, rel=1e-12)
        assert results[f"Jmpp_{direction}_Raw"] == pytest.approx(20.0, rel=1e-12)

        assert results[f"Voc_{direction}_Corr"] == pytest.approx(1.0, abs=1e-12)
        assert results[f"Isc_{direction}_Corr"] == pytest.approx(10.0, rel=1e-12)
        assert results[f"Jsc_{direction}_Corr"] == pytest.approx(20.0, rel=1e-12)
        assert results[f"FF_{direction}_Corr"] == pytest.approx(25.0, rel=1e-12)
        assert results[f"PCE_{direction}_Corr"] == pytest.approx(5.0, rel=1e-12)
        assert results[f"Pmpp_{direction}_Corr"] == pytest.approx(0.0025, rel=1e-12)

    assert results["HI_Raw"] == pytest.approx(0.0, abs=1e-12)
    assert results["HI_Corr"] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.offline
def test_unit_and_sign_contract() -> None:
    """Verify authoritative units and positive reporting conventions."""
    assert METRIC_UNIT_MAP == {
        "Voc": "V",
        "Isc": "mA",
        "Jsc": "mA/cm²",
        "FF": "%",
        "PCE": "%",
        "Rs": "Ω",
        "Rsh": "kΩ",
        "Pmpp": "W",
        "Vmpp": "V",
        "Impp": "mA",
        "Jmpp": "mA/cm²",
    }
    results = calculate_iv_parameters(_linear_curve(), _linear_curve(reverse=True), area_cm2=0.5)
    for suffix in ("F_Raw", "R_Raw", "F_Corr", "R_Corr"):
        for key in ("Isc", "Jsc", "FF", "PCE", "Pmpp", "Impp", "Jmpp"):
            assert results[f"{key}_{suffix}"] >= 0


@pytest.mark.offline
def test_duplicate_voltage_and_non_finite_points_are_filtered() -> None:
    """Duplicate voltages are averaged and NaN/Inf points are excluded."""
    voltage = [0.0, 0.5, 0.5, 1.0, np.nan, np.inf]
    current = [-0.02, -0.011, -0.009, 0.0, -0.1, 0.1]
    result = IVAnalysisUtils.analyze_scan(voltage, current, area_cm2=0.5)
    assert result["valid"] is True
    assert result["Voc"] == pytest.approx(1.0, abs=1e-12)
    assert result["Isc"] == pytest.approx(-0.02, abs=1e-12)
    assert result["Pmpp"] == pytest.approx(0.005, rel=1e-12)


@pytest.mark.offline
def test_too_few_points_returns_invalid_nan_contract() -> None:
    """A single point must not be reported as a valid IV analysis."""
    result = IVAnalysisUtils.analyze_scan([0.0], [-0.02], area_cm2=0.5)
    assert result["valid"] is False
    assert math.isnan(result["Voc"])
    assert math.isnan(result["PCE"])


@pytest.mark.offline
def test_no_zero_crossing_uses_nearest_measured_point_without_extrapolation() -> None:
    """Lock the current conservative no-crossing fallback behavior."""
    result = IVAnalysisUtils.analyze_scan([0.0, 0.5, 1.0], [-0.03, -0.02, -0.01], area_cm2=1.0)
    assert result["Voc"] == pytest.approx(1.0)
    assert result["Isc"] == pytest.approx(-0.03)


@pytest.mark.offline
@pytest.mark.parametrize("area", [0.0, -1.0])
def test_zero_or_negative_area_marks_area_dependent_metrics_invalid(area: float) -> None:
    """Non-positive device area cannot yield Jsc or PCE."""
    result = IVAnalysisUtils.analyze_scan([0.0, 0.5, 1.0], [-0.02, -0.01, 0.0], area_cm2=area)
    assert math.isnan(result["Jsc"])
    assert math.isnan(result["PCE"])


@pytest.mark.offline
def test_very_small_area_remains_finite_and_explicit() -> None:
    """A small positive area is accepted without divide-by-zero behavior."""
    result = IVAnalysisUtils.analyze_scan([0.0, 0.5, 1.0], [-0.02, -0.01, 0.0], area_cm2=1e-9)
    assert result["Jsc"] == pytest.approx(-2.0e7)
    assert np.isfinite(result["PCE"])


@pytest.mark.offline
def test_zero_current_curve_does_not_fabricate_efficiency() -> None:
    """A zero-current curve must not report non-zero power or efficiency."""
    result = IVAnalysisUtils.analyze_scan([0.0, 0.5, 1.0], [0.0, 0.0, 0.0], area_cm2=1.0)
    assert result["Isc"] == pytest.approx(0.0)
    assert result["Pmpp"] == pytest.approx(0.0)
    assert result["PCE"] == pytest.approx(0.0)
    assert math.isnan(result["FF"])


@pytest.mark.offline
def test_missing_scan_metadata_returns_invalid_prefixed_results() -> None:
    """Missing forward/reverse point lists return invalid values, not crashes."""
    result = calculate_iv_parameters([], [], area_cm2=0.5)
    assert math.isnan(result["Voc_F_Raw"])
    assert math.isnan(result["Voc_R_Corr"])
    assert result["valid_F_Raw"] is False
    assert result["valid_R_Corr"] is False
