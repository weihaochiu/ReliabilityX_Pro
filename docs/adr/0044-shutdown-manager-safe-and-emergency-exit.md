# ADR 0044: ShutdownManager for Safe Process Shutdown and Emergency Exit

## Status
Accepted

## Date
2026-05-15

## Context
ReliabilityX Pro controls physical SMU, relay, and chamber hardware.  The main
window previously connected the control-panel exit button directly to
`MainWindow.close()` and `closeEvent()` directly executed a best-effort stop and
hardware shutdown.  This made the shutdown behavior hard to audit and increased
`gui/main_window.py` responsibility.

The operator needs two explicit exit modes:

1. **Safe process shutdown**: stop the scheduler, wait for the current channel to
   reach the existing graceful stop boundary, force SMU output OFF, reset all
   relays, save runtime schedule state through the engine, flush logs, close
   worker thread, and exit.
2. **Emergency shutdown and exit**: immediately abort, force SMU output OFF,
   reset all relays, close hardware handles, log a critical shutdown event, and
   exit even if the current data point/curve may be incomplete.

## Decision
Introduce `core/shutdown_manager.py` as the single coordinator for application
exit.  `MainWindow` remains responsible for displaying the control-panel button
and invoking the manager, but no longer owns the detailed shutdown sequence.

The control-panel exit button is renamed to **🛑 安全關閉程式**.  Pressing it opens
a confirmation dialog with three choices:

- `✅ 安全流程關閉`
- `⚠️ 緊急停止並關閉`
- `取消`

`MainWindow.closeEvent()` now refuses to close the process directly unless the
shutdown manager has already completed a valid shutdown path.  Clicking the OS
window close button therefore uses the same confirmation flow instead of
bypassing hardware safety.

`MeasureEngine` now exposes:

- `force_safe_hardware_state(close_connections=False)`
- `emergency_shutdown()`
- `shutdown_hardware()` backed by the same safe-state routine

The safe-state order is always:

1. SMU output OFF
2. Relay reset_all
3. Optional hardware connection close
4. Hardware status update

## Consequences
- `gui/main_window.py` becomes less responsible for hardware-exit details.
- Shutdown behavior is easier to test and audit from log messages prefixed with
  `[SHUTDOWN]`.
- Safe shutdown may cancel application close if the current measurement does not
  reach a safe boundary within `config.SAFE_SHUTDOWN_WAIT_SEC`; the operator can
  then explicitly choose emergency shutdown.
- Emergency shutdown is intentionally allowed to produce incomplete current
  measurement data; this is logged as `EMERGENCY_SHUTDOWN_AND_EXIT`.

## Modified Files
- `core/shutdown_manager.py`
- `core/measure_engine.py`
- `gui/main_window.py`
- `gui/widgets/control_panel.py`
- `config.py`
- `docs/OPEN_ITEMS.md`
- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`
- `docs/README.md`
- `docs/version_history.txt`
