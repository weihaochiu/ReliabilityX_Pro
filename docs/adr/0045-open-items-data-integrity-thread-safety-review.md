# ADR 0045: Record deep data-integrity, thread-safety, and performance review items as detailed open items

## Status

Accepted

## Date

2026-05-15

## Context

A follow-up code review of the current ReliabilityX Pro codebase identified several deeper technical risks that were not runtime-fixed in this documentation-only pass. The review focused on scientific data integrity, silent failures, memory/performance behavior, thread safety, GUI responsiveness, and hardware recovery behavior.

The verified concerns include:

- `SMUDriver.read_vi()` and the VISA decorator returning synthetic numeric zeroes on read/communication failures.
- `SummaryLogger.update_summary_report()` relying on `locals()` and an undefined `data_dict` fallback.
- Numeric parsing and analysis fallbacks that can blur invalid data versus true physical zeroes.
- `TrendChartWindow` retaining unbounded in-memory history and re-sorting/filtering full history on every update.
- Main-window synchronous config writes and checkbox rollback signal feedback risk.
- `IVCurveLogger` lacking a write lock for future concurrent writer scenarios.
- Relay reconnect behavior that can reset all relay paths while a measurement may be active.
- SMU VISA backend initialization lacking a controlled operator-facing failure path.

## Decision

Record these verified risks as detailed open items in `docs/OPEN_ITEMS.md` rather than applying runtime code changes in this pass.

New open items added:

- OI-034 — SMU read errors must not return synthetic `(0.0, 0.0)` data.
- OI-035 — Remove `locals()` / undefined `data_dict` hack in SummaryLogger metadata.
- OI-036 — Invalid numeric parsing should not be silently coerced into scientific zeroes.
- OI-037 — Trend chart `all_data_history` has unbounded in-memory growth.
- OI-038 — Main-thread config file writes can freeze the GUI.
- OI-039 — Trend chart update path performs high-cost O(N) filter/sort on every new point.
- OI-040 — IVCurveLogger lacks a file-write lock.
- OI-041 — Checkbox rollback can trigger a recursive signal feedback loop.
- OI-042 — Relay reconnect must not unconditionally `reset_all()` during active measurement.
- OI-043 — SMU PyVISA backend initialization should fail explicitly with actionable guidance.

## Consequences

- Future runtime fixes can be performed in smaller, safer batches with clear acceptance criteria.
- The project backlog now preserves the evidence, risk, affected area, proposed fix, and validation criteria for each item.
- P0 scientific data-integrity items should be prioritized before UI-only enhancements.

## Files Updated

- `docs/OPEN_ITEMS.md`
- `AI_INSTRUCTIONS.md`
- `docs/adr/0041-open-items-tracking-process.md`
- `docs/adr/0045-open-items-data-integrity-thread-safety-review.md`
- `docs/ADR_INDEX.md`
- `docs/version_history.txt`
