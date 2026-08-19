"""gui/config_tabs/environment_tab/climate_chamber_widgets/chamber_debug_widget.py

Chamber diagnostics update (202606021545):
- Keep the manual command terminal visible enough to show full TX/RX ASCII/HEX.
- The controller now appends multi-line diagnostic reports instead of a short
  ``@0101..`` placeholder.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QVBoxLayout


class ChamberDebugWidget(QGroupBox):
    """Manual debug terminal widget for climate chamber commands."""

    manual_command_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        """Create the debug terminal widget."""
        super().__init__("手動除錯指令終端", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build debug terminal controls."""
        debug_layout = QVBoxLayout(self)

        debug_input_layout = QHBoxLayout()
        self.manual_cmd_input = QLineEdit("01")
        self.manual_cmd_input.setPlaceholderText("輸入 Signal ID 與資料，例如 01 或 05xxxx")
        self.btn_send_manual = QPushButton("🚀 發送/診斷")
        debug_input_layout.addWidget(self.manual_cmd_input)
        debug_input_layout.addWidget(self.btn_send_manual)

        self.manual_log_output = QTextEdit()
        self.manual_log_output.setObjectName("manual_log_output")
        self.manual_log_output.setReadOnly(True)
        self.manual_log_output.setFixedHeight(220)

        debug_layout.addLayout(debug_input_layout)
        debug_layout.addWidget(self.manual_log_output)

        self.btn_send_manual.clicked.connect(self.manual_command_requested.emit)

    def get_command_id(self) -> str:
        """Return current manual command text."""
        return self.manual_cmd_input.text().strip()

    def append_log(self, text: str) -> None:
        """Append diagnostic text into the terminal output."""
        self.manual_log_output.append(text)
        self.manual_log_output.append("")
