"""End-to-end production measurement pipeline using mock hardware only."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.pipeline_support import build_offline_engine, make_channel


@pytest.mark.offline
def test_complete_one_channel_mock_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run config, relay, SMU, correction, analysis, logger, and signal flow."""
    engine, smu, relay, recorder = build_offline_engine(tmp_path, monkeypatch)
    prepared: list[dict] = []
    points: list[dict] = []
    finished: list[dict] = []
    engine.channel_scan_prepared.connect(prepared.append)
    engine.point_measured.connect(points.append)
    engine.channel_measurement_finished.connect(finished.append)

    engine.start_scan_cycle([make_channel()])

    assert len(prepared) == 1
    assert len(points) == 10  # five forward and five reverse points
    assert len(finished) == 1
    result = finished[0]
    assert result["Voc_F_Raw"] == pytest.approx(1.0, abs=1e-12)
    assert result["Isc_F_Raw"] == pytest.approx(20.0, rel=1e-12)
    assert result["PCE_F_Raw"] == pytest.approx(10.0, rel=1e-12)
    assert result["Voc_R_Corr"] == pytest.approx(1.0, abs=1e-12)
    assert result["channel_label"] == "CH01"
    assert list(tmp_path.rglob("*IV curve.csv"))
    assert list(tmp_path.rglob("Summary_report.csv"))
    assert smu.output_state is False
    assert relay.relay_state == set()
    assert any(call["method"] == "switch_on" for call in recorder.calls)
    assert engine.last_finish_reason == "completed"


@pytest.mark.offline
def test_pipeline_never_sleeps_real_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Injected timing keeps a complete one-shot scan fast and deterministic."""
    engine, _, _, _ = build_offline_engine(tmp_path, monkeypatch)
    engine.start_scan_cycle([make_channel(delay_time=10000)])
    assert engine.last_finish_reason == "completed"
