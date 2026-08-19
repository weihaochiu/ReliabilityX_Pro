# ADR-0057 - Chamber manual spinbox edits must not compete with synchronous telemetry polling

Date: 2026-06-02

## Context
Rapidly clicking the target temperature/humidity spin-box arrows in System Configuration could make the dialog appear unresponsive while chamber telemetry polling was also performing synchronous RS-485 transactions.

## Decision
Manual setpoint spin boxes are treated as local command inputs. Their valueChanged events pause chamber polling for a short debounce window. ChamberDriver serial transactions are protected by a non-blocking IO lock, so concurrent main-window polling, settings-tab polling, and diagnostics cannot interleave on the same USB-RS485 port.

## Consequences
The operator can safely adjust target values without the GUI freezing. PV/SV readback labels may pause briefly during editing and resume automatically after edits settle. Setpoints are sent only when the operator presses the send/apply button.
