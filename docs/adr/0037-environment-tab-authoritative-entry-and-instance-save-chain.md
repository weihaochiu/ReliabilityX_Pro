# 0037 - Environment Tab Authoritative Entry and Instance Save Chain

## Status
Accepted

## Date
2026-04-03

## Context
The project introduced a shared `Environment Recipe` editor entry from
`SystemConfigDialog`, while the repository simultaneously contained:
- `gui/config_tabs/environment_tab.py`
- `gui/config_tabs/environment_tab/environment_tab_main.py`

This made the authoritative `EnvironmentTab` entry ambiguous and caused
runtime mismatch risk for the signal contract expected by
`SystemConfigDialog`.

In addition, the Climate / Glovebox / Indoor tabs attempted to persist
instance relay assignments and default environment recipes through
`EnvironmentManager.update_instance(instance_id, payload)`, but the core
manager did not yet implement this API. As a result, opening the dialog could
be fixed, but saving still failed with an `AttributeError`.

## Decision
1. Use `gui/config_tabs/environment_tab/environment_tab_main.py` as the single
   authoritative `EnvironmentTab` entry point.
2. Update `SystemConfigDialog` to import `EnvironmentTab` explicitly from the
   stable package path.
3. Keep shared recipe-editor routing via
   `open_environment_recipe_requested(str)` on the parent Environment tab.
4. Add `EnvironmentManager.update_instance(instance_id, payload)` in the core
   layer so all environment sub-tabs persist through the same model API.
5. Keep JSON file I/O in `core/environment_manager.py` to preserve MVC
   boundaries and avoid moving persistence logic into Qt widgets.

## Consequences
### Positive
- `SystemConfigDialog` no longer depends on an ambiguous import path.
- Saving Environment settings now has a complete chain from GUI widgets to
  JSON persistence.
- Relay assignment and default environment recipe changes are written back to
  `config/environment_profiles.json` by the model layer.

### Trade-offs
- Existing tabs now depend on the newly formalized `update_instance()` API.
- `SystemConfigDialog` still uses `uic.loadUi()` in the current phase; this was
  left unchanged to avoid broader UI regression in this bugfix batch.

## Related files
- `gui/system_config_dialog.py`
- `gui/config_tabs/environment_tab/environment_tab_main.py`
- `gui/config_tabs/environment_tab/climate_chamber_tab.py`
- `gui/config_tabs/environment_tab/vacuum_glovebox_tab.py`
- `gui/config_tabs/environment_tab/indoor_environment_tab.py`
- `core/environment_manager.py`
