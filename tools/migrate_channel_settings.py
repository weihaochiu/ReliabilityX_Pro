"""Migrate channel_settings.json to the legacy-compatible schema v2."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from core.channel_identity import migrate_channel_settings_file, validate_channel_settings_payload


def main() -> int:
    payload, changed = migrate_channel_settings_file(config.CHANNEL_SETTINGS_FILE, save=True)
    warnings = validate_channel_settings_payload(payload)
    print(f"channel_settings migration changed={changed}")
    if warnings:
        print("Validation warnings:")
        for item in warnings:
            print(f"- {item}")
        return 2
    print("Validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
