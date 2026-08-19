# ADR 0048: Data Validity, Unit Schema, Scheduler Policy, Debounced Saves, and Release Cleanup

## Status

Accepted

## Date

2026-05-15

## Context

ReliabilityX Pro is evolving into a long-running scientific measurement platform. Several remaining open items affected scientific traceability and operational robustness:

- Invalid numeric values could still be handled inconsistently across analysis, loggers, and trend rendering.
- IV/Summary/Trend labels and units were defined in multiple modules, creating risk of drift between scientific outputs.
- Channel checkbox changes were saved synchronously on the GUI thread and had unclear semantics while the scheduler was already running.
- Scheduler overload handling warned users but did not yet support a strict skip policy with auditable summary metadata.
- Release and patch packages could still include local-only/runtime artifacts such as personal paths, logs, cache, or stale manifest files.

## Decision

Implement the following shared policy and module boundaries.

1. **Central numeric parsing policy**
   - Add `core/numeric_utils.py`.
   - Invalid values become `NaN` or `None`, not scientific zero.
   - Valid physical zero remains accepted.
   - Callers may request warning logs with field/context information.

2. **Central measurement schema**
   - Add `core/measurement_schema.py`.
   - Summary-scale units are centralized as: `Voc(V)`, `Isc(mA)`, `Jsc(mA/cm²)`, `FF(%)`, `PCE(%)`, `Rs(Ω)`, `Rsh(kΩ)`, `Pmpp(W)`, `Vmpp(V)`, `Impp(mA)`, `Jmpp(mA/cm²)`, plus `Hysteresis Index`.
   - Summary logger, IV curve analysis matrix, trend spec, trend chart, trend snapshot renderer, and IV analysis widget read labels/keys from this schema instead of redefining them.

3. **Debounced async settings save**
   - Add `gui/settings_save_controller.py`.
   - Channel enable/disable changes update an in-memory pending settings payload immediately and are persisted through a QTimer-debounced background write.
   - Save failure rolls back the UI through `ChannelCard.set_checked()` and logs/displays the error.

4. **Measurement-running checkbox policy**
   - If the global scheduler is running, channel checkbox changes are allowed to be saved for the next scheduler start only.
   - The active worker scheduler queue is not modified live by the GUI checkbox path.
   - Any future live scheduler updates must be implemented through a state-machine/queued-signal design.

5. **Scheduler strict skip policy**
   - Add global scheduler policy settings under `SCHEDULER_POLICY`: `MODE` and `MAX_ALLOWED_DELAY_SEC`.
   - `flexible_catch_up` keeps measuring overdue channels and records delay metadata.
   - `strict_skip` skips overdue occurrences when delay exceeds the configured threshold, records `Scheduler_Skip_Reason`, and advances `next_due` from scheduled due + interval to preserve scientific cadence.

6. **Release cleanup**
   - Sanitize personal runtime settings.
   - Add `config/user_settings.example.json`.
   - Update `.gitignore` and `build_and_deploy.py` to exclude runtime/local-only artifacts such as logs, data, pycache, local settings, notification secrets, runtime schedule state, and `CHANGESET_MANIFEST.md`.

## Consequences

### Positive

- Invalid strings, blanks, `None`, `NaN`, and `inf` are no longer silently plotted or summarized as scientific zeroes.
- Scientific labels and units are less likely to drift between CSV outputs, trend charts, and widgets.
- Checkbox interactions become less likely to freeze the GUI on slow/cloud-synced disks.
- Scheduler skip behavior is auditable in Summary/log outputs.
- Patch/release outputs are safer to share and more reproducible.

### Trade-offs

- Trend charts and summary outputs may show blanks/omitted points for invalid values where older versions would show `0.0`; this is intentional to prevent data pollution.
- Running-scheduler checkbox changes are not live updates. Operators must stop/start the global scheduler for changes to take effect.
- Strict skip policy may intentionally create missing measurement occurrences when cadence is no longer scientifically reliable.

## Validation

- Python syntax compile was executed for modified Python files.
- Lightweight non-GUI checks verified numeric parsing, legacy metric label mapping, scheduler strict skip cadence advancement, and Summary logger scheduler columns.
- Hardware SMU/Relay/Chamber tests were not executed in this patch.

## Related Open Items

- OI-014 — Release manifest/cache cleanup
- OI-017 — Running-scheduler checkbox policy
- OI-020 — IV/Summary/Trend unit schema
- OI-030 — `user_settings.json` release isolation
- OI-032 — Logs/data/cache package exclusion
- OI-033 — Scheduler strict skip / catch-up policy
- OI-036 — Invalid numeric parsing policy
- OI-038 — Debounced config saves
