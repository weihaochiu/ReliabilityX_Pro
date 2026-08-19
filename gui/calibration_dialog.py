import json
import csv
import time
import datetime
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QWidget, QLabel, QPushButton, QProgressBar, 
                             QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt
import config

class CalibrationDialog(QDialog):
    """
    ReliabilityX Pro 系統量測校準精靈
    支援 32 通道個別校正、20 次精密採樣與歷史歷程紀錄 [cite: 223-224]
    """
    def __init__(self, measure_engine, log_manager, parent=None):
        super().__init__(parent)
        self.engine = measure_engine
        self.log_mgr = log_manager
        self.setWindowTitle("ReliabilityX Pro - 32通道科研級校準精靈")
        self.setMinimumSize(700, 550)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # --- 分頁 1: 零點校準 (Zero Cal) ---
        self.tab_zero = QWidget()
        self.setup_zero_ui()
        self.tabs.addTab(self.tab_zero, "零點電流校準 (Zero Cal)")

        # --- 分頁 2: 線阻校準 (Short Cal) ---
        self.tab_short = QWidget()
        self.setup_short_ui()
        self.tabs.addTab(self.tab_short, "線路電阻校準 (Short Cal)")

        layout.addWidget(self.tabs)

    def setup_zero_ui(self):
        """建置零點校準介面 (全域環境消除) [cite: 230-231]"""
        layout = QVBoxLayout(self.tab_zero)
        msg = ("<b>背景：</b>消除系統雜訊與繼電器板漏電流。<br>"
               "<b>警告：</b>請確保 32 個通道皆為<font color='red'>開路 (Open)</font>並處於<font color='blue'>避光環境</font> [cite: 236]內容。")
        layout.addWidget(QLabel(msg))

        self.btn_run_zero = QPushButton("執行 20 次精密採樣 (全域零點)")
        self.btn_run_zero.setObjectName("btn_run_zero")
        self.btn_run_zero.clicked.connect(self.run_zero_calibration)
        layout.addWidget(self.btn_run_zero)

        self.progress_zero = QProgressBar()
        layout.addWidget(self.progress_zero)
        
        self.lbl_zero_res = QLabel("狀態：待校準")
        layout.addWidget(self.lbl_zero_res)

    def setup_short_ui(self):
        """建置 32 通道個別線阻校準介面 [cite: 243-244]"""
        layout = QVBoxLayout(self.tab_short)
        layout.addWidget(QLabel("<b>目的：</b>修正 32 通道因路徑長度與接點電阻造成的壓降 (V_drop) [cite: 58-60]內容。"))

        # 通道顯示清單
        self.table_cal = QTableWidget(32, 3)
        self.table_cal.setHorizontalHeaderLabels(["通道", "最後校準值 (Ω)", "狀態"])
        self.table_cal.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i in range(32):
            self.table_cal.setItem(i, 0, QTableWidgetItem(f"CH {i+1:02d}"))
            self.table_cal.setItem(i, 1, QTableWidgetItem("--"))
        layout.addWidget(self.table_cal)

        btn_box = QHBoxLayout()
        self.btn_run_short = QPushButton("開始 32 通道批次校準")
        self.btn_run_short.clicked.connect(self.run_batch_short_calibration)
        btn_box.addWidget(self.btn_run_short)
        layout.addLayout(btn_box)

    # =================================================================
    # 核心校準邏輯
    # =================================================================

    def run_zero_calibration(self):
        """
        零點校準邏輯：20次採樣 + 統計分析 + 日誌備份 [cite: 232-235]
        """
        try:
            self.engine.relay.reset_all() # 確保所有通道斷開 [cite: 62, 233]
            time.sleep(0.5)
            
            samples = []
            for i in range(20):
                _, i_msd = self.engine.smu.measure_all()
                samples.append(i_msd)
                self.progress_zero.setValue(int((i+1)/20 * 100))
                time.sleep(0.1)

            avg_i = np.mean(samples)
            std_i = np.std(samples)
            
            # 1. 寫入 JSON (即時生效) [cite: 245-247]
            self.save_to_json("global_offset", {"avg": avg_i, "std": std_i})
            
            # 2. 寫入 system_event.log (紀錄 20 次採樣詳情) [cite: 88, 115]
            self.log_mgr.log_info(f"[CAL] Zero_Samples: {samples}")
            self.log_mgr.log_info(f"[CAL] Offset_Avg: {avg_i:.4e}, Std: {std_i:.4e}")

            # 3. 輸出歷史 CSV [cite: 185]
            self.append_history_csv("Zero_Calibration", avg_i, "A", f"Std: {std_i:.2e}")
            
            self.lbl_zero_res.setText(f"✅ 平均值: {avg_i*1e9:.3f} nA (Std: {std_i*1e9:.3f} nA)")
            QMessageBox.information(self, "完成", "零點校準已成功，最新參數已鎖定 [cite: 247]內容。")

        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"校準中斷: {e}")

    def run_batch_short_calibration(self):
        """
        32 通道批次線阻校準：
        模擬四線式量測，逐一計算 $R_{line} = V_{msd} / I_{src}$ [cite: 238, 242]
        """
        reply = QMessageBox.question(self, "確認", "請確保目前校準通道已「互夾 (Short)」，是否開始？")
        if reply == QMessageBox.StandardButton.No: return

        try:
            results = {}
            for ch in range(1, 33):
                # 冷切換序列 [cite: 73-76]
                self.engine.relay.switch_pair(ch, "ON")
                time.sleep(0.05) # 50ms 穩定延遲 [cite: 60, 211]
                
                # 施加 10mA 小電流測試
                self.engine.smu.configure_source_curr(0.01, v_limit=2.0)
                self.engine.smu.output_control("ON")
                time.sleep(0.2)
                
                v_msd, _ = self.engine.smu.measure_all()
                
                # 安全斷開機制 (避免開路高壓) 
                if v_msd > 1.5:
                    self.engine.smu.output_control("OFF")
                    self.engine.relay.reset_all()
                    raise Exception(f"CH {ch} 電壓異常 (> 1.5V)，可能未正確互夾！")
                
                r_line = v_msd / 0.01
                results[str(ch)] = r_line
                
                # 更新 UI 表格
                self.table_cal.setItem(ch-1, 1, QTableWidgetItem(f"{r_line:.3f}"))
                self.table_cal.scrollToItem(self.table_cal.item(ch-1, 0))
                
                self.engine.smu.output_control("OFF")
                self.engine.relay.switch_pair(ch, "OFF")

            self.save_to_json("per_channel_r_line", results)
            self.append_history_csv("Batch_Short_Cal", np.mean(list(results.values())), "Ohm", "32-Ch Average")
            QMessageBox.information(self, "完成", "32 通道個別線阻校準已存檔。")

        except Exception as e:
            QMessageBox.critical(self, "中止", str(e))

    def save_to_json(self, key, value):
        """儲存至 calibration_settings.json [cite: 245-246]"""
        path = config.CALIBRATION_SETTINGS_FILE
        data = {}
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        data[key] = value
        data["operator"] = config.DEFAULT_USERNAME or "local_operator"
        data["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def append_history_csv(self, cal_type, value, unit, note=""):
        """輸出校準歷史紀錄 CSV，供多次校準對比 [cite: 177, 185]"""
        history_file = config.BASE_CONFIG_DIR / "calibration_history.csv"
        exists = history_file.exists()
        with open(history_file, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["Time", "Operator", "Type", "Value", "Unit", "Note"])
            writer.writerow([
                datetime.datetime.now().isoformat(),
                config.DEFAULT_USERNAME or "local_operator",
                cal_type,
                f"{value:.6e}",
                unit,
                note,
            ])
