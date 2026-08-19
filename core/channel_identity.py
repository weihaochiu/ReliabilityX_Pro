"""Channel identity, schema migration, and archival helpers for ReliabilityX Pro.

This module intentionally preserves the legacy top-level numeric
``channel_settings.json`` layout to avoid breaking the current GUI/runtime, but
adds explicit schema metadata and stable identifiers that downstream features
can rely on:

- ``experiment_uid``: stable identifier for one device/experiment across app
  restarts and multiple run sessions.
- ``run_session_id``: identifier for a single Start All Cyclic Measurement run.
- ``channel_schema_version`` / top-level ``__schema_version``: migration guards.

The active relay assignment source-of-truth is the numeric channel record in
``channel_settings.json``.  ``hardware_map.json`` is treated as a default
mapping/template and legacy migration reference only.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = 2
ARCHIVE_SCHEMA_VERSION = 1
_RUNTIME_PREFIX = "__"


def is_runtime_metadata_key(key: Any) -> bool:
    return str(key).startswith(_RUNTIME_PREFIX)


def is_channel_key(key: Any) -> bool:
    return str(key).isdigit()


def _slug(value: Any, *, fallback: str = "NA", max_len: int = 40) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", text)
    text = re.sub(r"[^\w\u4e00-\u9fff.-]", "", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return (text or fallback)[:max_len]


def utc_now_text() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def generate_run_session_id(now: Optional[_dt.datetime] = None) -> str:
    now = now or _dt.datetime.now()
    return f"RUN_{now.strftime('%Y%m%d_%H%M%S')}"


def _fallback_channel_label(ch_id: Any) -> str:
    try:
        return f"CH{int(ch_id):02d}"
    except Exception:
        return f"CH{ch_id or 'UNKNOWN'}"


def has_complete_relay_path(record: Dict[str, Any]) -> bool:
    try:
        int(record.get("relay_pos"))
        int(record.get("relay_neg"))
        return True
    except Exception:
        return False


def infer_channel_status(record: Dict[str, Any]) -> str:
    if not isinstance(record, dict):
        return "invalid"
    if not has_complete_relay_path(record):
        return "draft"
    if record.get("is_enabled"):
        return "active"
    return "configured"


def build_experiment_uid(record: Dict[str, Any], ch_id: Any = None) -> str:
    """Build or preserve a stable experiment UID.

    A stored UID wins.  Otherwise we only create one when the identity fields are
    available, because an empty draft should not get a misleading experiment ID.
    """
    existing = str((record or {}).get("experiment_uid") or "").strip()
    if existing:
        return existing
    user = str((record or {}).get("user") or "").strip()
    project = str((record or {}).get("project") or "").strip()
    device = str((record or {}).get("device_name") or "").strip()
    if not (user and project and device):
        return ""
    label = str((record or {}).get("channel_label") or _fallback_channel_label(ch_id)).strip()
    return "EXP_" + "_".join([
        _slug(user, fallback="user"),
        _slug(project, fallback="project"),
        _slug(device, fallback="device"),
        _slug(label, fallback="channel"),
    ])


def normalize_channel_record(
    record: Dict[str, Any],
    ch_id: Any,
    *,
    run_session_id: str = "",
    assign_experiment_uid: bool = True,
) -> Dict[str, Any]:
    item = dict(record or {})
    try:
        item["internal_ch_id"] = int(item.get("internal_ch_id", ch_id))
    except Exception:
        item["internal_ch_id"] = ch_id
    item.setdefault("channel_label", _fallback_channel_label(ch_id))
    item["channel_schema_version"] = SCHEMA_VERSION
    item["status"] = infer_channel_status(item)
    if assign_experiment_uid:
        uid = build_experiment_uid(item, ch_id)
        if uid:
            item["experiment_uid"] = uid
    if run_session_id:
        item["run_session_id"] = run_session_id
    return item


def migrate_channel_settings_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Return a schema-v2-compatible payload and whether it changed."""
    if not isinstance(payload, dict):
        payload = {}
    migrated = dict(payload)
    changed = False
    if migrated.get("__schema_version") != SCHEMA_VERSION:
        migrated["__schema_version"] = SCHEMA_VERSION
        migrated["__schema_updated_at"] = utc_now_text()
        migrated["__schema_note"] = (
            "Legacy-compatible schema v2: numeric top-level channel records remain runtime-compatible; "
            "hardware_map.json is a default template/migration reference, while channel_settings records own active relay assignments."
        )
        changed = True
    for key, value in list(migrated.items()):
        if not is_channel_key(key) or not isinstance(value, dict):
            continue
        normalized = normalize_channel_record(value, key, assign_experiment_uid=True)
        if normalized != value:
            migrated[key] = normalized
            changed = True
    return migrated, changed


def migrate_channel_settings_file(file_path: Path, *, save: bool = True) -> Tuple[Dict[str, Any], bool]:
    path = Path(file_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except Exception:
        payload = {}
    migrated, changed = migrate_channel_settings_payload(payload)
    if save and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(migrated, ensure_ascii=False, indent=4), encoding="utf-8")
    return migrated, changed


def active_channel_records(payload: Dict[str, Any]) -> List[Tuple[int, Dict[str, Any]]]:
    records: List[Tuple[int, Dict[str, Any]]] = []
    for key, value in (payload or {}).items():
        if not is_channel_key(key) or not isinstance(value, dict):
            continue
        if has_complete_relay_path(value):
            try:
                records.append((int(key), value))
            except Exception:
                continue
    return records


def build_archive_record(
    ch_id: int,
    settings: Dict[str, Any],
    *,
    final_status: str = "ended_by_user",
    data_path: str = "",
    run_session_id: str = "",
) -> Dict[str, Any]:
    now = utc_now_text()
    normalized = normalize_channel_record(settings or {}, ch_id, run_session_id=run_session_id, assign_experiment_uid=True)
    label = normalized.get("channel_label") or _fallback_channel_label(ch_id)
    archive_id = f"ARCH_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{_slug(label, fallback='CH')}"
    return {
        "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
        "archive_id": archive_id,
        "experiment_uid": normalized.get("experiment_uid", ""),
        "run_session_id": normalized.get("run_session_id") or run_session_id or "",
        "internal_ch_id": normalized.get("internal_ch_id", ch_id),
        "channel_label": label,
        "user": normalized.get("user", ""),
        "project": normalized.get("project", ""),
        "device_name": normalized.get("device_name", ""),
        "environment_instance": normalized.get("environment_instance", ""),
        "environment_recipe": normalized.get("environment_recipe", ""),
        "measurement_recipe": normalized.get("measurement_recipe", ""),
        "relay_pos": normalized.get("relay_pos"),
        "relay_neg": normalized.get("relay_neg"),
        "area": normalized.get("area"),
        "v_start": normalized.get("v_start"),
        "v_stop": normalized.get("v_stop"),
        "v_step": normalized.get("v_step"),
        "delay_time": normalized.get("delay_time"),
        "interval_min": normalized.get("interval_min"),
        "i_limit": normalized.get("i_limit"),
        "created_at": normalized.get("created_at", ""),
        "ended_at": now,
        "final_status": final_status,
        "data_path": data_path,
        "source_channel_record": normalized,
    }


def build_relay_occupancy(payload: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    occupancy: Dict[int, List[Dict[str, Any]]] = {}
    for ch_id, record in active_channel_records(payload):
        label = record.get("channel_label") or _fallback_channel_label(ch_id)
        owner = {
            "ch_id": ch_id,
            "channel_label": label,
            "user": record.get("user", ""),
            "project": record.get("project", ""),
            "device_name": record.get("device_name", ""),
            "experiment_uid": record.get("experiment_uid", ""),
        }
        for polarity, field in (("SMU+", "relay_pos"), ("SMU-", "relay_neg")):
            try:
                relay_pin = int(record.get(field))
            except Exception:
                continue
            item = dict(owner)
            item["polarity"] = polarity
            occupancy.setdefault(relay_pin, []).append(item)
    return occupancy


def validate_channel_settings_payload(payload: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    seen_labels: Dict[str, str] = {}
    relay_polarity: Dict[int, str] = {}
    for key, record in (payload or {}).items():
        if not is_channel_key(key) or not isinstance(record, dict):
            continue
        label = str(record.get("channel_label") or _fallback_channel_label(key))
        if label in seen_labels:
            warnings.append(f"duplicate channel_label={label}: {seen_labels[label]} and {key}")
        seen_labels[label] = str(key)
        for polarity, field in (("pos", "relay_pos"), ("neg", "relay_neg")):
            try:
                pin = int(record.get(field))
            except Exception:
                continue
            previous = relay_polarity.get(pin)
            if previous and previous != polarity:
                warnings.append(f"relay {pin} used as both {previous} and {polarity}")
            relay_polarity[pin] = polarity
    return warnings
