"""Production emit-side payload and logger-consumer contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.measurement_schema import IV_PARAMETER_KEYS
from tests.pipeline_support import build_offline_engine, make_channel


@pytest.mark.offline
def test_signal_payload_preserves_current_identity_and_scientific_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cross-check prepared, point, final-result, and CSV-consumer payloads."""
    engine, _, _, _ = build_offline_engine(tmp_path, monkeypatch)
    prepared: list[dict] = []
    points: list[dict] = []
    final: list[dict] = []
    engine.channel_scan_prepared.connect(prepared.append)
    engine.point_measured.connect(points.append)
    engine.channel_measurement_finished.connect(final.append)
    engine.start_scan_cycle([make_channel()])

    prep = prepared[0]
    for key in ("user", "project", "device_name", "ch_id", "channel_label", "experiment_uid", "run_session_id"):
        assert prep[key]

    assert {point["direction"] for point in points} == {"fwd", "rev"}
    for point in points:
        assert {"ch_id", "direction", "v_src", "i_msd", "v_corr", "i_corr", "offset_current"} <= point.keys()

    result = final[0]
    for key in (
        "user",
        "project",
        "device_name",
        "ch_id",
        "channel_label",
        "experiment_uid",
        "run_session_id",
        "start_time",
        "scheduled_time",
        "actual_start_time",
        "actual_end_time",
        "file_path",
    ):
        assert result.get(key) not in (None, "")
    for suffix in ("F_Raw", "R_Raw", "F_Corr", "R_Corr"):
        for metric in IV_PARAMETER_KEYS:
            assert f"{metric}_{suffix}" in result

    summary_text = next(tmp_path.rglob("Summary_report.csv")).read_text(encoding="utf-8-sig")
    assert "Experiment_UID" in summary_text
    assert "Run_Session_ID" in summary_text
    assert "Forward_Raw" in summary_text
    assert "Forward_Corr" in summary_text
