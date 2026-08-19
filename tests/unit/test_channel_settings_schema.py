"""Regression tests for the public channel-settings schema contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.channel_identity import migrate_channel_settings_payload, validate_channel_settings_payload


@pytest.mark.offline
def test_empty_clone_channel_example_is_valid(repository_root: Path) -> None:
    """The tracked example is a valid empty schema-v2 bootstrap payload."""
    payload = json.loads((repository_root / "config" / "channel_settings.example.json").read_text(encoding="utf-8"))
    migrated, changed = migrate_channel_settings_payload(payload)
    assert migrated["__schema_version"] == 2
    assert validate_channel_settings_payload(migrated) == []
    assert changed is False


@pytest.mark.offline
def test_legacy_channel_is_normalized_with_stable_identity() -> None:
    """A legacy numeric record receives current identity and status fields."""
    payload = {
        "1": {
            "is_enabled": True,
            "user": "operator",
            "project": "project",
            "device_name": "device",
            "relay_pos": 1,
            "relay_neg": 2,
        }
    }
    migrated, changed = migrate_channel_settings_payload(payload)
    channel = migrated["1"]
    assert changed is True
    assert migrated["__schema_version"] == 2
    assert channel["internal_ch_id"] == 1
    assert channel["channel_schema_version"] == 2
    assert channel["experiment_uid"]
    assert channel["status"] == "active"


@pytest.mark.offline
def test_duplicate_logical_labels_and_cross_polarity_relays_are_rejected() -> None:
    """Schema validation detects identity and relay-polarity conflicts."""
    payload = {
        "1": {"is_enabled": True, "channel_label": "CH_C01", "relay_pos": 1, "relay_neg": 2},
        "2": {"is_enabled": True, "channel_label": "CH_C01", "relay_pos": 2, "relay_neg": 3},
    }
    errors = validate_channel_settings_payload(payload)
    assert any("duplicate channel_label" in error for error in errors)
    assert any("used as both" in error for error in errors)
