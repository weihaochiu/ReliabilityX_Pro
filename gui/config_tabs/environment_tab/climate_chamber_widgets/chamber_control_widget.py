"""gui/config_tabs/environment_tab/climate_chamber_widgets/chamber_control_widget.py

Stage 2.6 update:
- Split the old chamber_tab manual control section into a reusable widget.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDoubleSpinBox, QFormLayout, QGroupBox, QMessageBox, QPushButton


class ChamberControlWidget(QGroupBox):
    """Manual setpoint control widget for the chamber.

    The spin boxes in this widget are operator-owned command inputs.  Periodic
    chamber PV/SV telemetry must not overwrite them, because doing so makes the
    requested target temperature/humidity appear to track the current readback.
    """

    send_setpoints_requested = pyqtSignal()
    manual_input_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__("手動控制", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build manual control controls."""
        control_layout = QFormLayout(self)
        self.temp_sv_spin = QDoubleSpinBox()
        self.temp_sv_spin.setRange(-40.0, 150.0)
        self.temp_sv_spin.setSuffix(" °C")
        self.temp_sv_spin.setSingleStep(0.1)
        self.temp_sv_spin.setKeyboardTracking(False)
        self.temp_sv_spin.setAccelerated(False)
        self.temp_sv_spin.setToolTip("手動輸入的目標溫度；不會因 PV/SV telemetry 輪詢而自動變更。連續調整時會暫停背景讀值，避免 UI 卡住。")

        self.hum_sv_spin = QDoubleSpinBox()
        self.hum_sv_spin.setRange(0.0, 100.0)
        self.hum_sv_spin.setSuffix(" %")
        self.hum_sv_spin.setSingleStep(1.0)
        self.hum_sv_spin.setKeyboardTracking(False)
        self.hum_sv_spin.setAccelerated(False)
        self.hum_sv_spin.setToolTip("手動輸入的目標濕度；不會因 PV/SV telemetry 輪詢而自動變更。連續調整時會暫停背景讀值，避免 UI 卡住。")

        self.btn_send_setpoints = QPushButton("傳送設定")
        control_layout.addRow("目標溫度（手動輸入）:", self.temp_sv_spin)
        control_layout.addRow("目標濕度（手動輸入）:", self.hum_sv_spin)
        control_layout.addRow(self.btn_send_setpoints)

        self.btn_send_setpoints.clicked.connect(self.send_setpoints_requested.emit)
        self.temp_sv_spin.valueChanged.connect(self.manual_input_changed.emit)
        self.hum_sv_spin.valueChanged.connect(self.manual_input_changed.emit)

    def get_setpoints(self) -> tuple[float, float]:
        """Return current target setpoints."""
        return self.temp_sv_spin.value(), self.hum_sv_spin.value()

    def set_setpoints(self, temp_sv: float | None, hum_sv: float | None) -> None:
        """Deprecated compatibility method; do not call from polling.

        Args:
            temp_sv: Ignored status-read temperature setpoint.
            hum_sv: Ignored status-read humidity setpoint.

        Notes:
            Older code called this method from periodic telemetry polling.  That
            made manual command fields follow chamber readback values.  The
            method is kept as a no-op for binary/source compatibility, but new
            code must treat these spin boxes as user-entered command values.
        """
        _ = (temp_sv, hum_sv)

    def show_send_result(self, ok: bool, message: str) -> None:
        """Show send-setpoint result."""
        if ok:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.warning(self, "錯誤", message)
