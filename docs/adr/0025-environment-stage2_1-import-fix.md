# ADR-0025: Environment package import cleanup for Stage 2.1

## Status
Accepted

## Context
Stage 2 moved the environment-related config tabs into `gui/config_tabs/environment/`, but some import paths and startup code still referenced older locations or malformed strings.

## Decision
- Keep all environment-related config tabs under `gui/config_tabs/environment/`.
- Import `EnvironmentTab` from `.config_tabs.environment.environment_tab`.
- Construct `EnvironmentTab` with `parent=self`.
- Keep legacy `gui/config_tabs/chamber_tab.py` in place until environment migration is complete.

## Consequences
- Environment package loading is deterministic.
- Transitional legacy chamber configuration remains available.
- Old root-level environment tab files must be removed to avoid ambiguity.
