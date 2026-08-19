"""
TrendDisplayWidget: A widget for controlling trend chart display options.
"""
from PyQt6.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QComboBox, QCheckBox
from PyQt6.QtCore import pyqtSignal, pyqtSlot


class TrendDisplayWidget(QWidget):
    """
    A widget containing controls for how data is displayed on the trend chart,
    such as X-axis mode, normalization, and whether the environment subplot is shown.

    Emits a `displayOptionsChanged` signal whenever an option is modified.
    """

    displayOptionsChanged = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        group_box = QGroupBox("顯示模式")
        group_box.setStyleSheet(
            """
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
            """
        )
        v_layout = QVBoxLayout(group_box)

        self.cb_xaxis_mode = QComboBox()
        self.cb_xaxis_mode.addItems(["運行時間 (Hours)", "量測序號 (Seq)"])
        self.cb_xaxis_mode.currentTextChanged.connect(self._on_options_changed)

        self.chk_normalize = QCheckBox("標準化至初始值 (%)")
        self.chk_normalize.stateChanged.connect(self._on_options_changed)

        self.chk_show_env = QCheckBox("顯示環境子圖")
        self.chk_show_env.stateChanged.connect(self._on_options_changed)

        self.chk_smooth = QCheckBox("數據平滑 (Moving Avg)")
        self.chk_smooth.stateChanged.connect(self._on_options_changed)

        v_layout.addWidget(self.cb_xaxis_mode)
        v_layout.addWidget(self.chk_normalize)
        v_layout.addWidget(self.chk_show_env)
        v_layout.addWidget(self.chk_smooth)

        layout.addWidget(group_box)

    @pyqtSlot()
    def _on_options_changed(self):
        self.displayOptionsChanged.emit(self.get_current_options())

    def get_current_options(self):
        return {
            "x_axis_mode": self.cb_xaxis_mode.currentText(),
            "normalize": self.chk_normalize.isChecked(),
            "show_env": self.chk_show_env.isChecked(),
            "smoothing": self.chk_smooth.isChecked(),
        }
