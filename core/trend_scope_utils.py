from __future__ import annotations

"""Shared scope/group helpers for Trend Monitor and Telegram notifications."""

from typing import Any, Dict, Iterable, List, Optional

TREND_GROUP_MODE_OPTIONS = ["overall", "user_project"]


def normalize_group_mode(value: Optional[str]) -> str:
    """Normalize notification trend group mode.

    Args:
        value: Raw configured group mode.

    Returns:
        A supported group mode string.
    """
    text = str(value or "").strip().lower()
    return text if text in TREND_GROUP_MODE_OPTIONS else "overall"


def get_trend_group_mode_options() -> List[str]:
    """Return supported notification grouping modes."""
    return list(TREND_GROUP_MODE_OPTIONS)


def make_series_key(entry: Dict[str, Any]) -> str:
    """Build a stable series key for one channel/device result.

    ``experiment_uid`` is preferred when available so a long-duration device can
    be stitched across app restarts and multiple run sessions.  Legacy records
    fall back to user/project/device/channel identity.
    """
    experiment_uid = str(entry.get("experiment_uid") or "").strip()
    if experiment_uid:
        return f"exp:{experiment_uid}"
    user = str(entry.get("user") or "")
    project = str(entry.get("project") or "")
    device = str(entry.get("device_name") or "")
    ch_id = entry.get("ch_id")
    try:
        ch_text = f"{int(ch_id):02d}"
    except Exception:
        ch_text = str(ch_id or "")
    return f"legacy:{user}|{project}|{device}|{ch_text}"


def make_display_label(entry: Dict[str, Any]) -> str:
    """Build the user-visible series label."""
    device = str(entry.get("device_name") or "").strip()
    ch_id = entry.get("ch_id")
    try:
        ch_text = f"CH{int(ch_id):02d}"
    except Exception:
        ch_text = f"CH{ch_id}" if ch_id not in (None, "") else "CH?"
    return f"{device} ({ch_text})" if device else ch_text


def make_group_key(entry: Dict[str, Any], mode: Optional[str]) -> str:
    """Build a stable group key for notifications and trend legend."""
    group_mode = normalize_group_mode(mode)
    if group_mode == "user_project":
        user = str(entry.get("user") or "N/A").strip() or "N/A"
        project = str(entry.get("project") or "N/A").strip() or "N/A"
        return f"{user}|{project}"
    return "overall"


def make_group_label(entry: Dict[str, Any], mode: Optional[str] = "user_project") -> str:
    """Build a human-readable group label."""
    group_mode = normalize_group_mode(mode)
    if group_mode == "user_project":
        user = str(entry.get("user") or "N/A").strip() or "N/A"
        project = str(entry.get("project") or "N/A").strip() or "N/A"
        return f"{user} / {project}"
    return "整體"


def annotate_scope_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in normalized key/label fields for one active-scope entry."""
    item = dict(entry or {})
    item["series_key"] = make_series_key(item)
    item["display_label"] = make_display_label(item)
    item["group_label"] = make_group_label(item, "user_project")
    return item


def annotate_scope_entries(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fill in normalized key/label fields for many entries."""
    return [annotate_scope_entry(item) for item in (entries or []) if isinstance(item, dict)]


def group_entries(entries: Iterable[Dict[str, Any]], mode: Optional[str]) -> List[Dict[str, Any]]:
    """Group entries while preserving first-seen order.

    Returns:
        A list of dict items with keys: group_key, group_label, entries.
    """
    ordered: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}
    group_mode = normalize_group_mode(mode)

    for raw in entries or []:
        if not isinstance(raw, dict):
            continue
        item = annotate_scope_entry(raw)
        key = make_group_key(item, group_mode)
        if key not in index:
            group_label = make_group_label(item, group_mode) if group_mode != "overall" else "整體"
            bucket = {"group_key": key, "group_label": group_label, "entries": []}
            index[key] = bucket
            ordered.append(bucket)
        index[key]["entries"].append(item)
    return ordered


def active_scope_series_keys(entries: Iterable[Dict[str, Any]]) -> List[str]:
    """Return active-scope series keys in order."""
    ordered: List[str] = []
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        key = annotate_scope_entry(item).get("series_key")
        if key and key not in ordered:
            ordered.append(key)
    return ordered


def filter_records_to_active_scope(
    records: Iterable[Dict[str, Any]],
    active_scope_entries: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Filter result records to the current active scope.

    Args:
        records: Result records or trend history.
        active_scope_entries: Active scope entries built from channel settings.

    Returns:
        Filtered records annotated with scope keys/labels.
    """
    allowed = set(active_scope_series_keys(active_scope_entries))
    filtered: List[Dict[str, Any]] = []
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        item = annotate_scope_entry(raw)
        if item.get("series_key") in allowed:
            filtered.append(item)
    return filtered
