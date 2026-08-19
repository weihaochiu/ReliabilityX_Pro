"""gui/widgets/channel_card.py

Dynamic logical channel update:
- Display the logical channel label (for example CH_C01 / CH_I01 / CH_V01)
  instead of assuming fixed CH01-CH32 visible cards.
- Keep the numeric `channel_id` internally for compatibility with existing data
  loggers, signal payloads, and summary files.
- Keep the main card compact and move relay details into a tooltip.
- Make the checkbox wording explicit: checked means start cyclic measurement,
  unchecked means pause cyclic measurement.
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton
from PyQt6.QtCore import pyqtSignal


class ChannelCard(QFrame):
    """Compact card representing one configured logical measurement channel."""

    config_requested = pyqtSignal(int)
    end_requested = pyqtSignal(int)

    def __init__(self, channel_id: int, parent=None):
        super().__init__(parent)
        self.channel_id = channel_id
        self.logical_label = f"CH{self.channel_id:02d}"

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("ChannelCard")

        self._init_ui()
        self.setProperty("state", "disabled")

    def _init_ui(self):
        """Build the card UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        top_layout = QHBoxLayout()
        self.chk_enabled = QCheckBox()
        top_layout.addWidget(self.chk_enabled)
        top_layout.addStretch()

        self.lbl_user = QLabel("N/A")
        self.lbl_project = QLabel("N/A")
        self.lbl_device = QLabel("未命名")
        self.lbl_relay_summary = QLabel("Relay: --")
        self.lbl_status = QLabel("準備中")

        self.lbl_project.setObjectName("lbl_project")
        self.lbl_device.setObjectName("lbl_device")
        self.lbl_status.setObjectName("lbl_status")

        self.btn_ch_settings = QPushButton("⚙️ 設定")
        self.btn_end_channel = QPushButton("結束實驗 / 移除")
        self.btn_ch_settings.clicked.connect(self._on_config_clicked)
        self.btn_end_channel.clicked.connect(self._on_end_clicked)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.lbl_user)
        main_layout.addWidget(self.lbl_project)
        main_layout.addWidget(self.lbl_device)
        main_layout.addWidget(self.lbl_relay_summary)
        main_layout.addStretch()
        main_layout.addWidget(self.lbl_status)
        main_layout.addWidget(self.btn_ch_settings)
        main_layout.addWidget(self.btn_end_channel)

        self.chk_enabled.toggled.connect(self._update_ui_state)
        self._update_ui_state(self.is_checked())

    def update_data(self, data: dict):
        """Update the compact display and tooltip from channel settings."""
        data = data or {}
        self.logical_label = str(data.get("channel_label") or f"CH{self.channel_id:02d}")
        user = data.get("user", "N/A") or "N/A"
        project = data.get("project", "N/A") or "N/A"
        device_name = data.get("device_name", "未命名") or "未命名"
        interval = data.get("interval_min")
        relay_pos = data.get("relay_pos")
        relay_neg = data.get("relay_neg")
        environment = data.get("environment_instance", "-") or "-"
        relay_summary = data.get("relay_share_summary") or f"+R{relay_pos if relay_pos is not None else '--'} / -R{relay_neg if relay_neg is not None else '--'}"
        relay_tooltip = data.get("relay_detail_tooltip") or ""

        self._refresh_checkbox_text()
        self.lbl_user.setText(f"[{user}]")
        self.lbl_project.setText(project)
        self.lbl_device.setText(device_name)
        if interval not in (None, ""):
            self.lbl_relay_summary.setText(f"{relay_summary} | {interval} min")
        else:
            self.lbl_relay_summary.setText(relay_summary)

        tooltip_lines = [
            f"Channel: {self.logical_label}",
            f"Internal ID: CH{self.channel_id:02d}",
            f"Device: {device_name}",
            f"User / Project: {user} / {project}",
            f"Environment: {environment}",
            f"SMU+ Relay: {relay_pos}",
            f"SMU− Relay: {relay_neg}",
        ]
        if interval not in (None, ""):
            tooltip_lines.append(f"Interval: {interval} min")
        if relay_tooltip:
            tooltip_lines.extend(["", relay_tooltip])
        self.setToolTip("\n".join(tooltip_lines))

        self.set_checked(bool(data.get("is_enabled", False)))


    def _refresh_checkbox_text(self):
        """Render the checkbox as cyclic-measurement start/pause control."""
        action = "開始循環量測" if self.is_checked() else "暫停循環量測"
        self.chk_enabled.setText(f"{action}  {self.logical_label}")

    def update_status(self, message: str, status_level: str = "idle"):
        """Update the status label text and semantic color property."""
        self.lbl_status.setText(message)
        self.lbl_status.setProperty("status", status_level)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

    def _update_ui_state(self, is_checked: bool):
        """Refresh card appearance when active/disabled changes."""
        details_widgets = [
            self.lbl_user,
            self.lbl_project,
            self.lbl_device,
            self.lbl_relay_summary,
            self.lbl_status,
            self.btn_ch_settings,
            self.btn_end_channel,
        ]

        state = "active" if is_checked else "disabled"
        self.setProperty("state", state)

        self._refresh_checkbox_text()
        for widget in details_widgets:
            widget.show()

        self.style().unpolish(self)
        self.style().polish(self)

    def _on_config_clicked(self):
        """Emit a request to open this channel's configuration dialog."""
        self.config_requested.emit(self.channel_id)

    def _on_end_clicked(self):
        """Emit a request to end the experiment and remove this channel."""
        self.end_requested.emit(self.channel_id)

    def is_checked(self) -> bool:
        """Return whether this logical channel is enabled for scanning."""
        return self.chk_enabled.isChecked()

    def set_checked(self, checked: bool):
        """Set the checkbox state without causing a signal feedback loop."""
        if self.is_checked() == checked:
            return
        self.chk_enabled.blockSignals(True)
        self.chk_enabled.setChecked(checked)
        self.chk_enabled.blockSignals(False)
        self._update_ui_state(checked)
