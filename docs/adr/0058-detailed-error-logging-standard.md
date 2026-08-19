# ADR 0058: Detailed Error Logging Standard for Hardware and Persistence Failures

- **Status**: Accepted
- **Date**: 2026-06-03
- **Context**: ReliabilityX Pro is used as a hardware-connected scientific measurement system.  A GUI message such as "傳送設定值失敗" is not sufficient for machine testing because it does not reveal whether the failure came from timeout, FCS/checksum mismatch, parser error, rejected command, serial busy state, incorrect station ID, or a safety interlock.

## Decision

All hardware communication, file IO, parser, scheduler, and GUI-triggered hardware actions must write detailed persistent diagnostics when they fail.  User-facing dialogs may remain concise, but the log must preserve the evidence needed for post-run diagnosis.

Required diagnostic fields, when applicable:

1. Operation name and module/function.
2. Hardware identity and parameters: COM/VISA address, baudrate, station ID, relay channel, serial format, FCS/checksum mode.
3. Outgoing command: TX ASCII, TX HEX, SCPI command, relay command, or payload summary.
4. Incoming response: RX ASCII, RX HEX, raw response, timeout state.
5. Validation and parser results: FCS/checksum pass/fail, parsed fields, invalid/None sentinel fields.
6. Exception type and traceback.
7. Safety action and state assumption, such as "no setpoint change is assumed" or "SMU output OFF attempted".

## Consequences

- Drivers should not silently return `False` without logging reason and context.
- GUI pages should show concise messages and point operators to the log instead of hiding diagnostic details.
- New features must include both success-path and failure-path logging in their acceptance criteria.
- Chamber setpoint writes now log full RS-485 transaction context when the command fails.

## Affected files

- `AI_INSTRUCTIONS.md`
- `driver/chamber_driver.py`
- `gui/config_tabs/chamber_tab.py`
- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`
- `docs/README.md`
- `docs/version_history.txt`
