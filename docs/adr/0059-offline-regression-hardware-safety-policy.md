# ADR 0059: Offline Scientific Regression and Hardware Safety Test Policy

- **Status:** Accepted
- **Date:** 2026-08-19
- **Scope:** `tests/`, `pytest.ini`, `core/IV_parameter_analysis_utils.py`, scientific/config/logger/measurement contracts

## Context

ReliabilityX Pro previously had no collected pytest suite. Syntax checks could not prove IV parameter stability, calibration order, logger/schema consistency, relay cold-switching order, or exception cleanup. Running ad-hoc tests against production drivers also creates unacceptable laboratory risk because constructors and helpers can enumerate VISA/serial resources or operate physical outputs.

## Decision

1. All automated tests are offline and mock-only. Production orchestration is tested by dependency injection of `MockSMU`, `MockRelay`, and `MockEnvironment` objects that record calls, arguments, timestamps/order, configured limits, and output/relay state.
2. `tests/conftest.py` is a global safety gate. During pytest it rejects VISA resource managers, serial ports, outbound sockets, production SMU output ON, and production relay scan/switch/reset entrypoints.
3. Scientific expected values come from analytical equations or explicit hand-calculated fixtures. Tests never call the production function to generate their expected result.
4. The current reporting contract remains Voc(V), Isc/Impp(mA), Jsc/Jmpp(mA/cm²), FF/PCE(%), Rs(Ω), Rsh(kΩ), and Pmpp(W). Floating-point assertions use justified tolerances.
5. Offset and line-resistance correction order is locked to ADR-0043: `I_corrected = I_measured - offset_current`, followed by `V_corrected = V_measured - I_corrected * R_line`.
6. Data/config/backup writes in tests use `tmp_path`; repository `config/`, `data/`, `logs/`, `_local_only/`, and `BACKUP/` are not test output targets.
7. Hardware safety integration tests assert relay switching happens only while SMU output is off and all modeled exception paths converge on SMU OFF and relay reset cleanup.

## Consequences

- `python -m pytest -q` is now a meaningful pre-commit regression gate instead of “no tests collected.”
- A future test that accidentally reaches a real connection path fails immediately.
- Mock success proves software ordering and contracts, not physical instrument behavior; operator-reviewed machine tests remain separate.
- The first regression run exposed a validity-metadata bug where boolean `valid_*` flags were converted to numeric `0.0/1.0`; the unit standardization layer now preserves them as booleans without changing IV numeric formulas.

## Follow-up

- GUI offscreen smoke testing and an optional application runtime mock mode remain tracked under OI-008.
- Existing failure-completion and stale GUI metric-alias discrepancies remain tracked as open items rather than being hidden by tests.
