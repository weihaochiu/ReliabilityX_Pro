"""
[修改紀錄 by Gemini on 2026-03-16]
- 新增 'exit_requested' 信號與對應的 '安全關閉程式' 按鈕。
- 使用者點擊此按鈕將發送信號，由主視窗接收以執行安全關閉程序。

[修改紀錄 by ChatGPT on 2026-03-26]
- 新增 'show_iv_trend_requested' 信號。
- 在「系統管理」中新增「開啟 IV / TREND 視窗」按鈕。
- 此按鈕只負責通知主視窗開啟或喚回 IV Monitor 與 Trend Chart，不直接建立視窗。

[修改紀錄 by ChatGPT on 2026-03-26 - Logo 等比例修正]
- 修正左上角 Logo 會隨容器被不等比例放大的問題。
- 改為依 lbl_logo_top 可用區域進行等比例縮放。
- 增加 Logo 顯示區的高度限制與置中設定，避免被 layout 異常撐大。

[修改紀錄 by ChatGPT on 2026-05-14 - 全域循環量測控制]
- 將左側全域控制按鈕改名為「啟動全部循環量測」與「停止全部循環量測」。
- 新增全域排程狀態列，顯示停止中、排程執行中、量測中、安全停止中或錯誤停止。
"""
import os
import logging

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QGridLayout,
    QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont, QPixmap

# 取得日誌實例
logger = logging.getLogger("ReliabilityX_Pro")


class ControlPanel(QWidget):
    """
    ReliabilityX Pro 控制面板組件

    v2.3.0:
    - 新增可喚回 IV Monitor 與 Trend Chart 的按鈕。
    - 修正 Logo 顯示為等比例縮放，避免變形。
    """

    start_scan_requested = pyqtSignal()
    stop_scan_requested = pyqtSignal()
    reinit_hw_requested = pyqtSignal()
    sys_config_requested = pyqtSignal()
    show_iv_trend_requested = pyqtSignal()
    show_logs_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None  # 緩存原始圖片避免重複讀取
        self._init_ui()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)

        # --- CSET Logo 容器 ---
        self.lbl_logo_top = QLabel()
        self.lbl_logo_top.setObjectName("lbl_logo_top")
        self.lbl_logo_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo_top.setScaledContents(False)
        self.lbl_logo_top.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.lbl_logo_top.setMinimumHeight(120)
        self.lbl_logo_top.setMaximumHeight(260)

        # control_panel.py 位於 gui/widgets/，logo 位於 gui/cset_logo.png
        logo_path = os.path.join(os.path.dirname(__file__), "..", "cset_logo.png")

        if os.path.exists(logo_path):
            self.original_pixmap = QPixmap(logo_path)
            self._update_logo_pixmap()
        else:
            self.lbl_logo_top.setText("CSET Logo")
            logger.warning(f"找不到 Logo 檔案: {logo_path}")

        self.main_layout.addWidget(self.lbl_logo_top)

        # --- 硬體連線狀態 ---
        self.status_group = QGroupBox("硬體連線狀態")
        status_layout = QVBoxLayout(self.status_group)

        smu_layout, self.smu_status_indicator, self.smu_status_label = self._create_status_line("SMU")
        relay_layout, self.relay_status_indicator, self.relay_status_label = self._create_status_line("Relay")
        chamber_layout, self.chamber_status_indicator, self.chamber_status_label = self._create_status_line("Chamber")

        status_layout.addLayout(smu_layout)
        status_layout.addLayout(relay_layout)
        status_layout.addLayout(chamber_layout)

        btn_reinit_hw = QPushButton("🔄 重新偵測硬體")
        btn_reinit_hw.clicked.connect(self.reinit_hw_requested.emit)
        status_layout.addWidget(btn_reinit_hw)

        self.main_layout.addWidget(self.status_group)

        # --- 系統控制 ---
        ctrl_group = QGroupBox("系統控制")
        ctrl_layout = QVBoxLayout(ctrl_group)

        self.btn_start = QPushButton("▶ 啟動全部循環量測")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self.start_scan_requested.emit)

        self.btn_stop = QPushButton("⏸ 停止全部循環量測")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.clicked.connect(self.stop_scan_requested.emit)
        self.btn_stop.setEnabled(False)

        self.lbl_scheduler_status = QLabel("目前狀態：停止中")
        self.lbl_scheduler_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_scheduler_status.setWordWrap(True)
        self.lbl_scheduler_status.setProperty("status", "idle")

        ctrl_layout.addWidget(self.btn_start)
        ctrl_layout.addWidget(self.btn_stop)
        ctrl_layout.addWidget(self.lbl_scheduler_status)
        self.main_layout.addWidget(ctrl_group)

        # --- 環境監控 ---
        env_group = QGroupBox("環境監控")
        env_layout = QGridLayout(env_group)

        self.lbl_temp_pv = QLabel("--.- °C")
        self.lbl_temp_pv.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        self.lbl_temp_pv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_temp_pv.setProperty("env", "temp")

        self.lbl_hum_pv = QLabel("--.- %")
        self.lbl_hum_pv.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        self.lbl_hum_pv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hum_pv.setProperty("env", "hum")

        env_layout.addWidget(QLabel("溫度 (PV)"), 0, 0)
        env_layout.addWidget(QLabel("濕度 (PV)"), 0, 1)
        env_layout.addWidget(self.lbl_temp_pv, 1, 0)
        env_layout.addWidget(self.lbl_hum_pv, 1, 1)

        self.main_layout.addWidget(env_group)

        # --- 系統管理 ---
        mgmt_group = QGroupBox("系統管理")
        mgmt_layout = QVBoxLayout(mgmt_group)

        btn_config = QPushButton("⚙️ 系統全域設定")
        btn_config.clicked.connect(self.sys_config_requested.emit)

        btn_show_iv_trend = QPushButton("🪟 開啟 IV / TREND 視窗")
        btn_show_iv_trend.clicked.connect(self.show_iv_trend_requested.emit)

        btn_show_log = QPushButton("📜 查看日誌")
        btn_show_log.clicked.connect(self.show_logs_requested.emit)

        btn_exit = QPushButton("🛑 安全關閉程式")
        btn_exit.clicked.connect(self.exit_requested.emit)

        mgmt_layout.addWidget(btn_config)
        mgmt_layout.addWidget(btn_show_iv_trend)
        mgmt_layout.addWidget(btn_show_log)
        mgmt_layout.addWidget(btn_exit)

        self.main_layout.addWidget(mgmt_group)

        self.main_layout.addStretch()

        # --- 底部標籤 ---
        self.lbl_powered_by = QLabel("Powered by CSET, Chang Gung University")
        self.lbl_powered_by.setObjectName("lbl_powered_by")
        self.lbl_powered_by.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.lbl_powered_by)

    def _update_logo_pixmap(self):
        """
        依照 lbl_logo_top 自己目前可用的內容區域，做等比例縮放。
        """
        if self.original_pixmap is None or self.original_pixmap.isNull():
            return

        content_rect = self.lbl_logo_top.contentsRect()
        target_size = content_rect.size()

        if target_size.width() <= 0 or target_size.height() <= 0:
            return

        scaled_pixmap = self.original_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_logo_top.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        """
        當視窗大小改變時，自動觸發 Logo 的動態縮放並維持比例。
        """
        super().resizeEvent(event)
        self._update_logo_pixmap()

    def _create_status_line(self, name: str):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        indicator = QLabel("●")
        label = QLabel(f"{name}: 未連線")

        layout.addWidget(indicator)
        layout.addWidget(label)
        layout.addStretch()

        return layout, indicator, label

    def _update_status_label(self, indicator: QLabel, label: QLabel, name: str, is_ok: bool):
        status = "ok" if is_ok else "error"
        indicator.setProperty("status", status)
        ok_text = "已連線" if name != "Chamber" else "Telemetry OK"
        fail_text = "未連線" if name != "Chamber" else "Telemetry 未就緒"
        label.setText(f"{name}: {ok_text if is_ok else fail_text}")
        indicator.style().unpolish(indicator)
        indicator.style().polish(indicator)

    def set_hardware_status(self, smu_ok: bool, relay_ok: bool, chamber_ok: bool):
        self._update_status_label(self.smu_status_indicator, self.smu_status_label, "SMU", smu_ok)
        self._update_status_label(self.relay_status_indicator, self.relay_status_label, "Relay", relay_ok)
        self._update_status_label(self.chamber_status_indicator, self.chamber_status_label, "Chamber", chamber_ok)

    def update_env_data(self, temp: float | None, hum: float | None):
        if temp is not None:
            self.lbl_temp_pv.setText(f"{temp:.1f} °C")
        else:
            self.lbl_temp_pv.setText("ERR °C")

        if hum is not None:
            self.lbl_hum_pv.setText(f"{hum:.1f} %")
        else:
            self.lbl_hum_pv.setText("ERR %")

    def set_scheduler_status(self, text: str, status_level: str = "idle"):
        """Update the global cyclic-measurement scheduler status label.

        Args:
            text: User-facing scheduler state text.
            status_level: Semantic style key used by the global QSS
                ``QLabel[status=...]`` rules, such as ``idle``, ``ok``,
                ``info``, ``warning`` or ``error``.
        """
        self.lbl_scheduler_status.setText(f"目前狀態：{text}")
        self.lbl_scheduler_status.setProperty("status", status_level)
        self.lbl_scheduler_status.style().unpolish(self.lbl_scheduler_status)
        self.lbl_scheduler_status.style().polish(self.lbl_scheduler_status)

    def on_scan_started(self):
        """Reflect that the global scheduler has started."""
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.set_scheduler_status("量測排程執行中", "ok")

    def on_scan_finished(self):
        """Reflect that the global scheduler has stopped."""
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.set_scheduler_status("停止中", "idle")
