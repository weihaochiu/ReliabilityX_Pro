# ADR 0051: Active-scope System Config Dashboard, Unified Environment/Station Recipes, and R-line Diagnostics

- **Status**: Accepted
- **Date**: 2026-05-17
- **Decision Owner**: ReliabilityX Pro maintainers
- **Related ADRs**: ADR-0036, ADR-0037, ADR-0038, ADR-0049, ADR-0050

## Context

ReliabilityX Pro is moving from a fixed 32-channel concept toward dynamic logical channels grouped by environment. The System Config window already had a left-navigation shell and separate Measurement Recipe / Station Recipe areas, but the previous configuration model still had several problems:

1. The Dashboard treated unused hardware and environments as potential errors, even if no active channel needed them.
2. R-line readiness could not be evaluated globally because the number of possible SMU+/SMU- relay combinations is too large and most combinations are irrelevant for the current experiment.
3. Station Recipe and Environment Recipe described overlapping experiment concepts from the user's point of view.
4. Relay occupancy was shown too coarsely as a total relay count rather than an environment- and polarity-aware view.
5. R-line calibration history needed a visual diagnostic view to reveal abnormal relay-pair resistance patterns.

## Decision

### 1. Dashboard readiness is active-channel scoped

The Dashboard must only inspect the channels that are currently enabled in `channel_settings.json`. Required environments, R-line pairs, relay occupancy, and blocking conditions are derived from those active channel cards.

Unused equipment may be displayed as informational, but it must not produce a blocking error or stop progress unless at least one active channel requires it.

### 2. R-line readiness is pair-scoped, not global-combination scoped

R-line readiness checks only include relay pairs referenced by active channel cards. The R-line status is also surfaced locally on each channel card / overview row.

A separate R-line Diagnostics page provides a broader calibrated-pair view for engineering analysis.

### 3. Station Recipe and Environment Recipe are unified

The user-facing recipe concept is now **Environment / Station Recipe**. It describes environmental setpoints, required station hardware, timeline actions, and safety limits in one schema.

Legacy hardware connection fields (`smu`, `relay`, `chamber`) are migrated into `legacy_hardware_profile` for traceability. Active hardware connection settings remain under Hardware Connection / Relay Mapping pages.

### 4. Relay allocation is environment-aware and polarity-aware

Relay / Channel Mapping owns environment relay ranges. Each environment has a positive and negative relay segment. The GUI must display a 3x2 summary:

- rows: environment groups
- columns: SMU+ used/free and SMU- used/free

Environment range configuration is stored in `config/environment_profiles.json`.

### 5. R-line diagnostics include an environment-filtered 3D map

The R-line diagnostics page plots:

- X-axis: SMU+ relay number
- Y-axis: SMU- relay number
- Z-axis: R-line resistance in ohms

The view is dynamically filtered by environment and can be limited to active channel pairs. Outlier detection compares each point against the local environment median.

### 6. Measurement recipe family is represented by recipe name

No extra WBG/NBG/tandem type enum is introduced. Cell family is represented in the recipe name. Built-in recipes are created for:

- Normal Bandgap Perovskite - Standard IV
- WBG Perovskite - Standard IV
- NBG Perovskite - Standard IV
- Perovskite-Si Tandem - Standard IV

Recipes support edit and duplicate workflows so users can quickly create area- or device-specific variants.

## Consequences

### Benefits

- Dashboard readiness now matches the actual measurement task and avoids false errors from unused equipment.
- Relay availability is easier to understand because it is split by environment and SMU polarity.
- R-line calibration becomes more diagnosable through a 3D pair map and outlier indicators.
- The Station/Environment recipe UX becomes simpler and better aligned with real experiment setup.
- Existing environment manager compatibility is preserved by syncing unified station recipes to `environment_control_recipes.json`.

### Trade-offs

- System Config now has more derived views and needs stronger refresh logic after saving channel, relay, or calibration files.
- The 3D R-line plot requires optional Matplotlib support; if unavailable, table diagnostics remain available.
- Existing legacy station recipe records are retained, but maintainers should avoid adding new hardware connection fields to Environment / Station Recipe.

## Implementation Notes

Affected modules:

- `config.py`
- `gui/system_config_dialog.py`
- `gui/config_tabs/recipe_tab.py`
- `gui/config_tabs/station_recipe_tab.py`
- `gui/config_tabs/relay_tab.py`
- `gui/config_tabs/personnel_tab.py`
- `gui/config_tabs/rline_diagnostics_tab.py`
- `config/measurement_recipes.json`
- `config/station_recipes.json`
- `config/environment_control_recipes.json`
- `config/environment_profiles.json`
- `config/personnel_tab.json`

## Validation

- Python syntax validation was executed with `py_compile` across all project `.py` files.
- GUI behavior and hardware behavior still require manual validation on the target Windows workstation with SMU, relay board, and any environment controllers connected.
