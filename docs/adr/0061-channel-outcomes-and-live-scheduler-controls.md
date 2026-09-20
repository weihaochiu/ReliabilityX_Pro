# ADR 0061: Explicit channel outcomes and live scheduler controls

- Status: Accepted
- Date: 2026-09-20
- Related: ADR-0042, ADR-0048, ADR-0052, ADR-0059; OI-017, OI-050, OI-051

## Context

The operator needs to start all selected channels once, let independent intervals
run automatically, and pause/resume individual channels during the same session.
Previously checkbox changes only affected the next global start. The synchronous
worker scan loop also prevents ordinary queued Qt slots from receiving stop/toggle
commands until the loop exits. Failures could be counted as completed and cards
used obsolete metric keys.

## Decision

1. `measure_single_channel` returns `ChannelOutcome`. Only completed measurement,
   persistence and cleanup increment the successful attempt count or emit a result.
   Classifications include `blocked_config`, `blocked_calibration`, `failed_read`,
   `relay_failure`, `failed_analysis`, `failed_logger`, and `cleanup_failure`.
   Immediate abort continues to raise `MeasurementInterrupted` after cleanup.
2. A failed attempt stops the global scan before another channel is selected.
   The failed schedule item is not advanced or marked one-shot complete. Finish
   signals, error logs and runtime schedule state carry the failure classification.
   No automatic retry follows a failure; operator review and a new start are required.
3. Cross-thread requests use `SimpleQueue`, with copied settings. GUI-side enqueue
   methods perform no hardware IO or scheduler mutation. Only the worker consumes
   requests at channel boundaries or idle waits. The stop signal uses a direct
   connection exclusively to the enqueue method, never a hardware-facing slot.
4. Checkbox toggles are confirmed, saved asynchronously, then enqueued on successful
   persistence. A dedicated single-thread save pool serializes writes. Failed saves
   roll back checkbox intent; they do not enqueue the failed changes.
5. Pausing the current channel finishes both sweep directions and cleanup. Pausing
   a waiting channel removes it before its turn. All-paused sessions remain alive
   with bounded waits. Resume/new participation becomes due at the next boundary;
   paused time creates no backlog. Subsequent cadence remains scheduled_due + interval.
   This supersedes OI-017's previous next-global-start-only behavior.
6. While the global scheduler is stopped, checkboxes only select the next start.
   Opening the app never starts a scan automatically. `interval_min=0` remains
   one-shot; positive intervals repeat independently on one shared SMU/relay path.
7. Channel cards resolve one coherent forward Voc/PCE pair in the central schema:
   valid corrected pair, then valid raw pair, then legacy aliases only for a legacy
   payload. Missing/non-finite/invalid values display no-data, not zero. Genuine
   finite zero is preserved. A later completion status must not erase the metrics.

## Consequences and limits

- Initial and runtime-joined channels use the same basic parameter validation;
  engine R-line validation remains authoritative immediately before path selection.
- A summary-write failure can leave the already-written IV file. A cleanup failure
  can occur after both files exist. Existing files are preserved, but the attempt is
  failed and no successful result is emitted.
- Driver cleanup calls and mock assertions do not prove physical relay state or
  electrical isolation. Laboratory acceptance remains a separate machine test.
- Existing notification/plot consumers retain the canonical result payload and
  CSV formats. `completed_channel_count` counts successful attempts, including
  repeated cycles; it is not the number of distinct devices.
- Offline tests cover failure injection, multi-channel file separation, virtual
  clock cadence, pause/resume/join, full Qt window/worker operation and save failure.
