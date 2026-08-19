# ADR 0038: Dynamic Logical Channel and Per-Channel Scheduler

## Status
Accepted

## Date
2026-05-14

## Context
The previous main window showed a fixed CH01-CH32 grid. This made the UI too rigid for multi-environment experiments where only a subset of relay paths are configured and where devices may share one electrode/relay. The previous scan loop also completed all active channels and then used the first channel's `interval_min` as the wait time for the entire next round.

The target behavior is:

1. Do not display a fixed 32-channel grid on the main window.
2. Let users add logical channels only when needed.
3. Display logical labels such as `CH_V01`, `CH_I01`, and `CH_C01` based on the selected environment.
4. Keep direct SMU+ / SMU- relay selection simple.
5. Restrict relay dropdown choices to the selected environment's relay ranges.
6. Allow same-polarity relay sharing but show a confirmation message such as “Relay 01 將與 Device A 共用正極”.
7. Forbid using the same relay as positive in one channel and negative in another channel.
8. Always reset all relays before opening the current channel's two relays.
9. Run each channel according to its own `interval_min` / next due time.

## Decision

1. `gui/main_window.py` now builds a dynamic card grid from configured entries in `config/channel_settings.json` instead of creating 32 fixed cards.
2. A new “＋ 新增 Channel” action opens `ChannelSettingDialog` with the next unused internal numeric channel id.
3. Internal numeric `ch_id` is retained for existing loggers, signals, and file naming compatibility.
4. `channel_label` is persisted in channel settings and generated as:
   - climate → `CH_C##`
   - indoor → `CH_I##`
   - glovebox/vacuum → `CH_V##`
5. `gui/channel_setting_dialog.py` keeps the simple relay picker workflow. It does not introduce a separate shared-bus topology model.
6. Relay sharing is derived from existing channel settings at runtime:
   - same relay + same polarity → allowed after user confirmation
   - same relay + opposite polarity → blocked
   - same relay as both SMU+ and SMU− in the same channel → blocked
7. `gui/widgets/channel_action_widget.py` now shows relay usage hints under each selector.
8. `core/measure_engine.py` now uses a per-channel due-time scheduler instead of using the first active channel interval for the whole cycle.
9. The existing channel-level relay path isolation from ADR-0018 remains authoritative: each channel measurement still performs relay reset before opening the target relay path and cleanup after measurement.

## Consequences

### Positive

- The main window reflects configured logical experiments rather than fixed hardware slots.
- Relay sharing for common electrodes becomes possible without forcing users through a complex shared-bus wizard.
- Same-polarity relay sharing remains explicit and auditable through user confirmation.
- Opposite-polarity relay conflicts are blocked before saving.
- Each channel can have its own measurement interval.
- Existing numeric `ch_id`-based loggers and signal payloads remain compatible.

### Tradeoffs

- This version still uses `ChannelSettingDialog` as the controller for relay sharing validation; a future refactor may move this logic into a model/service class.
- The diagnostic buttons in `ChannelSettingDialog` still call the worker object's synchronous methods directly. This known thread-boundary issue remains documented in `ARCHITECTURE.md` and is not changed by this ADR.
- Relay sharing is derived from channel settings and not stored as an explicit shared-bus table. This is intentional for the first simplified implementation.

## Affected Files

- `gui/main_window.py`
- `gui/channel_setting_dialog.py`
- `gui/widgets/channel_action_widget.py`
- `gui/widgets/channel_card.py`
- `core/measure_engine.py`
- `docs/ADR_INDEX.md`
- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`
- `docs/README.md`
- `docs/version_history.txt`
