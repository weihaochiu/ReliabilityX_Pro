"""Per-channel measurement scheduler for ReliabilityX Pro.

This module owns time-due ordering and conflict metadata.  The measurement
engine remains the Qt-facing orchestration facade, while this scheduler keeps
the scientific cadence stable: the next scheduled time is always calculated
from the previous scheduled due time, not from the delayed actual finish time.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ChannelScheduleItem:
    """Runtime scheduling state for one logical channel."""

    order: int
    channel: Dict[str, Any]
    next_due: _dt.datetime
    interval_min: float
    active: bool = True
    paused: bool = False
    last_scheduled_time: Optional[_dt.datetime] = None
    last_actual_start_time: Optional[_dt.datetime] = None
    last_actual_end_time: Optional[_dt.datetime] = None
    delay_sec: float = 0.0
    conflict_flag: bool = False
    conflict_group_size: int = 1
    queue_position: int = 1
    conflict_peer_labels: List[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def ch_id(self) -> Any:
        return self.channel.get("ch_id")

    @property
    def label(self) -> str:
        raw_id = self.channel.get("ch_id")
        try:
            fallback = f"CH{int(raw_id):02d}"
        except Exception:
            fallback = f"CH{raw_id}"
        return self.channel.get("channel_label") or fallback

    @property
    def device_name(self) -> str:
        return self.channel.get("device_name") or "Device"

    def mark_started(
        self,
        actual_start: _dt.datetime,
        *,
        conflict_group_size: int = 1,
        queue_position: int = 1,
        conflict_peer_labels: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Record start metadata for the current scheduled measurement."""
        self.last_scheduled_time = self.next_due
        self.last_actual_start_time = actual_start
        self.last_actual_end_time = None
        self.delay_sec = max(0.0, (actual_start - self.next_due).total_seconds())
        self.conflict_group_size = max(1, int(conflict_group_size or 1))
        self.queue_position = max(1, int(queue_position or 1))
        self.conflict_flag = self.conflict_group_size > 1 or self.delay_sec > 1.0
        self.skipped = False
        self.skip_reason = ""
        peers = list(conflict_peer_labels or [])
        self.conflict_peer_labels = [label for label in peers if label and label != self.label]
        return self.current_metadata()

    def mark_skipped(
        self,
        actual_time: _dt.datetime,
        *,
        reason: str,
        conflict_group_size: int = 1,
        queue_position: int = 1,
        conflict_peer_labels: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Record a skipped scheduled occurrence and advance cadence anchor."""
        metadata = self.mark_started(
            actual_time,
            conflict_group_size=conflict_group_size,
            queue_position=queue_position,
            conflict_peer_labels=conflict_peer_labels,
        )
        self.skipped = True
        self.skip_reason = reason
        self.last_actual_end_time = actual_time
        metadata = self.current_metadata()
        metadata["scheduler_skip_reason"] = reason
        self.mark_completed(actual_time)
        return metadata

    def mark_completed(self, actual_end: _dt.datetime) -> None:
        """Advance schedule after one measurement.

        Important scientific cadence rule:
        - next_due is calculated from the *scheduled* due time that was just
          served, not from actual_end.  Therefore a delayed queue does not drift
          future Device A / Device B cadence.
        - interval <= 0 means one-shot measurement and deactivates this item.
        """
        self.last_actual_end_time = actual_end
        if self.interval_min > 0:
            base_due = self.last_scheduled_time or self.next_due
            self.next_due = base_due + _dt.timedelta(minutes=self.interval_min)
        else:
            self.active = False

    def current_metadata(self) -> Dict[str, Any]:
        scheduled = self.last_scheduled_time or self.next_due
        return {
            "scheduled_time": scheduled,
            "actual_start_time": self.last_actual_start_time,
            "actual_end_time": self.last_actual_end_time,
            "schedule_delay_sec": self.delay_sec,
            "queue_position": self.queue_position,
            "conflict_flag": self.conflict_flag,
            "conflict_group_size": self.conflict_group_size,
            "conflict_peer_labels": ";".join(self.conflict_peer_labels),
            "next_due_time_basis": "scheduled_due_plus_interval",
            "scheduler_skip_reason": self.skip_reason if self.skipped else "",
        }


class MeasurementScheduler:
    """Single-resource per-channel scheduler.

    It assumes one SMU/relay measurement resource, so simultaneous due channels
    are serialized.  Future due times remain anchored to planned cadence.
    """

    def __init__(
        self,
        active_channels_data: Iterable[Dict[str, Any]],
        now: Optional[_dt.datetime] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        scheduler_policy: Optional[Dict[str, Any]] = None,
    ):
        self.started_at = now or _dt.datetime.now()
        self.scheduler_policy = self._normalize_policy(scheduler_policy)
        self.items: List[ChannelScheduleItem] = []
        state_items = {}
        if isinstance(previous_state, dict):
            for item in previous_state.get("items", []) or []:
                if isinstance(item, dict):
                    key = self._state_key(item.get("ch_id"), item.get("channel_label"))
                    state_items[key] = item

        for order, ch_data in enumerate(active_channels_data or []):
            interval_min = self.safe_interval_minutes(ch_data)
            key = self._state_key(ch_data.get("ch_id"), ch_data.get("channel_label"))
            previous = state_items.get(key, {})
            next_due = self._parse_dt(previous.get("next_due")) or self.started_at
            # If interval changed, keep persisted cadence anchor but update future interval.
            self.items.append(
                ChannelScheduleItem(
                    order=order,
                    channel=ch_data,
                    next_due=next_due,
                    interval_min=interval_min,
                    active=True,
                )
            )

    @staticmethod
    def _normalize_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        policy = policy or {}
        mode = str(policy.get("mode", policy.get("MODE", "flexible_catch_up")) or "flexible_catch_up").strip().lower()
        if mode not in {"flexible_catch_up", "strict_skip"}:
            mode = "flexible_catch_up"
        try:
            max_delay = int(float(policy.get("max_allowed_delay_sec", policy.get("MAX_ALLOWED_DELAY_SEC", 300))))
        except (TypeError, ValueError):
            max_delay = 300
        return {"mode": mode, "max_allowed_delay_sec": max(0, max_delay)}

    @property
    def policy_mode(self) -> str:
        return self.scheduler_policy["mode"]

    @property
    def max_allowed_delay_sec(self) -> int:
        return self.scheduler_policy["max_allowed_delay_sec"]

    def should_skip_due_item(self, item: ChannelScheduleItem, now: Optional[_dt.datetime] = None) -> bool:
        if self.policy_mode != "strict_skip":
            return False
        now = now or _dt.datetime.now()
        delay_sec = max(0.0, (now - item.next_due).total_seconds())
        return delay_sec > float(self.max_allowed_delay_sec)

    @staticmethod
    def _state_key(ch_id: Any, channel_label: Any = None) -> str:
        if ch_id not in (None, ""):
            return f"id:{ch_id}"
        return f"label:{channel_label or ''}"

    @staticmethod
    def _parse_dt(value: Any) -> Optional[_dt.datetime]:
        if isinstance(value, _dt.datetime):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return _dt.datetime.fromisoformat(text)
        except Exception:
            try:
                return _dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

    @staticmethod
    def _dt_to_text(value: Optional[_dt.datetime]) -> str:
        if isinstance(value, _dt.datetime):
            return value.isoformat(timespec="seconds")
        return ""

    @staticmethod
    def safe_interval_minutes(ch_data: Dict[str, Any]) -> float:
        try:
            value = ch_data.get("interval_min", 0)
            if value in (None, ""):
                return 0.0
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    def has_active(self) -> bool:
        return any(item.active for item in self.items)

    def set_channel_enabled(self, channel: Dict[str, Any], enabled: bool, now: _dt.datetime) -> None:
        """Apply an operator toggle at a safe channel boundary.

        Args:
            channel: Channel snapshot; used when joining/resuming.
            enabled: Whether to measure this channel.
            now: Resume anchor. Paused time does not create catch-up scans.
        """
        item = next((entry for entry in self.items if entry.ch_id == channel["ch_id"]), None)
        if item is None:
            if enabled:
                self.items.append(ChannelScheduleItem(
                    order=len(self.items), channel=dict(channel), next_due=now,
                    interval_min=self.safe_interval_minutes(channel),
                ))
            return
        if enabled and not item.active:
            item.channel = dict(channel)
            item.interval_min = self.safe_interval_minutes(channel)
            item.next_due = now
        item.active = enabled
        item.paused = not enabled

    def next_sleep_seconds(self, now: Optional[_dt.datetime] = None) -> Optional[float]:
        active_items = [item for item in self.items if item.active]
        if not active_items:
            return None
        now = now or _dt.datetime.now()
        next_due = min(item.next_due for item in active_items)
        return max(0.0, (next_due - now).total_seconds())

    def due_items(self, now: Optional[_dt.datetime] = None) -> List[ChannelScheduleItem]:
        now = now or _dt.datetime.now()
        due = [item for item in self.items if item.active and item.next_due <= now]
        due.sort(key=lambda item: (item.next_due, -self._priority_value(item.channel), item.interval_min, item.order))
        return due

    def to_state_dict(self, *, status: str = "running") -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "status": status,
            "saved_at": self._dt_to_text(_dt.datetime.now()),
            "started_at": self._dt_to_text(self.started_at),
            "next_due_time_basis": "scheduled_due_plus_interval",
            "scheduler_policy": dict(self.scheduler_policy),
            "items": [
                {
                    "ch_id": item.ch_id,
                    "channel_label": item.label,
                    "device_name": item.device_name,
                    "interval_min": item.interval_min,
                    "active": item.active,
                    "paused": item.paused,
                    "next_due": self._dt_to_text(item.next_due),
                    "last_scheduled_time": self._dt_to_text(item.last_scheduled_time),
                    "last_actual_start_time": self._dt_to_text(item.last_actual_start_time),
                    "last_actual_end_time": self._dt_to_text(item.last_actual_end_time),
                    "schedule_delay_sec": item.delay_sec,
                    "conflict_flag": item.conflict_flag,
                    "conflict_group_size": item.conflict_group_size,
                    "queue_position": item.queue_position,
                    "scheduler_skip_reason": item.skip_reason,
                }
                for item in self.items
            ],
        }

    @staticmethod
    def _priority_value(ch_data: Dict[str, Any]) -> int:
        raw = str(ch_data.get("priority", "normal") or "normal").strip().lower()
        if raw in {"high", "h", "高", "urgent", "critical"}:
            return 2
        if raw in {"low", "l", "低"}:
            return 0
        return 1
