"""Validate channel_settings.json without modifying it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from core.channel_identity import migrate_channel_settings_payload, validate_channel_settings_payload


def main() -> int:
    path = config.CHANNEL_SETTINGS_FILE
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig")) if Path(path).exists() else {}
    migrated, changed = migrate_channel_settings_payload(payload)
    warnings = validate_channel_settings_payload(migrated)
    print(f"schema_update_needed={changed}")
    if warnings:
        print("Validation warnings:")
        for item in warnings:
            print(f"- {item}")
        return 2
    print("Validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
