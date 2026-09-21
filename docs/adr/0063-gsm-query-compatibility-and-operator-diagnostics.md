# ADR 0063: GSM source queries and evidence-based operator diagnostics

- Status: Accepted
- Date: 2026-09-21
- Related: ADR-0058, ADR-0062; OI-056, OI-057

## Evidence

The supplied station log (15:38-15:41) repeatedly shows Relay commands `on 03` and
`on 57`, followed by mask `0200000000000008`. The SMU accepts source/fixed-mode
queries, but `:SOUR:CURR:LEV?` times out. There is no output ON or READ? before
cleanup; OFF returns 0 and Relay readall returns all zero. Clip continuity cannot
influence this pre-output query. Controller bits cannot prove mechanical contacts.

The GSM-20H10 REV B manual, printed pages 252-253 (PDF 254-255), explicitly lists
`:SOURce:CURRent?` and `:SOURce:VOLTage?` as programmed-amplitude queries.
The previous mock tests accepted the optional-LEVel spellings and did not model
this observed firmware difference. Passing offline tests was not device acceptance.

## Decision

1. Use `:SOUR:CURR?` for current setup and `:SOUR:VOLT?` for every voltage-level
   verification, including polarity and formal IV sweeps. Keep writes, limits,
   finite-value checks, readback comparisons and output interlocks intact. Do not
   increase timeouts, skip verification or retry alternative queries after timeout.
   Actual firmware acceptance of the documented spelling still requires a station test.
2. Preserve structured command, response and stable error code on SMU communication
   exceptions. Report the actual default VISA backend implementation, not a guessed
   NI-VISA label when pyvisa-py is active.
3. Centralize operator wording in framework-free `core/diagnostic_messages.py`.
   Numeric R-line qualification raises typed ValueError subclasses with stable
   categories; do not classify translated exception strings using loose keywords.
4. The engine records attempted stages, controller-pair confirmation, whether ON
   was sent/confirmed, whether V/I was acquired, samples, and separate final OFF /
   all-off confirmations. A failure report is constructed after cleanup. Unknown
   or failed cleanup must never appear as a confirmed safe state.
5. Keep existing queued diagnostic requests/results. Add request-correlated
   diagnostic_progress to the active R-line button; stage text means attempted
   work, not completed hardware action. Ignore stale or unrelated request IDs.
6. `gui/diagnostic_dialog.py` renders a plain Chinese title, failed stage, explanation,
   progress/safety evidence, next actions and expandable technical details with copy.
   GUI does no additional hardware probing to compose a failure message.
7. Integrate reports into channel R-line/spot-check/save failures, SMU dashboard read
   exceptions, Relay reset failures and Chamber connection failures. Chamber port-open
   failure must not claim the port was opened. Do not automatically switch COM1 to
   the observed USB-RS485 COM8 or change station ID. Relay reset False cannot clear
   UI buttons or trigger a success message.

## Validation and limits

- Strict memory-only protocol emulator rejects both legacy source-LEVel query
  spellings, accepts documented forms, and executes actual driver/engine methods.
  Open and short fixtures both reach ON/READ; only short qualifies. Injected query
  failures still block ON and preserve exact command and cleanup facts.
- Qt tests cover Chinese text, details toggle/copy, stale progress, Relay false
  success and Chamber false-open claims. Dark-QSS offscreen preview visually checked
  with a locally loaded Windows CJK font (preview-only; no new runtime asset).
- Physical contacts, relay external supply, DUT continuity and new query acceptance
  remain OI-056. No automatic hardware or network tests are introduced.
- Existing synchronous hardware operations in settings tabs are not migrated to
  a new worker in this patch. No new hardware call is added for explanations;
  channel R-line and polarity diagnostics remain queued. SMU manual read is blocked
  while engine measurement is active.
- No new dependencies, UI resources or build flags. Normal imports collect the two
  new Python modules. Existing calibration guards and v2 records remain unchanged.
