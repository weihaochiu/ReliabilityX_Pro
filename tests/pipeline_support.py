"""Shared offline measurement-pipeline setup for integration tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

import config
from core.iv_curve_logger import IVCurveLogger
from core.measure_engine import MeasureEngine
from core.summary_logger import SummaryLogger
from tests.mocks.mock_relay import MockRelay
from tests.mocks.mock_smu import CallRecorder, MockSMU


def make_channel(**overrides: Any) -> dict[str, Any]:
    """Build one complete, one-shot logical channel fixture.

    Args:
        **overrides: Values replacing fixture defaults.

    Returns:
        Current production channel dictionary.
    """
    channel: dict[str, Any] = {
        "ch_id": 1,
        "internal_ch_id": 1,
        "channel_label": "CH01",
        "user": "offline_user",
        "project": "offline_project",
        "device_name": "offline_device",
        "area": 0.5,
        "relay_pos": 1,
        "relay_neg": 2,
        "v_start": 0.0,
        "v_stop": 1.0,
        "v_step": 0.25,
        "i_limit": 0.1,
        "delay_time": 0,
        "interval_min": 0,
        "is_enabled": True,
        "experiment_uid": "EXP_OFFLINE",
        "run_session_id": "RUN_OFFLINE",
    }
    channel.update(overrides)
    return channel


def build_offline_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    smu: MockSMU | None = None,
    relay: MockRelay | None = None,
    recorder: CallRecorder | None = None,
) -> tuple[MeasureEngine, MockSMU, MockRelay, CallRecorder]:
    """Create an isolated production engine injected with pure mocks.

    Args:
        tmp_path: Per-test output root.
        monkeypatch: Pytest monkeypatch fixture.
        smu: Optional SMU mock.
        relay: Optional relay mock.
        recorder: Optional shared event recorder.

    Returns:
        Engine, SMU, relay, and shared recorder.
    """
    shared = recorder or CallRecorder()
    mock_smu = smu or MockSMU(shared)
    mock_relay = relay or MockRelay(shared)
    monkeypatch.setattr(config, "sanitize_user_paths", lambda: {"data_dir": tmp_path, "log_dir": tmp_path})
    monkeypatch.setattr(config, "get_safe_data_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "get_safe_log_dir", lambda: tmp_path)
    monkeypatch.setattr(
        config,
        "get_scheduler_runtime_settings",
        lambda settings=None: {"mode": "flexible_catch_up", "max_allowed_delay_sec": 300},
    )

    engine = MeasureEngine(smu_driver=mock_smu, relay_driver=mock_relay, chamber_driver=None, log_manager=None)
    engine.iv_curve_logger = IVCurveLogger(root_path=tmp_path)
    engine.summary_logger = SummaryLogger(root_path=tmp_path)
    engine._interruptible_sleep = lambda seconds: None
    engine._load_schedule_state = lambda: {}
    engine._save_schedule_state = lambda scheduler, status="running": None

    calibration_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def load_configs() -> bool:
        """Populate isolated in-memory configs without repository writes."""
        engine.ch_settings = {}
        engine.cal_settings = {
            "offset_current": 0.0,
            "line_resistance_map": {"1_2": {"value": 0.0, "time": calibration_time}},
        }
        return True

    engine.load_configs = load_configs
    return engine, mock_smu, mock_relay, shared
