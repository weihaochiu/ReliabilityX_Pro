# ADR 0046: SMU read failures must be explicit and startup resource loading must be path-safe

- **Status:** Accepted
- **Date:** 2026-05-15
- **Scope:** `driver/smu_driver.py`, `core/measure_engine.py`, `core/summary_logger.py`, `core/iv_curve_logger.py`, `main.py`, `docs/OPEN_ITEMS.md`

## Context

The latest code review identified several small but high-value fixes that reduce data-integrity and deployment risk without changing the overall measurement architecture:

1. `SMUDriver.read_vi()` and the `@visa_command` wrapper could return synthetic `(0.0, 0.0)` values when the SMU response was empty, malformed, or affected by VISA communication errors.
2. `SummaryLogger.update_summary_report()` contained a `locals()` / undefined `data_dict` fallback in the offset-current metadata path.
3. `IVCurveLogger.save_iv_curve()` did not guard file writes with a lock.
4. `main.py` loaded `assets/style.qss` by relative path, which can fail when launched from a shortcut, different working directory, or packaged EXE.
5. SMU VISA backend initialization had no controlled, user-facing failure path if both the default VISA backend and `@py` backend failed.
6. Checkbox rollback safety had already been implemented through `ChannelCard.set_checked()` and needed to be verified/marked done in `OPEN_ITEMS.md`.

## Decision

Implement a targeted hardening patch:

- Add explicit SMU driver exception classes: `SMUDriverError`, `VisaBackendUnavailableError`, `HardwareCommunicationError`, `HardwareReadError`, and `HardwareParseError`.
- Change `SMUDriver.read_vi()` so invalid/empty/malformed `:READ?` responses raise explicit exceptions instead of returning fake zero voltage/current data.
- Keep non-`read_vi` helper calls backward-compatible where practical, but ensure `read_vi` cannot silently fabricate scientific data.
- Update `MeasureEngine.scan_sequence()` to catch/log `HardwareReadError` at the voltage step, abort the affected channel path, and avoid writing synthetic points.
- Ensure `measure_single_channel()` turns SMU output off during channel cleanup before relay cleanup.
- Replace the `SummaryLogger` `locals()` / undefined `data_dict` expression with a direct lookup on `results`.
- Add a `threading.Lock()` to `IVCurveLogger` and wrap the full CSV write block.
- Load QSS with `config.get_resource_path("assets/style.qss")`.
- Fail SMU VISA backend initialization with a controlled `VisaBackendUnavailableError`, then show a Qt critical dialog and write a log message in `main.py`.
- Mark verified checkbox rollback handling as done because `ChannelCard.set_checked()` blocks `chk_enabled` signals during programmatic rollback.

## Consequences

- A valid physical 0.0 V / 0.0 A measurement remains possible only when the instrument successfully returns those values.
- Hardware read failures now stop the affected scan path rather than contaminating IV CSV, Summary, Trend, or notification data with fabricated zeroes.
- Operators on PCs without a working VISA backend receive an actionable error instead of an ambiguous traceback.
- IV curve file writing becomes safer for future multi-SMU or async logging work.
- Existing CSV output format is preserved.

## Follow-up

The broader invalid numeric policy remains tracked separately as OI-036. Relay reconnect active-path policy, trend chart memory bounding, trend chart throttling, and async config-save behavior remain separate open items.
