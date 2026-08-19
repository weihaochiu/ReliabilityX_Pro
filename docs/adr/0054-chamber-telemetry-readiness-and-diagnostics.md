# ADR-0054 Chamber telemetry readiness and diagnostics

## Status
Accepted - 2026-06-02

## Context
During on-machine setup, the Windows device manager showed the chamber USB-RS485 converter as `CMS/ITRI USB to RS485 (COM8)`.  The chamber manual specifies RS-232C/RS-485, 9600 bps, half-duplex, even parity, 8 data bits, 1 stop bit, TX termination CR+LF, RX termination CR, and Signal `01` for analog PV/SV data.  The previous GUI reported success when the serial COM port opened, even when temperature and humidity PV remained `ERR`.

## Decision
Chamber readiness is now defined as successful Signal `01` telemetry parsing, not merely serial-port-open.  The driver exposes full TX/RX ASCII and HEX diagnostics and can probe several FCS calculation modes for field debugging until the vendor FCS algorithm page is confirmed.

## Consequences
- Main-window chamber status now means `Telemetry OK` only after PV/SV readback succeeds.
- Hardware Connection / Chamber test displays failure when COM opens but the chamber does not return parsable telemetry.
- Debug terminal output is suitable for diagnosing station ID, RS485 A/B wiring, remote communication enablement, and FCS mismatch.
- Formal production operation should lock the FCS mode to the vendor-confirmed algorithm after the FCS manual page is supplied.
