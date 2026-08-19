# ADR 0045: Code Review Risk Open Items for Scheduler, MeasureEngine, and Runtime Robustness

## Status

Accepted

## Date

2026-05-15

## Context

A code review of `ReliabilityX Pro_202605151025.zip` identified several confirmed risks and optimization opportunities in the current runtime implementation:

- Scheduler datetime parsing can silently fall back to `started_at` when persisted runtime timestamps cannot be parsed. The specific millisecond ISO example is supported by Python `datetime.fromisoformat()`, but non-standard or manually edited timestamps remain a risk.
- `_probe_smu_connected()` closes the SMU session on probe exception, which can be too destructive for transient communication glitches.
- `_interruptible_sleep()` uses a `time.sleep()` polling loop inside a QObject-based worker context, which may delay queued-signal handling.
- Scheduler priority parsing does not currently normalize numeric priority values.
- `MeasureEngine` remains large and still combines orchestration, hardware probing, scan execution, diagnostics, and safe-state handling.
- Channel scheduling and measurement code still passes free-form dictionaries instead of typed validated channel configuration objects.
- `main.py` loads QSS by a working-directory-relative path.
- Long-term reliability operation would benefit from bounded hardware retry, advanced sweep modes, adaptive scheduling, and chamber/environment settled-state gating.

## Decision

Track these findings as formal open items OI-034 through OI-044 in `docs/OPEN_ITEMS.md`. These items are not implemented in this change; they are recorded so future modifications can be prioritized and verified against clear acceptance criteria.

## Consequences

- The backlog now distinguishes confirmed bugs/risks from broader feature proposals.
- Future code changes should prioritize OI-035 and OI-036 before further expanding diagnostics or hardware recovery behavior.
- The scheduler, hardware lifecycle, scan execution, and environment gate improvements should be implemented incrementally to avoid destabilizing the existing measurement flow.

## Related Open Items

- OI-034 — Harden scheduler datetime parsing and avoid silent schedule reset
- OI-035 — Avoid force-closing SMU during transient probe errors
- OI-036 — Replace blocking sleep loop with Qt-friendly interrupt / timer pattern
- OI-037 — Normalize scheduler priority schema for string and numeric values
- OI-038 — Continue MeasureEngine refactor into HardwareCoordinator and ScanExecutor
- OI-039 — Introduce typed ChannelConfig instead of free-form dicts
- OI-040 — Make QSS asset loading robust for shortcut / different working directory launches
- OI-041 — Add bounded hardware retry / auto-recovery during scan
- OI-042 — Add advanced sweep modes for reliability experiments
- OI-043 — Adaptive scheduling / auto-disable abnormal channels
- OI-044 — Gate IV measurement on chamber/environment settled state
