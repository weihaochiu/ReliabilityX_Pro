# ADR 0049: Channel Identity, Cross-Restart Trend History, Relay Occupancy, and Active-Scope Telegram PDF Foundation

## Status
Accepted

## Date
2026-05-16

## Context
ReliabilityX Pro had already moved to dynamic logical channels and per-channel scheduling, but several downstream workflows still relied on unstable combinations of user/project/device/channel labels. This made cross-restart trend stitching, channel archive/restore, Telegram report grouping, and relay occupancy diagnostics difficult to maintain.

The user also clarified that raw logs are valuable for debugging, but should not be mixed into source patch exports because logs and private JSON can contain local paths, project/device names, runtime state, and Telegram secrets.

## Decision
1. Add `core/channel_identity.py` as the canonical helper for channel schema migration, stable `experiment_uid`, per-run `run_session_id`, archive record creation, relay occupancy derivation, and channel settings validation.
2. Preserve the legacy-compatible top-level numeric `channel_settings.json` layout, but add `__schema_version=2` and per-channel `channel_schema_version`, `internal_ch_id`, `status`, and `experiment_uid`.
3. Define active relay assignment source-of-truth as `channel_settings.json`; `hardware_map.json` remains a default template and legacy migration reference only.
4. Persist `experiment_uid` and `run_session_id` into IV curve metadata, Summary rows, channel archive records, Trend series keys, and Telegram trend report history.
5. Extend Trend Chart to load historical `Summary_report.csv` records for active-scope experiments so degradation history can continue across app stops/restarts.
6. Extend Relay Tab to show active relay occupancy derived from channel settings alongside the legacy/default hardware map template.
7. Extend Telegram trend dispatch to prefer active-scope grouped PDF reports when `trend_pdf_enabled=true`, falling back to PNG/text when PDF rendering fails.
8. Track a new diagnostic bundle export open item for future sanitized log/config sharing.

## Consequences
- Existing GUI/runtime code remains compatible because channel settings stay in the top-level numeric dictionary format.
- Downstream features can now use `experiment_uid` instead of guessing by folder path or display name.
- Trend Chart can stitch active experiment data across app restarts when Summary CSV records are available.
- Relay Tab now separates template mapping from active occupancy, reducing the risk of treating stale `hardware_map.json` as active source-of-truth.
- Archive records are more traceable, but a full restore UI remains a future task.
- Diagnostic bundle export is intentionally deferred; source patch export should still exclude raw logs/private configs.

## Validation
- Python syntax check should pass for modified runtime modules.
- `tools/migrate_channel_settings.py` and `tools/validate_channel_settings.py` provide schema migration/validation entry points.
- Hardware and GUI behavior still require real-device validation.
