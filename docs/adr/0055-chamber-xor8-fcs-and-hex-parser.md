# ADR 0055: Chamber XOR8 FCS and Signal 01 HEX Parser

- **Status**: Accepted
- **Date**: 2026-06-02

## Context

During RS-485 chamber bring-up, the diagnostic terminal showed that legacy `sum8_include_at` generated `@010102*` and received no response. The chamber responded to `xor8_include_at`, specifically `@010140*`, with a Signal `01` analog-data frame:

```text
@01010A9127100A917FFF000019380000010------------------------------0000000006021A0F2A3772*
```

The previous parser treated Signal `01` analog fields as 6-digit decimal strings and attempted to convert substrings such as `0A9127` using `float()`, causing parse failures. The vendor manual shows fixed-position analog data fields, and field data confirms the first values are 4-character hexadecimal words.

## Decision

`driver.chamber_driver.ChamberDriver` shall use `xor8_include_at` as the default and first diagnostic FCS mode for the chamber. Signal `01` telemetry shall be parsed as fixed-width 4-character hexadecimal words:

- temperature PV: signed 16-bit hex / 100
- humidity PV: unsigned 16-bit hex / 100
- temperature SV: signed 16-bit hex / 100
- humidity SV: unsigned 16-bit hex / 100

Sentinel fields such as `7FFF`, `FFFF`, or dash-filled fields are treated as unavailable (`None`) instead of numeric telemetry.

## Consequences

- Startup and connection testing no longer wait on the known-wrong SUM8 frame before probing the confirmed XOR8 mode.
- The diagnostic response above parses to Temp PV = 27.05 °C, RH PV = 100.00%, Temp SV = 27.05 °C, and RH SV = unavailable.
- UI code can safely render unavailable SV fields as `--.-` while preserving PV telemetry readiness.
- Other FCS modes remain available for manual diagnostics, but production telemetry uses XOR8 including `@`.

## Validation

- Offline parser test with the field response confirmed XOR8 FCS validation and fixed-width HEX parsing.
- `driver/chamber_driver.py` passed `py_compile`.
