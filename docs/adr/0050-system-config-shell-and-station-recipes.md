# ADR 0050: SystemConfigDialog Shell and Station Recipe Separation

## Status
Accepted

## Context

`SystemConfigDialog` had grown into a single top-level tab widget containing users/projects, SMU, relay, chamber, measurement safety, measurement recipes, environment pages, environment recipes, and notifications.  The UI was difficult to scan, and adding more items such as Station Recipes, bilingual labels, email report scheduling, supervisor CC, relay occupancy, and chamber telemetry would make the same-level tab model increasingly fragile.

Measurement recipes and hardware/station recipes also represent different scientific provenance layers.  A measurement recipe defines how an IV curve is acquired.  A station recipe defines the hardware and environment station used to acquire it.  Keeping both in one list would make it difficult to determine whether a data difference came from IV scan parameters or from station hardware/environment configuration.

## Decision

The system configuration dialog is refactored into a shell/controller layout:

- Left navigation list for major settings areas.
- Right `QStackedWidget` content area.
- Dashboard landing page for status summary and quick jumps.
- Existing config tabs embedded inside the shell for Phase 1 compatibility.
- Advanced Settings page with collapsed-by-default panels.
- Measurement Recipes and Station Recipes are separate pages and separate JSON-backed data models.

A new `gui/config_tabs/station_recipe_tab.py` manages station / hardware recipes.  A new `config/station_recipes.json` is introduced and accessed through `config.load_station_recipes()` and `config.save_station_recipes()`.

## Consequences

### Positive

- Global settings no longer rely on a crowded same-level tab bar as the primary navigation mechanism.
- Operators see a dashboard summary before editing low-level hardware settings.
- Measurement recipes and station recipes become traceable separately.
- Future user email report scheduling, supervisor CC, i18n, relay occupancy, and environment-control expansion can be added without overcrowding the main settings shell.
- `SystemConfigDialog` no longer uses `uic.loadUi()` directly, reducing one PyInstaller risk point for this dialog.

### Trade-offs

- Existing embedded config tab widgets still use their legacy implementation internally.  This is intentional for Phase 1 to avoid a large regression surface.
- Relay connection and relay/channel mapping still live in the existing `RelayTab`; future phases can split them into smaller widgets if needed.
- Station recipes are persisted and editable but not yet consumed by the measurement runtime.  Runtime application should be implemented in a later open item.

## Follow-up Work

- OI-046: replace hard-coded UI strings with formal i18n/bilingual helpers.
- OI-047: implement email PDF report scheduling and supervisor CC.
- Future: apply selected Station Recipe to hardware connection defaults and runtime report metadata.
- Future: split legacy config tabs away from `uic.loadUi()` and into smaller pure-Python widgets.
