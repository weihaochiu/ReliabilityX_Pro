"""OI-051 canonical forward-pair validity and GUI display regressions."""

from types import SimpleNamespace

import pytest

from core.measurement_schema import forward_card_metrics


@pytest.mark.offline
@pytest.mark.parametrize("payload, expected", [
    ({"Voc_F_Corr": .95, "PCE_F_Corr": 18.2, "Voc_F_Raw": 1, "PCE_F_Raw": 20}, (.95, 18.2, "Corr")),
    ({"Voc_F_Corr": 0, "PCE_F_Corr": 0}, (0, 0, "Corr")),
    ({"Voc_F_Corr": .95, "PCE_F_Corr": 18.2, "valid_F_Corr": False,
      "Voc_F_Raw": 1, "PCE_F_Raw": 20}, (1, 20, "Raw")),
    ({"Voc_F_Corr": float("nan"), "PCE_F_Corr": 18.2,
      "Voc_F_Raw": 1, "PCE_F_Raw": 20}, (1, 20, "Raw")),
    ({"Voc_F_Corr": .95, "PCE_F_Raw": 20}, (None, None, "Invalid")),
    ({"Voc_F_Corr": float("inf"), "PCE_F_Corr": 20}, (None, None, "Invalid")),
    ({"Voc_F_Corr": True, "PCE_F_Corr": 20}, (None, None, "Invalid")),
    ({"Voc_F_Corr": None, "PCE_F_Corr": 20, "Voc_f": 1, "Eff_f": 2}, (None, None, "Invalid")),
    ({"Voc_f": .9, "Eff_f": 12}, (.9, 12, "Legacy")),
    ({}, (None, None, "Invalid")),
])
def test_forward_pair_contract(payload, expected):
    """Preserve genuine zeroes, reject invalid data, and avoid mixing sources."""
    assert forward_card_metrics(payload) == expected


@pytest.mark.offline
def test_real_card_preserves_metrics_after_completion(qapp):
    """Exercise real Qt card/controller and the subsequent completion signal."""
    from PyQt6.QtWidgets import QMainWindow
    from gui.main_window import MainWindow
    from gui.widgets.channel_card import ChannelCard

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    card = ChannelCard(channel_id=1)
    window.cards_by_ch_id = {1: card}
    window.engine = SimpleNamespace(is_running=False)
    try:
        window.on_measurement_finished({"ch_id": 1, "Voc_F_Corr": .95, "PCE_F_Corr": 18.2})
        window.update_realtime_status({"ch_id": 1, "message": "已完成"})
        assert "0.950V" in card.lbl_status.text()
        assert "18.20%" in card.lbl_status.text()
        assert "校正" in card.lbl_status.text()
        assert card.lbl_status.property("status") == "ok"
        window.on_measurement_finished({"ch_id": 1})
        assert "無有效" in card.lbl_status.text()
        assert "0.00" not in card.lbl_status.text()
        assert card.lbl_status.property("status") == "warning"
        window.on_measurement_finished({"ch_id": 1, "Voc_F_Raw": 1.1, "PCE_F_Raw": 19.0})
        assert "原始" in card.lbl_status.text()
    finally:
        card.deleteLater()
        window.deleteLater()
        qapp.processEvents()
