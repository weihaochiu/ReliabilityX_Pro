from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, 
                             QComboBox, QPushButton, QLabel, QGridLayout,
                             QMessageBox, QApplication)
from PyQt6.QtCore import QTimer, Qt
from driver.smu_driver import SMUDriver

class SMUTab(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(1000)
        
        self.init_ui()
        self.smu_interface_combo.currentTextChanged.connect(self._on_interface_changed)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # SMU Settings
        smu_group = QGroupBox("SMU 設定")
        smu_form = QFormLayout(smu_group)
        self.smu_interface_combo = QComboBox()
        self.smu_interface_combo.addItems(["GPIB", "LAN", "USB"])
        self.smu_addr_combo = QComboBox()
        self.smu_addr_combo.setEditable(True)
        smu_scan_btn = QPushButton("🔄 掃描 GPIB/USB 設備")
        smu_scan_btn.clicked.connect(self._scan_visa_resources)
        
        smu_form.addRow("連線模式:", self.smu_interface_combo)
        smu_form.addRow("位址 (IP/VISA):", self.smu_addr_combo)
        smu_form.addRow(smu_scan_btn)
        smu_form.addRow("SMU NPLC:", self._create_nplc_combo())
        layout.addWidget(smu_group)

        # SMU Diagnostics
        diag_group = QGroupBox("SMU 狀態診斷 (Diagnostic Dashboard)")
        diag_layout = QVBoxLayout(diag_group)

        # Verification line
        verify_layout = QHBoxLayout()
        btn_verify_idn = QPushButton("🔍 驗證設備連線 (*IDN?)")
        btn_verify_idn.clicked.connect(self._verify_idn)
        self.lbl_idn_result = QLabel("等待驗證...")
        self.lbl_idn_result.setObjectName("lbl_idn_result")
        verify_layout.addWidget(btn_verify_idn)
        verify_layout.addWidget(self.lbl_idn_result, 1)
        diag_layout.addLayout(verify_layout)
        
        # Digital Display
        display_layout = QGridLayout()
        self.v_display = QLabel("00.000 V")
        self.v_display.setProperty("class", "display")
        self.v_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.i_display = QLabel("0.000e-00 A")
        self.i_display.setProperty("class", "display")
        self.i_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.output_toggle_btn = QPushButton("OUTPUT OFF")
        self.output_toggle_btn.setObjectName("output_toggle_btn")
        self.output_toggle_btn.setCheckable(True)
        self.output_toggle_btn.clicked.connect(self._toggle_output)

        self.read_now_btn = QPushButton("🔍 立即讀取數據 (診斷)")
        self.read_now_btn.setObjectName("read_now_btn")
        self.read_now_btn.clicked.connect(self._update_dashboard)

        display_layout.addWidget(QLabel("電壓 (V)"), 0, 0)
        display_layout.addWidget(QLabel("電流 (I)"), 0, 1)
        display_layout.addWidget(self.v_display, 1, 0)
        display_layout.addWidget(self.i_display, 1, 1)
        display_layout.addWidget(self.output_toggle_btn, 2, 0, 1, 2)
        display_layout.addWidget(self.read_now_btn, 3, 0, 1, 2)

        diag_layout.addLayout(display_layout)
        layout.addWidget(diag_group)
        layout.addStretch()

    def _on_interface_changed(self, interface):
        self.smu_addr_combo.clearEditText()
        if interface == "LAN":
            self.smu_addr_combo.setPlaceholderText("請輸入或掃描 LAN VISA 位址")
        elif interface == "USB":
            self.smu_addr_combo.setPlaceholderText("可留白以自動偵測")
        elif interface == "GPIB":
            self.smu_addr_combo.setPlaceholderText("請輸入或掃描 GPIB 位址")

    def _create_nplc_combo(self):
        self.combo_nplc = QComboBox()
        self.combo_nplc.addItems(["0.01", "0.1", "1.0", "10.0"])
        return self.combo_nplc
    
    def cleanup(self):
        self.monitor_timer.stop()
        
    def set_visibility(self, visible):
        self.monitor_timer.stop()
        if visible:
            if self.engine and self.engine.smu and self.engine.smu.is_connected:
                self._update_idn_label()
                is_on = self.engine.smu.is_output_on()
                self.output_toggle_btn.setChecked(is_on)
                self.output_toggle_btn.setText("OUTPUT ON" if is_on else "OUTPUT OFF")

    def _update_dashboard(self):
        if not self.engine or not self.engine.smu or not self.engine.smu.is_connected:
            QMessageBox.warning(self, "錯誤", "SMU 未連線，無法讀取數據。請在主視窗連線硬體。")
            return
        
        original_text = self.read_now_btn.text()
        try:
            self.read_now_btn.setEnabled(False)
            self.read_now_btn.setText("⏳ 正在讀取...")
            QApplication.processEvents()

            v, i = self.engine.smu.read_vi()
            self.v_display.setText(f"{v:08.3f} V")
            self.i_display.setText(f"{i:.3e} A")
            
        finally:
            self.read_now_btn.setEnabled(True)
            self.read_now_btn.setText(original_text)

    def _verify_idn(self):
        if not self.engine or not self.engine.smu or not self.engine.smu.is_connected:
            QMessageBox.warning(self, "錯誤", "SMU 未連線。請在主視窗連線硬體。")
            return
        self._update_idn_label()

    def _update_idn_label(self):
        idn = self.engine.smu.get_idn()
        status = "success"
        if not idn or "查詢失敗" in idn or "未連線" in idn:
            idn = "查詢失敗或未連線"
            status = "fail"
        
        self.lbl_idn_result.setText(idn)
        self.lbl_idn_result.setProperty("status", status)
        self.lbl_idn_result.style().unpolish(self.lbl_idn_result)
        self.lbl_idn_result.style().polish(self.lbl_idn_result)

    def _toggle_output(self):
        if not self.engine or not self.engine.smu or not self.engine.smu.is_connected:
            QMessageBox.warning(self, "錯誤", "SMU 未連線。")
            self.output_toggle_btn.setChecked(False)
            return

        is_on = self.output_toggle_btn.isChecked()
        self.engine.smu.output_control(is_on)
        self.output_toggle_btn.setText("OUTPUT ON" if is_on else "OUTPUT OFF")

    def _scan_visa_resources(self):
        self.smu_addr_combo.clear()
        try:
            resources = SMUDriver.list_available_resources()
            if resources:
                self.smu_addr_combo.addItems(resources)
            else:
                QMessageBox.information(self, "掃描結果", "未發現任何 VISA 設備。")
        except Exception as e:
            QMessageBox.critical(self, "掃描失敗", f"掃描 VISA 設備時發生錯誤: {e}")

    def load_settings(self, settings):
        smu_conf = settings.get("SMU_CONFIG", {})
        self.smu_interface_combo.setCurrentText(smu_conf.get("INTERFACE_TYPE", "USB"))
        self.smu_addr_combo.setCurrentText(smu_conf.get("VISA_ADDRESS", ""))
        self.combo_nplc.setCurrentText(str(smu_conf.get("DEFAULT_NPLC", 1.0)))
        self._on_interface_changed(self.smu_interface_combo.currentText())

    def get_settings(self):
        return {
            "INTERFACE_TYPE": self.smu_interface_combo.currentText(),
            "VISA_ADDRESS": self.smu_addr_combo.currentText(),
            "DEFAULT_NPLC": float(self.combo_nplc.currentText())
        }
