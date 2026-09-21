# ADR 0062: Qualified R-line and mandatory illuminated-solar-cell polarity checks

- Status: Accepted
- Date: 2026-09-21
- Related: ADR-0043, ADR-0047, ADR-0058, ADR-0061; OI-054, OI-055, OI-056

## Context

The operator measured approximately 149 ohms with isolated clips on physical
relays 3 and 57. The engine divided measured voltage by the requested 10 mA,
so 1.499 V with only 5 nA could falsely qualify. Relay writes accepted an ERROR
response containing an echo or prompt, and calibration success preceded cleanup.
The operator confirmed an illuminated photovoltaic device and explicitly requested
a mandatory polarity check before every formal forward/reverse attempt.

## Decision

1. Keep GUI hardware requests queued to the active MeasureEngine worker. Reject
   reentrant diagnostics. No hardware is accessed by automated tests.
2. R-line uses 10 mA / 1.5 V only after verified output OFF, all-off, pair selection,
   full relay-mask readback and strict SMU mode/level/limit readback. Reject unknown
   or active voltage compliance, nonfinite samples, |V| >= 99% of the limit, and
   measured signed I outside +10 mA +/-1%. Calculate |V_measured/I_measured| in
   IV_parameter_analysis_utils, never divide by the requested current.
3. Return a successful calibration only after verified output OFF and relay
   all-off. The GUI checks JSON save success before history/success notification.
   Save validation_version=2 plus measured V/I, setpoint, limit and compliance.
   Preserve legacy records on disk but block their use until remeasured. Recheck
   v2 numeric evidence and stored resistance consistency when reading calibration.
4. Relay acknowledgements require an exact echo and terminating prompt with no
   unexpected payload. Full readall must contain a complete hexadecimal mask;
   for 64 channels physical decimal IDs are 0..63 (3/57 -> 0200000000000008).
   Reset and connection readiness require all-zero readback. This proves only
   controller-reported state, NOT mechanical contact isolation or cable topology.
5. Strict SMU methods propagate IO failures and log TX/RX. They do not use the
   legacy decorator that can swallow write errors. Current-source compliance uses
   :SENS:VOLT:PROT:TRIP?; voltage-source compliance uses :SENS:CURR:PROT:TRIP?.
   Source mode, fixed mode, level, limit and output state queries must agree.
6. Before every formal channel attempt, at its already verified pair, source
   0 V with min(channel I limit, global I maximum, 0.1 A) compliance; settle 0.1 s.
   Require finite readings, no current compliance, |V_measured| <= 10 mV and
   offset-corrected I < -10 uA. I > +10 uA means reversed; near zero means
   open/dark/weak signal, not a proven wiring diagnosis. Other failures are unknown.
   Any non-normal result aborts this attempt and the global queue, without sweeps.
   Manual spot-check and formal precheck use the same central classifier.
7. Formal sweeps verify source settings, output and each step, check current
   compliance at every point, and preserve measured voltage separately from
   setpoint. Raw analysis, plotting and curve CSV prefer measured voltage, with
   v_src fallback only for historical point payloads. Correction remains signed:
   I_corr=I_measured-offset; V_corr=V_measured-I_corr*R_line. Unit conversion and
   scientific calculations remain centralized. Sweep generation never exceeds
   V_stop, including when the step does not divide the span exactly.
8. Preserve continuous output across forward-to-reverse transition; turn output
   OFF after reverse before analysis/file IO and again during mandatory cleanup.
   Remove the scheduler's final READ? after output OFF. A cleanup failure is
   reported, not silently treated as a successful electrical state.
9. Disable the inactive DiagnosticsService legacy R-line method rather than leave
   an alternate callable implementation that returns a false zero. Phase-1
   scaffold integration is not part of this change.
10. Catch System Configuration page-validation errors before any settings writes;
    show the conflicting relay/environment names and keep the dialog editable.
    Do not silently remap environment relay ownership.

## Consequences and limits

- All existing pre-v2 R-line calibrations require remeasurement, not deletion.
- +/-1%, 99%, 10 uA and 10 mV are conservative application guardrails, NOT vendor
  accuracy claims. Low-light/small-current devices and cells exceeding the 0.1 A
  precheck cap can be blocked. Changing this policy needs operator review.
- Readback adds per-point communication time; scheduler cadence remains anchored
  to scheduled_due+interval, not finish time. Actual acquisition is slower.
- Curves already saved before a later cleanup failure may remain on disk, as in
  ADR-0061. They are not counted as a successful channel outcome; inspect logs.
- This patch does not prove why the physical circuit was open/shorted. Lab
  acceptance and the actual firmware's readback response format remain OI-056.
- No new dependencies/assets or PyInstaller data flags. Existing build script
  includes changed Python modules through normal imports.

## References and validation

- Local GSM-20H10 User Manual REV B (2023-06-09): printed pages 246-253 for source
  modes/levels, 309-310 for voltage/current compliance queries.
- Numato 64 Channel USB Relay user guide: decimal relay IDs and readall mask:
  https://docs.numato.com/docs/64-channel-usb-relay-module-user-guide/
- Offline tests cover open 149/0 ohm regressions, actual-current formula, legacy
  rejection, protocol errors, masks, strict SCPI, persistence, cleanup, mandatory
  polarity, formal compliance, raw voltage consumers and existing scheduler GUI.
