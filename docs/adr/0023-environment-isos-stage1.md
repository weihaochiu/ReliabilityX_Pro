# ADR-0023: Introduce Stage-1 Environment & ISOS Foundation

- Date: 2026-04-02
- Status: Accepted
- Decision Owner: ReliabilityX Pro architecture discussion

## Context

The existing system was designed primarily around a single chamber-like environment model. Recent planning requires:
- Multiple physical environments under one measurement system
- Per-environment channel range ownership
- Separation between measurement recipe and environment control recipe
- A future path toward ISOS-derived custom protocols such as `ISOS-LVac-*`

## Decision

Stage 1 introduces:
1. Three fixed environment GUI sub-tabs
2. Dedicated environment config schemas
3. A top-level `EnvironmentManager`
4. Validation rules for channel/relay range ownership
5. Runtime lock state support

## Consequences

### Positive
- Creates a stable foundation before touching measurement core
- Prevents channel-range overlap
- Makes later `channel_setting_dialog.py` refactor safer
- Keeps Climate / Glovebox / Indoor maintenance separated

### Negative
- Adds new configuration files that must be kept in sync
- Requires later integration work in GUI and scheduler
- Does not yet perform hardware control or data collection

## Follow-up
- Stage 2: bind channel settings to environment instances
- Stage 3: add main window environment summary and scheduler
- Stage 4: integrate loggers and runtime services
