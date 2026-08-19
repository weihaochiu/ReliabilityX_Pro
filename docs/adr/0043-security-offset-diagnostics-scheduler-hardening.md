# ADR-0043 — Security, Offset Correction, Diagnostics Queuing, and Scheduler Hardening

## Status
Accepted — 2026-05-15

## Context
Recent open items identified five critical risks: real Telegram secrets in distributable config, corrected IV data not applying `offset_current`, GUI diagnostics calling worker-thread engine methods directly, scheduler state loss after restart, and lack of overload warning when requested cadence is physically unreachable.

## Decision
1. Telegram notification settings must support release-safe secret indirection using local TXT files:
   - `TELEGRAM.bot_token_file`
   - `TELEGRAM.chat_id_file`
   File values take precedence at runtime. Example config is shipped without real secrets.
2. `MeasureEngine.scan_sequence()` applies `offset_current` before corrected voltage compensation:
   - `i_corr = i_msd - offset_current`
   - `v_corr = v_msd - i_corr * r_line_ohm`
3. `ChannelSettingDialog` requests line resistance and spot-check diagnostics through queued Qt signals. Results return through engine result signals.
4. `MeasurementScheduler` persists runtime `next_due` state to `config/runtime_schedule_state.json` so cadence can continue after restart.
5. `MeasureEngine` estimates measurement load before starting and logs a scheduler overload warning when total expected active-channel measurement time exceeds the shortest configured interval.

## Consequences
- Release ZIP files no longer expose real Telegram token/chat ID.
- Corrected curves, summary, trend, and notification reports use offset-corrected current.
- Diagnostics no longer directly block/cross-call the worker-thread engine from the GUI thread.
- Per-channel cadence is more stable across restart and still uses `scheduled_due + interval` rather than delayed finish time.
- Users receive log visibility when cadence is impossible with current active channels/settings.
