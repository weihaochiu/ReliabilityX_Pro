# ADR-0056: Chamber Manual Setpoint Inputs Must Not Be Overwritten by Telemetry Polling

## Status
Accepted

## Context

After enabling RS-485 Chamber telemetry, Signal 01 readback can return PV and SV
values every polling interval.  The previous UI copied readback SV values into the
manual target temperature and humidity spin boxes.  On this chamber, temperature
SV can equal or track the current process temperature and humidity SV may be
reported as an unused sentinel (`7FFF`, represented as `None`).  Rewriting the
manual command fields during polling made the target setpoint appear to change
without operator intent.

## Decision

PV/SV telemetry polling updates readback labels only.  Manual target temperature
and humidity spin boxes are operator-owned command inputs.  They are not mutated
by periodic status reads or test-connection refreshes.  Missing humidity SV is
rendered as `--.- %` in readback labels and must not be forced into the manual
input as `0.0%`.

## Consequences

- Operators can type a target temperature/humidity and verify it remains stable
  until they press `傳送設定`.
- Readback status remains visible in the status monitor area.
- Future "copy current SV to input" behavior, if needed, must be implemented as
  an explicit user action rather than automatic polling side effect.
