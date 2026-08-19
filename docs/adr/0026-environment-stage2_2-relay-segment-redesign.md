# ADR 0026: Environment mapping redesign to relay segments

## Status
Accepted

## Context
The previous Stage-2 design let each channel manually select an environment instance.  
After UI review, this was considered too complicated and too easy to misconfigure.

## Decision
The system now defines:

- Environment = determined by assigned `SMU+ / SMU- relay segments`
- Channels do not directly choose the environment anymore
- `channel_setting_dialog.py` infers environment metadata from `Relay Pos`

Additionally:

- `Climate Chamber` first embeds the existing `chamber_tab.py`
- Legacy `chamber_tab.py` remains transitional and must not be deleted yet

## Consequences
### Positive
- Simpler operator workflow
- Lower risk of environment / relay mismatch
- Better alignment with physical wiring structure

### Trade-offs
- Transition period keeps a legacy chamber widget alive inside the new environment tab
- Collector / control service split remains for later stages
