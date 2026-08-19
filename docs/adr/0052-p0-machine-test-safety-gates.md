# ADR 0052: P0 Machine-Test Safety Gates for Relay All-Off and R-line Traceability

- **Status**: Accepted
- **Date**: 2026-06-02
- **Decision Owner**: ReliabilityX Pro maintainers
- **Related ADRs**: ADR-0018, ADR-0043, ADR-0047, ADR-0051

## Context

Before machine testing, four P0 risks were identified:

1. `RelayDriver.reset_all()` used a generic `reset` command whose exact physical relay all-off behavior was not sufficiently explicit for emergency stop, startup, and cold-switching safety.
2. `config/channel_settings.json` contained an enabled draft channel with incomplete metadata, IV parameters, and relay pair.
3. R-line records older than the configured reminder threshold could still be used after operator confirmation, and legacy R-line values without timestamps were not treated as hard blockers.
4. Runtime relay settings in `config_settings.json` were not guaranteed to be the same values used by the relay driver.

## Decision

### 1. Relay all-off must use an explicit vector command

`RelayDriver.reset_all()` must turn all physical relay channels off using Numato's vector command:

```text
relay writeall 0000000000000000
```

For a 64-channel relay board, the all-off payload is 16 hexadecimal zeros. If the vector command does not receive a valid prompt response, the driver falls back to sending `relay off NN` for each physical relay channel. The fallback does not issue the ambiguous `reset` command.

### 2. Enabled draft channels are not allowed for machine testing

Any channel with `is_enabled=true` but incomplete user/project/device, IV parameters, or relay pair must be disabled before machine testing. The operator must intentionally configure and enable a complete channel card.

### 3. Expired or non-traceable R-line is a hard stop

R-line records are valid only when they contain a numeric value and a parseable timestamp that is not older than the configured maximum age. Missing records, expired records, and legacy values without timestamps block startup in the GUI and are also blocked again in `MeasureEngine` before relay switching.

### 4. Relay runtime config is single-source

`config.RELAY_CONFIG` is merged from `config/config_settings.json` with safe defaults. `RelayDriver` reads PORT, BAUDRATE, SAFE_MODE, IDENTIFIER, and TOTAL_CHANNELS from this runtime config by default.

## Consequences

- Operators must remeasure line resistance for the actual relay pair before machine testing if the previous value is older than the global threshold or lacks a timestamp.
- A stale R-line value cannot be overridden by clicking through a warning dialog.
- Emergency / startup relay all-off is auditable and no longer depends on the undefined behavior of `reset`.
- The Relay config page and driver use the same connection settings.
