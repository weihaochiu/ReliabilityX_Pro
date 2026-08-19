# ADR 0032: Climate Chamber Widget Decomposition

## Status
Accepted

## Context
The previous Climate Chamber implementation embedded the old `chamber_tab.py`
as a monolithic legacy block. This caused layout coupling and made future
maintenance risky.

The user requested:
1. Parent `environment_tab.py` + child tabs grouped under `gui/config_tabs/environment_tab/`
2. Climate-specific widgets grouped under
   `gui/config_tabs/environment_tab/climate_chamber_widgets/`
3. `chamber_tab.py` decomposed into reusable parts

## Decision
1. Create a new package layout under `gui/config_tabs/environment_tab/`
2. Decompose the old climate chamber UI into:
   - ChamberConnectionWidget
   - ChamberStatusWidget
   - ChamberControlWidget
   - ChamberDebugWidget
3. Rebuild `ClimateChamberTab` by composing those widgets
4. Keep indoor and glovebox tabs in the same package, but do not over-expand
   them yet

## Consequences
- Better separation of responsibilities
- No more legacy giant widget embedding
- Easier future maintenance and safer incremental changes
