"""gui/config_tabs/chamber_tab.py

Chamber diagnostics update (202606021625):
- Hardware Connection / Chamber requires successful PV/SV telemetry before
  reporting connection success.
- COM ports show full USB-RS485 device descriptions.
- Manual terminal prints complete TX/RX ASCII and HEX diagnostics for FCS/RS485
  troubleshooting.
- Manual target setpoint spin boxes are user-owned inputs and are not overwritten
  by periodic PV/SV polling.
- Rapid manual setpoint changes pause synchronous chamber polling to prevent the
  System Configuration dialog from becoming unresponsive.
- Chamber setpoint-send failures now point operators to detailed persistent logs
  containing TX/RX ASCII, TX/RX HEX, FCS, timeout, and protocol notes.
"""

from __future__ import annotations

import time

import serial.tools.list_ports
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChamberTab(QWidget):
    """Low-level chamber hardware connection and diagnostics tab."""

    def __init__(self, engine, parent=None):
        """Initialize the chamber hardware tab."""
        super().__init__(parent)
        self.engine = engine

        self.chamber_update_timer = QTimer(self)
        self.chamber_update_timer.setInterval(2000)
        self.chamber_update_timer.timeout.connect(self._update_chamber_status)
        self._manual_input_pause_timer = QTimer(self)
        self._manual_input_pause_timer.setSingleShot(True)
        self._manual_input_pause_timer.setInterval(1200)
        self._manual_input_pause_timer.timeout.connect(self._resume_polling_after_manual_input)
        self._polling_visible = False
        self._poll_in_progress = False

        self.init_ui()

    def init_ui(self):
        """Build the UI for connection, status, setpoints, and diagnostics."""
        main_layout = QVBoxLayout(self)
        top_layout = QHBoxLayout()

        conn_group = QGroupBox("連線設定")
        conn_layout = QFormLayout(conn_group)

        port_baud_layout = QHBoxLayout()
        self.chamber_port_combo = QComboBox()
        self.chamber_port_combo.setMinimumWidth(260)
        port_baud_layout.addWidget(self.chamber_port_combo, 2)
        self.chamber_baud_combo = QComboBox()
        self.chamber_baud_combo.addItems(["4800", "9600", "19200", "38400", "57600", "115200"])
        self.chamber_baud_combo.setCurrentText("9600")
        port_baud_layout.addWidget(self.chamber_baud_combo, 1)

        self.chamber_id_spin = QSpinBox()
        self.chamber_id_spin.setRange(1, 99)

        self.protocol_hint = QLabel("RS-485 ASCII | 9600 bps | 8E1 | 半二重 | TX=CR+LF | RX=CR | Signal 01=Analog PV/SV")
        self.protocol_hint.setWordWrap(True)
        self.protocol_hint.setStyleSheet("color: #D6E4FF; font-weight: 600; padding: 4px;")

        conn_btn_layout = QHBoxLayout()
        scan_chamber_btn = QPushButton("🔄 掃描 Port")
        scan_chamber_btn.clicked.connect(self._scan_chamber_ports)
        self.test_conn_btn = QPushButton("🔗 測試連線")
        self.test_conn_btn.clicked.connect(self._test_chamber_connection)
        conn_btn_layout.addWidget(scan_chamber_btn)
        conn_btn_layout.addWidget(self.test_conn_btn)

        conn_layout.addRow("COM Port/Baud:", port_baud_layout)
        conn_layout.addRow("站號 (ID):", self.chamber_id_spin)
        conn_layout.addRow("通訊規格:", self.protocol_hint)
        conn_layout.addRow(conn_btn_layout)
        top_layout.addWidget(conn_group)

        status_group = QGroupBox("狀態監控")
        status_grid = QGridLayout(status_group)

        self.temp_pv_label = self._create_label_for_grid("--.- °C", "temp_pv")
        self.temp_sv_label = self._create_label_for_grid("--.- °C", "temp_sv")
        self.hum_pv_label = self._create_label_for_grid("--.- %", "hum_pv")
        self.hum_sv_label = self._create_label_for_grid("--.- %", "hum_sv")

        status_grid.addWidget(QLabel("溫度 T (°C)"), 0, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)
        status_grid.addWidget(QLabel("濕度 H (%)"), 0, 2, 1, 2, Qt.AlignmentFlag.AlignCenter)
        status_grid.addWidget(QLabel("PV (實際)"), 1, 0)
        status_grid.addWidget(QLabel("SV (設定)"), 1, 1)
        status_grid.addWidget(QLabel("PV (實際)"), 1, 2)
        status_grid.addWidget(QLabel("SV (設定)"), 1, 3)
        status_grid.addWidget(self.temp_pv_label, 2, 0)
        status_grid.addWidget(self.temp_sv_label, 2, 1)
        status_grid.addWidget(self.hum_pv_label, 2, 2)
        status_grid.addWidget(self.hum_sv_label, 2, 3)
        top_layout.addWidget(status_group, 1)

        main_layout.addLayout(top_layout)

        control_group = QGroupBox("手動控制")
        control_layout = QFormLayout(control_group)
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
        self.temp_sv_spin.valueChanged.connect(self._pause_polling_for_manual_input)
        self.hum_sv_spin.valueChanged.connect(self._pause_polling_for_manual_input)
        self.send_sv_btn = QPushButton("傳送設定")
        self.send_sv_btn.clicked.connect(self._send_chamber_setpoints)
        control_layout.addRow("目標溫度（手動輸入）:", self.temp_sv_spin)
        control_layout.addRow("目標濕度（手動輸入）:", self.hum_sv_spin)
        control_layout.addRow(self.send_sv_btn)
        main_layout.addWidget(control_group)

        debug_group = QGroupBox("手動除錯指令終端")
        debug_layout = QVBoxLayout(debug_group)

        debug_input_layout = QHBoxLayout()
        self.manual_cmd_input = QLineEdit("01")
        self.manual_cmd_input.setPlaceholderText("輸入 Signal ID 與資料，例如 01 或 05xxxx")
        self.btn_send_manual = QPushButton("🚀 發送/診斷")
        self.btn_send_manual.clicked.connect(self._on_manual_send_clicked)
        debug_input_layout.addWidget(self.manual_cmd_input)
        debug_input_layout.addWidget(self.btn_send_manual)

        self.manual_log_output = QTextEdit()
        self.manual_log_output.setObjectName("manual_log_output")
        self.manual_log_output.setReadOnly(True)
        self.manual_log_output.setFixedHeight(220)

        debug_layout.addLayout(debug_input_layout)
        debug_layout.addWidget(self.manual_log_output)
        main_layout.addWidget(debug_group)
        main_layout.addStretch()

    def _create_label_for_grid(self, text: str, prop: str) -> QLabel:
        """Create one status label."""
        label = QLabel(text)
        label.setProperty("display", prop)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _port_label(self, port_info) -> str:
        """Return an operator-readable COM-port label."""
        desc = port_info.description or "Serial Port"
        if port_info.device in desc:
            return desc
        return f"{desc} ({port_info.device})"

    def _get_selected_port(self) -> str:
        """Return the raw COM port value selected in the combo box."""
        data = self.chamber_port_combo.currentData()
        if data:
            return str(data)
        text = self.chamber_port_combo.currentText().strip()
        if "(" in text and text.endswith(")"):
            return text.rsplit("(", 1)[-1].rstrip(")")
        return text

    def _set_selected_port(self, port: str) -> None:
        """Select a raw COM port value, adding it if necessary."""
        port = str(port or "").strip()
        if not port:
            return
        for idx in range(self.chamber_port_combo.count()):
            if str(self.chamber_port_combo.itemData(idx)) == port:
                self.chamber_port_combo.setCurrentIndex(idx)
                return
        self.chamber_port_combo.addItem(port, port)
        self.chamber_port_combo.setCurrentIndex(self.chamber_port_combo.count() - 1)

    def _scan_chamber_ports(self):
        """Scan and display COM ports with USB-RS485 device descriptions."""
        current = self._get_selected_port()
        self.chamber_port_combo.clear()
        for item in serial.tools.list_ports.comports():
            self.chamber_port_combo.addItem(self._port_label(item), item.device)
        if current:
            self._set_selected_port(current)

    def _on_manual_send_clicked(self):
        """Send a manual diagnostic command and show full TX/RX details."""
        driver = getattr(self.engine, "chamber_driver", None)
        if not driver or not driver.is_connected():
            self.manual_log_output.append("[錯誤] 溫濕度箱 serial port 尚未開啟。請先測試連線。")
            return

        cmd_id = self.manual_cmd_input.text().strip()
        if not cmd_id:
            self.manual_log_output.append("[錯誤] Signal ID 不可為空。")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if hasattr(driver, "send_manual_command_detailed"):
                report = driver.send_manual_command_detailed(cmd_id)
            else:
                report = driver.send_manual_command(cmd_id)
        finally:
            QApplication.restoreOverrideCursor()
        self.manual_log_output.append(report)
        self.manual_log_output.append("")

    def load_settings(self, settings):
        """Load chamber settings from config_settings.json."""
        chamber_conf = settings.get("CHAMBER_CONFIG", {}) if isinstance(settings, dict) else {}
        self._scan_chamber_ports()
        self._set_selected_port(chamber_conf.get("PORT", ""))
        self.chamber_id_spin.setValue(int(chamber_conf.get("ID", 1)))
        self.chamber_baud_combo.setCurrentText(str(chamber_conf.get("BAUDRATE", 9600)))

    def get_settings(self):
        """Return chamber settings for persistence."""
        return {
            "PORT": self._get_selected_port(),
            "ID": self.chamber_id_spin.value(),
            "BAUDRATE": int(self.chamber_baud_combo.currentText()),
        }

    def set_visibility(self, visible):
        """Start polling only while the tab is visible and serial is open."""
        self._polling_visible = bool(visible)
        driver = getattr(self.engine, "chamber_driver", None)
        if self._polling_visible and driver and driver.is_connected() and not self._manual_input_pause_timer.isActive():
            self.chamber_update_timer.start()
        else:
            self.chamber_update_timer.stop()

    def cleanup(self):
        """Stop timer on dialog close."""
        self.chamber_update_timer.stop()
        self._manual_input_pause_timer.stop()

    def _pause_polling_for_manual_input(self):
        """Pause synchronous chamber polling while the operator edits setpoints.

        Rapid spin-box arrow clicks can otherwise compete with serial telemetry
        polling on the GUI thread.  The manual input remains local until the
        operator presses ``傳送設定``; polling resumes shortly after editing stops.
        """
        self.chamber_update_timer.stop()
        self._manual_input_pause_timer.start()

    def _resume_polling_after_manual_input(self):
        """Resume chamber polling after a quiet period following manual edits."""
        driver = getattr(self.engine, "chamber_driver", None)
        if self._polling_visible and driver and driver.is_connected():
            self.chamber_update_timer.start()

    def _test_chamber_connection(self):
        """Open serial port and require readable PV/SV telemetry for success."""
        driver = getattr(self.engine, "chamber_driver", None)
        if not driver:
            QMessageBox.critical(self, "失敗", "engine.chamber_driver 不存在。")
            return

        port = self._get_selected_port()
        station_id = self.chamber_id_spin.value()
        baud_rate = int(self.chamber_baud_combo.currentText())
        if not port:
            QMessageBox.warning(self, "錯誤", "請先選擇一個 COM Port！")
            return

        driver.disconnect()
        driver.station_id = str(station_id).zfill(2)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            serial_ok = driver.connect(port, baudrate=baud_rate)
            if serial_ok:
                telemetry_ok, status, diagnostic = driver.test_telemetry(probe_all=True)
            else:
                telemetry_ok, status, diagnostic = False, None, getattr(driver, "last_error", "Serial open failed")
        finally:
            QApplication.restoreOverrideCursor()

        self.manual_log_output.append(diagnostic)
        self.manual_log_output.append("")

        if telemetry_ok and status:
            QMessageBox.information(
                self,
                "成功",
                f"成功讀取溫濕度箱 telemetry (ID: {station_id})。\n"
                f"PV: {status['temp_pv']:.1f} °C / {status['hum_pv']:.1f} %\n"
                f"FCS mode: {getattr(driver, 'fcs_mode', '-')}",
            )
            self._apply_status(status)
            self.chamber_update_timer.start()
        else:
            self._show_error_status()
            self.chamber_update_timer.stop()
            QMessageBox.critical(
                self,
                "失敗",
                f"{port} 已開啟，但沒有讀到可解析的溫濕度 PV/SV。\n\n"
                "請檢查站號、RS485 A/B、Chamber 通訊啟用/Remote 設定，以及手冊 FCS 計算方式。\n"
                "下方手動除錯終端已輸出 TX/RX ASCII 與 HEX。",
            )

    @staticmethod
    def _is_number(value):
        """Return True when a chamber telemetry value can be formatted numerically.

        Args:
            value: Raw telemetry value from ``ChamberDriver.read_status()``.

        Returns:
            True if ``value`` is not None and can be converted to float.
        """
        if value is None:
            return False
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False

    @classmethod
    def _format_status_value(cls, value, suffix: str, missing_text: str) -> str:
        """Format a chamber status value without changing manual setpoint inputs.

        Args:
            value: Numeric status value or None when the chamber reports an unused
                analog field such as ``7FFF``.
            suffix: Unit suffix displayed after the numeric value.
            missing_text: Text used when the value is not available.

        Returns:
            Safe display text for a telemetry label.
        """
        if not cls._is_number(value):
            return missing_text
        return f"{float(value):.1f}{suffix}"

    def _apply_status(self, status):
        """Render chamber PV/SV readback labels without mutating manual inputs.

        The manual target temperature/humidity spin boxes are operator-owned input
        fields.  Periodic telemetry polling must update only the readback labels;
        otherwise the target field appears to follow the present chamber value and
        can mislead the operator before pressing ``傳送設定``.
        """
        self.temp_pv_label.setText(self._format_status_value(status.get('temp_pv'), " °C", "ERR °C"))
        self.temp_sv_label.setText(self._format_status_value(status.get('temp_sv'), " °C", "--.- °C"))
        self.hum_pv_label.setText(self._format_status_value(status.get('hum_pv'), " %", "ERR %"))
        self.hum_sv_label.setText(self._format_status_value(status.get('hum_sv'), " %", "--.- %"))

    def _show_error_status(self):
        """Render chamber telemetry error state."""
        self.temp_pv_label.setText("ERR °C")
        self.temp_sv_label.setText("--.- °C")
        self.hum_pv_label.setText("ERR %")
        self.hum_sv_label.setText("--.- %")

    def _update_chamber_status(self):
        """Poll chamber status while the tab is visible and not being edited."""
        if self._poll_in_progress or self._manual_input_pause_timer.isActive():
            return
        driver = getattr(self.engine, "chamber_driver", None)
        if driver and driver.is_connected():
            self._poll_in_progress = True
            try:
                status = driver.read_status()
                if status:
                    self._apply_status(status)
                else:
                    self._show_error_status()
            finally:
                self._poll_in_progress = False

    def _send_chamber_setpoints(self):
        """Write manual temperature/humidity setpoints."""
        driver = getattr(self.engine, "chamber_driver", None)
        if not driver or not driver.is_connected():
            QMessageBox.warning(self, "錯誤", "溫濕度箱未連接！")
            return

        current_status = driver.read_status()
        old_t, old_h = ("N/A", "N/A")
        if current_status:
            old_t, old_h = current_status['temp_sv'], current_status['hum_sv']

        new_t = self.temp_sv_spin.value()
        new_h = self.hum_sv_spin.value()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            success = driver.write_setpoints(new_t, new_h)
        finally:
            QApplication.restoreOverrideCursor()

        if success:
            reason = "使用者手動設定"
            if getattr(self.engine, "log_mgr", None):
                self.engine.log_mgr.log_config_change(
                    "[ENV] Chamber SV", f"{old_t}/{old_h}", f"{new_t}/{new_h}", reason
                )
            QMessageBox.information(self, "成功", "設定值已傳送。")
            QTimer.singleShot(500, self._update_chamber_status)
        else:
            detail = str(getattr(driver, "last_error", "") or "未提供錯誤摘要，請查看 logs。")
            QMessageBox.critical(
                self,
                "失敗",
                "傳送設定值失敗！\n\n"
                f"原因摘要：{detail}\n\n"
                "完整 TX/RX ASCII、TX/RX HEX、FCS、timeout 與 protocol 診斷已寫入 logs。",
            )
