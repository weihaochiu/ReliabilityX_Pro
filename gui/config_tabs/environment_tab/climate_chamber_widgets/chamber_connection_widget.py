"""gui/config_tabs/environment_tab/climate_chamber_widgets/chamber_connection_widget.py

Chamber diagnostics update (202606021545):
- Display full COM-port descriptions such as ``CMS/ITRI USB to RS485 (COM8)``.
- Treat telemetry readback as the required success condition for connection tests.
- Show the fixed chamber serial contract from the manual: RS-485 ASCII, 9600 8E1,
  TX CR+LF, RX CR, Signal 01 analog data.
"""

from __future__ import annotations

import serial.tools.list_ports

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
)


class ChamberConnectionWidget(QGroupBox):
    """Connection widget for the climate chamber."""

    scan_ports_requested = pyqtSignal()
    test_connection_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        """Create the connection widget."""
        super().__init__("連線設定", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build connection controls."""
        conn_layout = QFormLayout(self)

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

        self.protocol_hint = QLabel("RS-485 ASCII | 9600 bps | 8E1 | TX=CR+LF | RX=CR | Signal 01=Analog PV/SV")
        self.protocol_hint.setWordWrap(True)
        self.protocol_hint.setStyleSheet("color: #D6E4FF; font-weight: 600; padding: 4px;")

        conn_btn_layout = QHBoxLayout()
        self.btn_scan_ports = QPushButton("🔄 掃描 Port")
        self.btn_test_connection = QPushButton("🔗 測試連線")
        conn_btn_layout.addWidget(self.btn_scan_ports)
        conn_btn_layout.addWidget(self.btn_test_connection)

        conn_layout.addRow("COM Port/Baud:", port_baud_layout)
        conn_layout.addRow("站號 (ID):", self.chamber_id_spin)
        conn_layout.addRow("通訊規格:", self.protocol_hint)
        conn_layout.addRow(conn_btn_layout)

        self.btn_scan_ports.clicked.connect(self.scan_ports_requested.emit)
        self.btn_test_connection.clicked.connect(self.test_connection_requested.emit)

    def _port_label(self, port_info) -> str:
        """Return an operator-readable COM-port label."""
        desc = port_info.description or "Serial Port"
        if port_info.device in desc:
            return desc
        return f"{desc} ({port_info.device})"

    def scan_ports(self) -> None:
        """Populate all available COM ports with device descriptions."""
        current = self.get_port()
        self.chamber_port_combo.clear()
        for item in serial.tools.list_ports.comports():
            self.chamber_port_combo.addItem(self._port_label(item), item.device)
        if current:
            self.set_port(current)

    def get_port(self) -> str:
        """Return the selected raw COM port value."""
        data = self.chamber_port_combo.currentData()
        if data:
            return str(data)
        text = self.chamber_port_combo.currentText().strip()
        if "(" in text and text.endswith(")"):
            return text.rsplit("(", 1)[-1].rstrip(")")
        return text

    def set_port(self, port: str) -> None:
        """Select a raw COM port, adding it if it is not currently visible."""
        port = str(port or "").strip()
        if not port:
            return
        for idx in range(self.chamber_port_combo.count()):
            if str(self.chamber_port_combo.itemData(idx)) == port:
                self.chamber_port_combo.setCurrentIndex(idx)
                return
        self.chamber_port_combo.addItem(port, port)
        self.chamber_port_combo.setCurrentIndex(self.chamber_port_combo.count() - 1)

    def set_connection_values(self, port: str, station_id: int, baudrate: int) -> None:
        """Apply connection values loaded from settings."""
        self.set_port(port)
        self.chamber_id_spin.setValue(int(station_id))
        self.chamber_baud_combo.setCurrentText(str(baudrate))

    def test_connection_with_driver(self, driver) -> tuple[bool, str]:
        """Execute serial-open plus telemetry-read test through the driver."""
        port = self.get_port()
        station_id = self.chamber_id_spin.value()
        baud_rate = int(self.chamber_baud_combo.currentText())

        if not port:
            return False, "請先選擇一個 COM Port！"

        driver.disconnect()
        driver.station_id = str(station_id).zfill(2)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            serial_ok = driver.connect(port, baudrate=baud_rate)
            if not serial_ok:
                return False, f"無法開啟 {port}。請檢查 USB-RS485 driver、port 是否被其他軟體占用。"
            telemetry_ok, status, diagnostic = driver.test_telemetry(probe_all=True)
        finally:
            QApplication.restoreOverrideCursor()

        if telemetry_ok and status:
            return True, (
                f"成功讀取溫濕度箱 telemetry (ID: {station_id})。\n"
                f"PV: {status.get('temp_pv'):.1f} °C / {status.get('hum_pv'):.1f} %\n"
                f"FCS mode: {getattr(driver, 'fcs_mode', '-') }"
            )
        return False, (
            f"{port} 已開啟，但未讀到可解析的溫濕度 PV/SV。\n\n"
            "請檢查站號、RS485 A/B、Chamber 通訊啟用/Remote 設定，以及手冊 FCS 計算方式。\n\n"
            f"{diagnostic}"
        )

    def show_connection_result(self, ok: bool, message: str) -> None:
        """Show connection test result to the user."""
        if ok:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.critical(self, "失敗", message)
