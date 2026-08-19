from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from core.measurement_schema import (
    TREND_METRIC_OPTIONS,
    TREND_METRIC_KEY_MAP,
    metric_key_from_label as _schema_metric_key_from_label,
    metric_slug_from_label as _schema_metric_slug_from_label,
)
from core.numeric_utils import parse_float_or_none

TREND_DIRECTION_OPTIONS: List[str] = ["逆掃 (Reverse)", "正掃 (Forward)"]
TREND_PATH_OPTIONS: List[str] = ["修正後 (Corr)", "原始 (Raw)"]
TREND_X_AXIS_OPTIONS: List[str] = ["運行時間 (Hours)", "量測序號 (Seq)"]

_METRIC_KEY_MAP = dict(TREND_METRIC_KEY_MAP)

def get_trend_metric_options() -> List[str]:
    return list(TREND_METRIC_OPTIONS)


def get_trend_direction_options() -> List[str]:
    return list(TREND_DIRECTION_OPTIONS)


def get_trend_path_options() -> List[str]:
    return list(TREND_PATH_OPTIONS)


def get_trend_x_axis_options() -> List[str]:
    return list(TREND_X_AXIS_OPTIONS)


def metric_supports_direction(metric_label: str) -> bool:
    return metric_key_from_label(metric_label) != "HI"


def metric_key_from_label(metric_label: str) -> str:
    return _schema_metric_key_from_label(metric_label)


def normalize_metric_labels(metric_labels: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for item in metric_labels or []:
        text = str(item or "").strip()
        if text == "Hysteresis_Index":
            text = "Hysteresis Index"
        if text in TREND_METRIC_OPTIONS and text not in normalized:
            normalized.append(text)
    return normalized


def normalize_direction_label(label: Optional[str]) -> str:
    text = str(label or "").strip()
    return text if text in TREND_DIRECTION_OPTIONS else TREND_DIRECTION_OPTIONS[0]


def normalize_path_label(label: Optional[str]) -> str:
    text = str(label or "").strip()
    return text if text in TREND_PATH_OPTIONS else TREND_PATH_OPTIONS[0]


def normalize_x_axis_label(label: Optional[str]) -> str:
    text = str(label or "").strip()
    return text if text in TREND_X_AXIS_OPTIONS else TREND_X_AXIS_OPTIONS[1]


def direction_code(direction_label: Optional[str]) -> str:
    label = normalize_direction_label(direction_label)
    return "R" if "Reverse" in label else "F"


def path_code(path_label: Optional[str]) -> str:
    label = normalize_path_label(path_label)
    return "Corr" if "Corr" in label else "Raw"


def metric_filename_slug(metric_label: str) -> str:
    return _schema_metric_slug_from_label(metric_label)


def get_metric_value(result: Dict[str, Any], metric_label: str, direction_label: Optional[str], path_label: Optional[str], default: Optional[float] = None):
    metric_key = metric_key_from_label(metric_label)
    result = result or {}
    path = path_code(path_label)

    if metric_key == "HI":
        for key in (f"HI_{path}", f"Hysteresis_Index_{path}", "HI", "Hysteresis_Index"):
            value = parse_float_or_none(result.get(key))
            if value is not None:
                return value
        return default

    direction = direction_code(direction_label)
    lookup_candidates = [
        f"{metric_key}_{direction}_{path}",
        f"{metric_key}_{direction.lower()}_{path}",
        f"{metric_key}_{direction}_{path.lower()}",
        f"{metric_key}_{direction.lower()}_{path.lower()}",
    ]
    alias_map = {
        "PCE": ["Eff_f", "PCE_f", "Eff_r", "PCE_r", "PCE"],
        "Voc": ["Voc_f", "Voc_r", "Voc"],
        "Jsc": ["Jsc_f", "Jsc_r", "Jsc"],
        "FF": ["FF_f", "FF_r", "FF"],
        "Rs": ["Rs_f", "Rs_r", "Rs"],
        "Rsh": ["Rsh_f", "Rsh_r", "Rsh", "Rsh_kOhm"],
        "Pmpp": ["Pmpp_f", "Pmpp_r", "Pmpp"],
        "Vmpp": ["Vmpp_f", "Vmpp_r", "Vmpp"],
        "Impp": ["Impp_f", "Impp_r", "Impp"],
        "Jmpp": ["Jmpp_f", "Jmpp_r", "Jmpp"],
    }
    lookup_candidates.extend(alias_map.get(metric_key, [metric_key]))

    for key in lookup_candidates:
        value = parse_float_or_none(result.get(key))
        if value is not None:
            return value

    container_names = {
        ("F", "Raw"): ["Forward_Raw", "F_Raw", "forward_raw", "forwardRaw"],
        ("R", "Raw"): ["Reversed_Raw", "Reverse_Raw", "R_Raw", "reversed_raw", "reverse_raw", "reversedRaw"],
        ("F", "Corr"): ["Forward_Corr", "F_Corr", "forward_corr", "forwardCorr"],
        ("R", "Corr"): ["Reversed_Corr", "Reverse_Corr", "R_Corr", "reversed_corr", "reverse_corr", "reversedCorr"],
    }.get((direction, path), [])

    aliases = [metric_key, metric_key.lower(), metric_key.upper()]
    if metric_key == "Rsh":
        aliases.extend(["Rsh_kOhm", "rsh_kohm", "RSH_KOHM"])

    for container_name in container_names:
        sub = result.get(container_name)
        if isinstance(sub, dict):
            for alias in aliases:
                value = parse_float_or_none(sub.get(alias))
                if value is not None:
                    return value

    return default
