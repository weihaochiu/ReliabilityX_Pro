# ADR 0047: Hardware reconnect safety, R-line traceability, overload visibility, and trend performance hardening

- **Status:** Accepted
- **Date:** 2026-05-15
- **Scope:** `config.py`, `config/config_settings.json`, `gui/config_tabs/measurement_tab.py`, `gui/channel_setting_dialog.py`, `gui/widgets/channel_action_widget.py`, `gui/main_window.py`, `core/measure_engine.py`, `core/hardware/hardware_manager.py`, `core/IV_parameter_analysis_utils.py`, `core/summary_logger.py`, `core/iv_curve_logger.py`, `gui/trend_chart_window.py`, `docs/OPEN_ITEMS.md`

## Context

The current ReliabilityX Pro codebase already includes per-channel scheduling, drift-free conflict handling, shutdown management, and explicit SMU read-error handling. The next highest-risk backlog items were:

1. Relay reconnect could reset all relay paths during an active measurement.
2. Invalid numeric values could still become scientific zeroes in analysis/display paths.
3. R-line calibration needed traceable history, a configurable expiry window, and a save/start safeguard when a selected relay pair had never been calibrated.
4. Scheduler overload was logged but not visible before starting a run, and overload context was not consistently carried into data outputs.
5. Trend chart data and render paths could grow or redraw without practical bounds during long reliability experiments.

## Decision

Implement a targeted hardening patch without introducing a large state-machine rewrite:

- Add `CALIBRATION_SETTINGS.RLINE_MAX_AGE_DAYS` and `TREND_CHART` runtime settings to `config/config_settings.json` and helper accessors in `config.py`.
- Add an R-line max-age control to the measurement/system configuration page. The default is 30 days, but operators can set 60 days or another laboratory policy value.
- Evaluate R-line calibration records through a shared config helper. Channel setting save and global measurement start now hard-block relay pairs that have never been calibrated; expired calibration produces a red warning and requires explicit confirmation.
- Append every R-line measurement to `data/rline_history.csv` with timestamp, operator/user, project, device, channel label, environment, relay pins, source current, measured voltage/current, resistance, request ID, status, and note.
- Propagate R-line age / expiry / max-age metadata into IV curve and summary outputs.
- Add active-measurement relay reconnect context. Idle reconnect may reset relays; reconnect during active measurement is treated as unsafe and causes the current scan path to stop rather than silently resetting all relays.
- Move invalid numeric handling in IV analysis toward `np.nan`/invalid state instead of physical zeroes for insufficient or malformed data. This is a phase-1 policy; centralized invalid numeric logging remains a follow-up.
- Add a scheduler overload confirmation dialog before global start. Flexible catch-up remains the default policy; strict skip/manual policy is not included in this patch.
- Limit trend-chart in-memory history using configurable max points and debounce redraws with a `QTimer`. Maintain a per-series ordered cache so each redraw does not re-filter/re-sort the full history.

## Consequences

- R-line compensation is more traceable and safer: users cannot accidentally save/start an active channel whose selected SMU+/SMU- path has never been calibrated.
- The R-line reminder window is no longer hard-coded to 30 days and can match lab SOPs such as 60 days.
- Relay reconnect during active scans no longer silently changes the physical circuit and continues writing data.
- Overloaded schedules are visible to operators before start and are traceable in output metadata.
- Trend charts should remain more responsive during long experiments because GUI cache and repaint cadence are bounded.
- Analysis outputs may now contain `NaN` for invalid/insufficient calculations where earlier code returned zero. Downstream views must treat `NaN` as invalid data, not as a real measurement.

## Follow-up

- OI-036 remains partially open for centralized invalid numeric logging and consistent UI representation of `NaN` / invalid values.
- OI-033 remains partially open for strict skip/manual overload policy.
- If future work implements relay path restore after reconnect, it must prove the physical relay state was restored before any further SMU readings and must log data-validity decisions.
- Trend historical lazy loading/downsampling can be added later if the bounded in-memory cache is insufficient for very long campaigns.
