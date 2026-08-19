"""CSV logger regression tests using temporary data directories only."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from core.iv_curve_logger import IVCurveLogger
from core.measurement_schema import IV_PARAMETER_KEYS, SUMMARY_SUB_HEADERS
from core.summary_logger import SummaryLogger


def _analysis_results() -> dict[str, float]:
    """Return explicit fixture values for every current analysis key."""
    result: dict[str, float] = {"HI_Raw": 0.0, "HI_Corr": 0.0}
    for suffix in ("F_Raw", "R_Raw", "F_Corr", "R_Corr"):
        for index, key in enumerate(IV_PARAMETER_KEYS, start=1):
            result[f"{key}_{suffix}"] = float(index)
    return result


def _metadata() -> dict[str, object]:
    """Return a complete current production metadata fixture."""
    now = dt.datetime(2026, 8, 19, 12, 0, 0)
    return {
        "user": "offline_user",
        "project": "offline_project",
        "device_name": "offline_device",
        "ch_id": 1,
        "channel_label": "CH01",
        "experiment_uid": "EXP_OFFLINE",
        "run_session_id": "RUN_OFFLINE",
        "relay_pos": 1,
        "relay_neg": 2,
        "line_res": 3.5,
        "line_res_date": "2026-08-19 11:00:00",
        "offset_current": 1e-6,
        "area": 0.5,
        "v_start": 0.0,
        "v_stop": 1.0,
        "v_step": 0.5,
        "delay_time": 0,
        "interval_min": 0,
        "start_time": now,
        "scheduled_time": now,
        "actual_start_time": now,
        "actual_end_time": now,
        "schedule_delay_sec": 0.0,
        "queue_position": 1,
        "conflict_flag": False,
        "next_due_time_basis": "scheduled_due_plus_interval",
        "temp": 25.0,
        "hum": 50.0,
    }


@pytest.mark.offline
def test_iv_curve_and_summary_contracts_match_analysis_schema(tmp_path: Path) -> None:
    """Raw curve, summary matrix, and summary report share metric names."""
    metadata = _metadata()
    analysis = _analysis_results()
    points = [
        {"v_src": 0.0, "i_msd": -0.02, "v_corr": 0.0, "i_corr": -0.019},
        {"v_src": 1.0, "i_msd": 0.0, "v_corr": 1.0, "i_corr": 0.0},
    ]
    iv_logger = IVCurveLogger(root_path=tmp_path)
    summary_logger = SummaryLogger(root_path=tmp_path)

    curve_path = iv_logger.save_iv_curve(metadata, points, list(reversed(points)), analysis)
    summary_path = summary_logger.update_summary_report({**metadata, **analysis, "file_path": curve_path})
    assert curve_path.is_file()
    assert summary_path is None  # Current API writes in place and has no return value.

    curve_text = curve_path.read_text(encoding="utf-8-sig")
    assert "Forward_Raw" in curve_text
    assert "Reversed_Raw" in curve_text
    for header in SUMMARY_SUB_HEADERS:
        assert header in curve_text

    report_path = tmp_path / "offline_user" / "offline_project" / "offline_device" / "Summary_report.csv"
    with report_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    header = next(row for row in rows if row and row[0] == "Start_Time")
    for required in (
        "Experiment_UID",
        "Run_Session_ID",
        "Channel_Label",
        "Internal_CH_ID",
        "Scheduled_Time",
        "Actual_Start_Time",
        "Actual_End_Time",
        "Schedule_Delay_Sec",
        "Raw_Data_File",
    ):
        assert required in header
    assert all(len(row) == SummaryLogger.TOTAL_COLS for row in rows)


@pytest.mark.offline
def test_loggers_write_only_below_tmp_path(tmp_path: Path, repository_root: Path) -> None:
    """Logger output is isolated from the repository ``data`` directory."""
    before = set((repository_root / "data").rglob("*")) if (repository_root / "data").exists() else set()
    logger = SummaryLogger(root_path=tmp_path)
    logger.update_summary_report({**_metadata(), **_analysis_results()})
    after = set((repository_root / "data").rglob("*")) if (repository_root / "data").exists() else set()
    assert before == after
    assert list(tmp_path.rglob("Summary_report.csv"))
