"""Central IV result schema and display-unit registry.

All runtime modules should use this file instead of hard-coding labels such as
``Jsc (mA/cm²)`` or ``Rsh (kΩ)`` independently.  The analysis layer returns
summary-scale values using these reporting units.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List

SCHEMA_VERSION = "iv-summary-unit-schema-v1"


@dataclass(frozen=True)
class IVMetric:
    key: str
    summary_header: str
    trend_label: str
    unit: str
    filename_slug: str
    supports_direction: bool = True


IV_METRICS: List[IVMetric] = [
    IVMetric("Voc", "Voc(V)", "Voc (V)", "V", "voc"),
    IVMetric("Isc", "Isc(mA)", "Isc (mA)", "mA", "isc"),
    IVMetric("Jsc", "Jsc(mA/cm²)", "Jsc (mA/cm²)", "mA/cm²", "jsc"),
    IVMetric("FF", "FF(%)", "FF (%)", "%", "ff"),
    IVMetric("PCE", "PCE(%)", "PCE (%)", "%", "pce"),
    IVMetric("Rs", "Rs(Ω)", "Rs (Ω)", "Ω", "rs"),
    IVMetric("Rsh", "Rsh(kΩ)", "Rsh (kΩ)", "kΩ", "rsh"),
    IVMetric("Pmpp", "Pmpp(W)", "Pmpp (W)", "W", "pmpp"),
    IVMetric("Vmpp", "Vmpp(V)", "Vmpp (V)", "V", "vmpp"),
    IVMetric("Impp", "Impp(mA)", "Impp (mA)", "mA", "impp"),
    IVMetric("Jmpp", "Jmpp(mA/cm²)", "Jmpp (mA/cm²)", "mA/cm²", "jmpp"),
]

HYSTERESIS_METRIC = IVMetric(
    "HI",
    "Hysteresis_Index",
    "Hysteresis Index",
    "",
    "hysteresis_index",
    supports_direction=False,
)

IV_PARAMETER_KEYS: List[str] = [metric.key for metric in IV_METRICS]
SUMMARY_SUB_HEADERS: List[str] = [metric.summary_header for metric in IV_METRICS]
TREND_METRIC_OPTIONS: List[str] = [metric.trend_label for metric in IV_METRICS] + [HYSTERESIS_METRIC.trend_label]
TREND_METRIC_KEY_MAP: Dict[str, str] = {metric.trend_label: metric.key for metric in IV_METRICS}
TREND_METRIC_KEY_MAP[HYSTERESIS_METRIC.trend_label] = HYSTERESIS_METRIC.key
TREND_METRIC_KEY_MAP["Hysteresis_Index"] = HYSTERESIS_METRIC.key  # legacy label
TREND_METRIC_SLUG_MAP: Dict[str, str] = {metric.trend_label: metric.filename_slug for metric in IV_METRICS}
TREND_METRIC_SLUG_MAP[HYSTERESIS_METRIC.trend_label] = HYSTERESIS_METRIC.filename_slug
TREND_METRIC_SLUG_MAP["Hysteresis_Index"] = HYSTERESIS_METRIC.filename_slug
METRIC_UNIT_MAP: Dict[str, str] = {metric.key: metric.unit for metric in IV_METRICS}
METRIC_TREND_LABEL_BY_KEY: Dict[str, str] = {metric.key: metric.trend_label for metric in IV_METRICS}
METRIC_TREND_LABEL_BY_KEY[HYSTERESIS_METRIC.key] = HYSTERESIS_METRIC.trend_label

IV_CURVE_POINT_HEADERS: List[str] = [
    "Scan_Direction",
    "Voltage_RAW(V)",
    "Current_Raw(A)",
    "Current_Density_Raw(A/cm²)",
    "Output_Power_Raw(W)",
    "Voltage_Corr(V)",
    "Current_Corr(A)",
    "Current_Density_Corr(A/cm²)",
    "Output_Power_Corr(W)",
]


def metric_key_from_label(label: str) -> str:
    return TREND_METRIC_KEY_MAP.get(str(label or "").strip(), "PCE")


def metric_label_from_key(key: str) -> str:
    return METRIC_TREND_LABEL_BY_KEY.get(str(key or ""), str(key or ""))


def metric_slug_from_label(label: str) -> str:
    return TREND_METRIC_SLUG_MAP.get(str(label or "").strip(), "trend")


def forward_card_metrics(results: dict) -> tuple[float | None, float | None, str]:
    """Resolve a coherent forward Voc/PCE pair for OI-051 card displays.

    Args:
        results: Canonical analysis payload, optionally carrying validity flags.

    Returns:
        Voc, PCE and source (Corr, Raw, Legacy or Invalid). Explicit invalidity
        blocks that source; finite zeroes are valid. Legacy aliases apply only
        to payloads without canonical forward keys.
    """
    def finite_number(value):
        """Parse one finite metric without fabricating missing zeroes."""
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            return None
        return number if math.isfinite(number) else None

    for source in ("Corr", "Raw"):
        suffix = f"F_{source}"
        if not bool(results.get(f"valid_{suffix}", True)):
            continue
        voc = finite_number(results.get(f"Voc_{suffix}"))
        pce = finite_number(results.get(f"PCE_{suffix}"))
        if voc is not None and pce is not None:
            return voc, pce, source
    canonical = ("Voc_F_Corr", "PCE_F_Corr", "Voc_F_Raw", "PCE_F_Raw", "valid_F_Corr", "valid_F_Raw")
    if not any(key in results for key in canonical):
        voc, pce = finite_number(results.get("Voc_f")), finite_number(results.get("Eff_f"))
        if voc is not None and pce is not None:
            return voc, pce, "Legacy"
    return None, None, "Invalid"
