# ADR-0039: Environment-grouped channel list and end-channel flow

## Status
Accepted

## Context

After ADR-0038 introduced dynamic logical channels, two follow-up issues were found:

1. Legacy channel entries could have a `channel_label` such as `CH_C01` but no valid `environment_instance`. In that case, the main card could derive a climate-channel label while the detail dialog defaulted to the first environment option, making the card and setting dialog inconsistent.
2. Once users can add logical channels dynamically, they also need a safe way to end an experiment and remove the channel from the active main-window list so the relay path is available for the next experiment.
3. Channels from different environment families should not be visually mixed in one flat row. Users need separate Vacuum / Indoor / Climate Chamber groups.

## Decision

The system now keeps channel environment display and detail editing aligned by using the same inference priority:

1. valid saved `environment_instance`
2. `channel_label` prefix (`CH_C`, `CH_I`, `CH_V`)
3. configured relay ranges from `EnvironmentManager`
4. current dropdown fallback only when no other evidence exists

`MainWindow` displays dynamic channel cards grouped by environment family and environment instance. Cards no longer appear as one mixed CH_V / CH_I / CH_C grid.

Each `ChannelCard` now provides a `結束實驗 / 移除` action. `MainWindow` confirms the action, removes the channel entry from `config/channel_settings.json`, and writes the removed channel's final configuration to `config/archived_channel_settings.json`. Scientific data files are not deleted by this action.

## Consequences

- The main card title, grouping, and detail dialog environment selection use consistent environment inference.
- Ending an experiment removes the logical channel from active use and effectively releases its relay path for future dynamic channel creation.
- Existing experiment data remains on disk and can still be used for traceability.
- The action is intentionally not a hard data-delete operation; it deletes the active logical channel configuration only.

## Affected modules

- `gui/main_window.py`
- `gui/channel_setting_dialog.py`
- `gui/widgets/channel_card.py`
- `docs/ADR_INDEX.md`
- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`
- `docs/README.md`
- `docs/version_history.txt`
