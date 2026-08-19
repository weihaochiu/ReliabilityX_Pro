"""gui/widgets/channel_action_widget.py

Dynamic logical channel update:
- Keep direct SMU+ / SMU- relay selection simple for the user.
- Show scientific relay-sharing hints under each relay selector.
- Relay sharing remains derived from channel settings rather than manually managed
  as a separate bus topology.
"""

from datetime import datetime

from PyQt6.QtWidgets import QWidget, QPushButton, QLabel, QGridLayout, QComboBox
from PyQt6.QtCore import pyqtSignal

LABEL_WIDTH = 150


class ChannelActionWidget(QWidget):
    """Relay and diagnostic action widget.

    The widget intentionally stays UI-only. It does not decide whether a relay
    selection is legal; the controller (`ChannelSettingDialog`) calculates the
    relay-sharing state and passes human-readable hints into this widget.
    """

    measure_rline_clicked = pyqtSignal()
    spot_check_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        """Build relay selectors, diagnostic labels, and action buttons."""
        layout = QGridLayout(self)

        self.combo_relay_pos = QComboBox()
        self.combo_relay_neg = QComboBox()
        self.label_pos_hint = QLabel("SMU+ Relay: 請先選擇 relay。")
        self.label_neg_hint = QLabel("SMU− Relay: 請先選擇 relay。")
        self.label_rline = QLabel("線路阻抗 (R-line): --- Ω")
        self.label_isc_diag = QLabel("Isc 診斷: --- A")
        self.btn_measure_rline = QPushButton("量測線路阻抗")
        self.btn_spot_check = QPushButton("即時連線測試")

        labels = [
            QLabel("SMU+ Relay:"),
            QLabel("SMU− Relay:"),
        ]
        for label in labels:
            label.setFixedWidth(LABEL_WIDTH)

        layout.addWidget(labels[0], 0, 0)
        layout.addWidget(self.combo_relay_pos, 0, 1)
        layout.addWidget(self.label_pos_hint, 1, 0, 1, 2)
        layout.addWidget(labels[1], 2, 0)
        layout.addWidget(self.combo_relay_neg, 2, 1)
        layout.addWidget(self.label_neg_hint, 3, 0, 1, 2)
        layout.addWidget(self.label_rline, 4, 0, 1, 2)
        layout.addWidget(self.label_isc_diag, 5, 0, 1, 2)
        layout.addWidget(self.btn_measure_rline, 6, 0)
        layout.addWidget(self.btn_spot_check, 6, 1)

        layout.setColumnStretch(1, 1)

        self.btn_measure_rline.clicked.connect(self.measure_rline_clicked)
        self.btn_spot_check.clicked.connect(self.spot_check_clicked)
        self.set_relay_usage_hints(None, None)

    def get_data(self):
        """Return selected relay ids as text values."""
        return {
            "relay_pos": self.combo_relay_pos.currentText(),
            "relay_neg": self.combo_relay_neg.currentText(),
        }

    def set_data(self, data, calibration_settings):
        """Apply saved relay selections and refresh the R-line readout.

        Args:
            data: Dictionary containing `relay_pos` and `relay_neg`.
            calibration_settings: The calibration `line_resistance_map`.
        """
        data = data or {}
        pos_relay = data.get("relay_pos")
        neg_relay = data.get("relay_neg")

        if pos_relay is not None and str(pos_relay) != "":
            self.combo_relay_pos.setCurrentText(str(pos_relay))
        else:
            self.combo_relay_pos.setCurrentIndex(-1)

        if neg_relay is not None and str(neg_relay) != "":
            self.combo_relay_neg.setCurrentText(str(neg_relay))
        else:
            self.combo_relay_neg.setCurrentIndex(-1)

        pos_text = self.combo_relay_pos.currentText().strip()
        neg_text = self.combo_relay_neg.currentText().strip()
        self.update_rline_display(pos_text, neg_text, calibration_settings)

    def _extract_rline_value_and_time(self, record):
        """Normalize one R-line calibration record.

        Args:
            record: Legacy numeric value or dict with `value` / `time`.

        Returns:
            tuple[float | None, str | None]: Resistance value and timestamp.
        """
        if isinstance(record, (int, float)):
            return float(record), None

        if isinstance(record, dict):
            value = record.get("value")
            if isinstance(value, (int, float)):
                return float(value), record.get("time")

        return None, None

    def _parse_time_text(self, time_text):
        if not time_text:
            return None
        text = str(time_text).strip()
        for parser in (
            datetime.fromisoformat,
            lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S.%f"),
            lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S"),
            lambda x: datetime.strptime(x, "%Y/%m/%d %H:%M:%S"),
            lambda x: datetime.strptime(x, "%Y/%m/%d %H:%M"),
        ):
            try:
                return parser(text)
            except Exception:
                continue
        return None

    def update_rline_display(self, pos_text, neg_text, calibration_settings, max_age_days=30):
        """Update line-resistance label for the selected relay path.

        Missing R-line is shown as a blocking setup issue; expired R-line is a
        red traceability warning based on the global Config threshold.
        """
        self.label_rline.setStyleSheet("color: #555555;")
        if not pos_text or not neg_text:
            self.label_rline.setText("線路阻抗 (R-line): --- Ω")
            return

        rline_key = f"{pos_text}_{neg_text}"
        rline_record = calibration_settings.get(rline_key)

        value, time_text = self._extract_rline_value_and_time(rline_record)

        if value is None:
            self.label_rline.setStyleSheet("color: #C0392B;")
            self.label_rline.setText("線路阻抗 (R-line): 尚未量測，需先量測後才能存檔")
            return

        age_note = ""
        dt = self._parse_time_text(time_text)
        if dt is not None:
            age_days = max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
            if age_days > max_age_days:
                self.label_rline.setStyleSheet("color: #C0392B;")
                age_note = f"，已 {age_days:.0f} 天 > {max_age_days} 天，建議重新校正"
            else:
                self.label_rline.setStyleSheet("color: #555555;")
                age_note = f"，{age_days:.0f} 天前"

        if time_text:
            self.label_rline.setText(
                f"線路阻抗 (R-line): {value:.4f} Ω ({time_text}{age_note})"
            )
        else:
            self.label_rline.setStyleSheet("color: #C0392B;")
            self.label_rline.setText(
                f"線路阻抗 (R-line): {value:.4f} Ω (舊格式，無時間戳；上機前需重新校正)"
            )

    def show_rline_error(self, msg="讀取失敗"):
        """Show an R-line readout error."""
        self.label_rline.setText(f"線路阻抗 (R-line): {msg}")

    def update_isc_status(self, current, status_text, color):
        """Update Isc diagnostic result."""
        self.label_isc_diag.setText(f"Isc 診斷: {current:.2e} A ({status_text})")
        self.label_isc_diag.setStyleSheet(f"color: {color};")

    def set_relay_options(self, pos_list, neg_list):
        """Populate relay selectors with environment-limited relay ranges."""
        current_pos = self.combo_relay_pos.currentText()
        current_neg = self.combo_relay_neg.currentText()

        self.combo_relay_pos.blockSignals(True)
        self.combo_relay_neg.blockSignals(True)

        self.combo_relay_pos.clear()
        self.combo_relay_pos.addItems(pos_list)

        self.combo_relay_neg.clear()
        self.combo_relay_neg.addItems(neg_list)

        if current_pos in pos_list:
            self.combo_relay_pos.setCurrentText(current_pos)
        else:
            self.combo_relay_pos.setCurrentIndex(-1)

        if current_neg in neg_list:
            self.combo_relay_neg.setCurrentText(current_neg)
        else:
            self.combo_relay_neg.setCurrentIndex(-1)

        self.combo_relay_pos.blockSignals(False)
        self.combo_relay_neg.blockSignals(False)

    def _apply_hint_style(self, label, level):
        """Apply semantic style to one relay hint label."""
        colors = {
            "idle": "#666666",
            "independent": "#555555",
            "shared": "#B26A00",
            "error": "#C0392B",
        }
        label.setStyleSheet(f"color: {colors.get(level, '#555555')};")

    def set_relay_usage_hints(self, pos_hint, neg_hint, pos_level="idle", neg_level="idle"):
        """Show relay-sharing hints calculated by the controller.

        Args:
            pos_hint: Message for SMU+ relay.
            neg_hint: Message for SMU− relay.
            pos_level: One of idle / independent / shared / error.
            neg_level: One of idle / independent / shared / error.
        """
        self.label_pos_hint.setText(pos_hint or "SMU+ Relay: 請先選擇 relay。")
        self.label_neg_hint.setText(neg_hint or "SMU− Relay: 請先選擇 relay。")
        self._apply_hint_style(self.label_pos_hint, pos_level)
        self._apply_hint_style(self.label_neg_hint, neg_level)
