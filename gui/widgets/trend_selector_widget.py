"""
TrendSelectorWidget: A widget for selecting the metric and dimensions for the trend chart.
"""
from PyQt6.QtWidgets import QWidget, QGroupBox, QFormLayout, QComboBox
from PyQt6.QtCore import pyqtSignal, pyqtSlot

from core.trend_spec import (
    get_trend_direction_options,
    get_trend_metric_options,
    get_trend_path_options,
    metric_supports_direction,
)


class TrendSelectorWidget(QWidget):
    """
    A widget containing QComboBoxes for selecting the metric, scan direction,
    and data path (Raw/Corr) to be displayed on the trend chart.

    Emits a `selectionChanged` signal whenever a choice is modified.
    """
    selectionChanged = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QFormLayout(self)
        layout.setContentsMargins(10, 15, 10, 10)

        group_box = QGroupBox("維度與指標")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid silver;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """)
        form_layout = QFormLayout(group_box)

        self.cb_metric = QComboBox()
        self.cb_metric.addItems(get_trend_metric_options())

        self.cb_direction = QComboBox()
        self.cb_direction.addItems(get_trend_direction_options())

        self.cb_path = QComboBox()
        self.cb_path.addItems(get_trend_path_options())

        for cb in [self.cb_metric, self.cb_direction, self.cb_path]:
            cb.currentTextChanged.connect(self._on_selection_changed)

        form_layout.addRow("量測指標:", self.cb_metric)
        form_layout.addRow("掃描方向:", self.cb_direction)
        form_layout.addRow("數據路徑:", self.cb_path)

        layout.addWidget(group_box)

    @pyqtSlot()
    def _on_selection_changed(self):
        state = self.get_current_selection()
        self.selectionChanged.emit(state)

    def get_current_selection(self):
        metric = self.cb_metric.currentText()
        supports_direction = metric_supports_direction(metric)
        self.cb_direction.setDisabled(not supports_direction)

        return {
            "metric": metric,
            "direction": self.cb_direction.currentText() if supports_direction else None,
            "path": self.cb_path.currentText(),
        }
