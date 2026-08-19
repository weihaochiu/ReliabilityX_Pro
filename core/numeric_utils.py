"""Numeric parsing and formatting utilities for ReliabilityX Pro.

This module centralizes the invalid numeric policy used by IV analysis,
loggers, and GUI plots.  Scientific zero (0.0) is valid only when it is
actually parsed from the data source; invalid text/None/blank/NaN/inf must not
be silently converted into 0.0.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

_LOG = logging.getLogger(__name__)


def _emit_warning(logger: Optional[Any], message: str) -> None:
    target = logger or _LOG
    for method_name in ("warning", "log_warning"):
        method = getattr(target, method_name, None)
        if callable(method):
            try:
                method(message)
                return
            except TypeError:
                continue
    try:
        _LOG.warning(message)
    except Exception:
        pass


def is_blank(value: Any) -> bool:
    """Return True for values that represent intentionally missing data."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def is_valid_number(value: Any, *, allow_inf: bool = False) -> bool:
    """Return True only when value can be represented as a valid float."""
    if is_blank(value):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) or (allow_inf and math.isinf(number))


def parse_float(
    value: Any,
    *,
    default: Any = math.nan,
    field_name: str = "",
    context: str = "",
    logger: Optional[Any] = None,
    warn_invalid: bool = False,
    allow_inf: bool = False,
) -> Any:
    """Parse a numeric field without converting invalid data to scientific zero.

    Parameters
    ----------
    value:
        Input value to parse.
    default:
        Returned when the value is blank, invalid, NaN, or inf (unless
        ``allow_inf`` is true).  Use ``math.nan`` for analysis and ``None`` for
        GUI/loggers that should render blanks.
    field_name/context:
        Optional identifiers included in warning logs.
    logger:
        Python logger or project LogManager-like object.
    warn_invalid:
        Emit a warning when a nonblank invalid value is encountered.
    allow_inf:
        Preserve +/-inf when explicitly allowed.
    """
    if is_blank(value):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        if warn_invalid:
            label = field_name or "numeric_field"
            prefix = f"[{context}] " if context else ""
            _emit_warning(logger, f"{prefix}Invalid numeric value for {label}: {value!r}; stored as invalid, not 0.0")
        return default
    if math.isfinite(number) or (allow_inf and math.isinf(number)):
        return number
    if warn_invalid:
        label = field_name or "numeric_field"
        prefix = f"[{context}] " if context else ""
        _emit_warning(logger, f"{prefix}Non-finite numeric value for {label}: {value!r}; stored as invalid, not 0.0")
    return default


def parse_float_or_nan(value: Any, **kwargs: Any) -> float:
    """Parse value as float, returning NaN for invalid/missing values."""
    return float(parse_float(value, default=math.nan, **kwargs))


def parse_float_or_none(value: Any, **kwargs: Any) -> Optional[float]:
    """Parse value as float, returning None for invalid/missing values."""
    return parse_float(value, default=None, **kwargs)


def format_optional_number(value: Any, digits: int = 6, *, suffix: str = "", blank: str = "") -> str:
    """Format a possibly invalid number without inventing zeroes."""
    number = parse_float_or_none(value)
    if number is None:
        return blank
    return f"{number:.{digits}f}{suffix}"
