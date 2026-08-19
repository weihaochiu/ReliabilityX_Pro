# ADR 0042: Drift-free scheduler conflict handling and logging

## Status
Accepted

## Context

ReliabilityX Pro uses one SMU and one relay path, so two devices that become due at the same time cannot be measured physically in parallel.  The previous per-channel scheduler serialized due channels, but the next due time was advanced from the actual finish time.  This caused long-term cadence drift: for example, if Device B was due at 09:00 but measured at 09:01 because Device A was first in the queue, the old behavior could schedule Device B's next run at 09:16 instead of the scientifically intended 09:15.

For long-duration reliability tests, the planned cadence is part of the experiment.  Queue delay must be recorded, but it must not redefine the cadence.

## Decision

Add `core/measurement_scheduler.py` as the scheduler boundary and keep `core/measure_engine.py` as the Qt-facing measurement orchestration facade.

The scheduler now follows these rules:

1. One SMU/relay resource means only one channel is measured at a time.
2. If multiple channels are due simultaneously or already overdue, they are serialized.
3. The queue order is deterministic: scheduled due time, priority, interval, then creation order.
4. The next due time is calculated as:

```text
next_due = scheduled_due_time_that_was_served + interval_min
```

It is not calculated from the actual finish time.

Example:

```text
Device A interval = 10 min
Device B interval = 15 min
Both due at 09:00

09:00 Device A starts first
09:01 Device B starts after queue delay

Next Device A due = 09:10
Next Device B due = 09:15
```

The queue delay is not discarded.  It is written to:

- system log through `LogManager`
- IV curve CSV metadata
- Summary report scheduler columns

## Consequences

### Positive

- Long-term cadence no longer drifts because of temporary queue delays.
- Schedule conflicts are visible in logs and scientific output files.
- Trend and downstream analysis can distinguish planned sampling time from actual sampling time.
- `MeasureEngine` is less responsible for time-ordering details; scheduler state is isolated in `core/measurement_scheduler.py`.

### Trade-offs

- If measurement duration is longer than interval, the channel may immediately remain due after completion.  This is intentional because the experiment is overloaded; future work should add overload warnings or skip policies.
- Existing Summary_report files keep their old headers.  New files created after this ADR include the additional scheduler columns.

## Updated data fields

The following metadata fields are emitted for each measurement:

- `scheduled_time`
- `actual_start_time`
- `actual_end_time`
- `schedule_delay_sec`
- `queue_position`
- `conflict_flag`
- `conflict_group_size`
- `conflict_peer_labels`
- `next_due_time_basis = scheduled_due_plus_interval`
