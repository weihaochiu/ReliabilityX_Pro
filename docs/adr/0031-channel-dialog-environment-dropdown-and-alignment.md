# ADR 0031: Channel Dialog Environment Dropdown and Alignment

## Status
Accepted

## Context
The user required two focused fixes inside `channel_setting_dialog.py`:
1. The environment block must be split into its own widget and must include
   both an environment dropdown and an environment-recipe dropdown.
2. All field start positions across the dialog must align from top to bottom.

## Decision
1. Create `ChannelEnvironmentWidget` as the dedicated environment widget.
2. Move environment selection out of `ChannelActionWidget`.
3. Standardize the label-column width across:
   - ChannelInfoWidget
   - ChannelParamWidget
   - ChannelEnvironmentWidget
   - ChannelActionWidget
4. Keep environment recipe filtering in the controller layer and core manager.

## Consequences
- Better separation of responsibilities
- Clearer alignment and more consistent UI
- Easier future maintenance for environment-related channel settings
