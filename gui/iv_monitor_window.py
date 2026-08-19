"""
[修改紀錄 by Gemini on 2026-03-18]
- 新增功能 (儲存格式): 擴充「儲存圖表」功能，支援 PNG, JPG, TIFF, BMP 等多種格式。

[修改紀錄 by ChatGPT on 2026-03-25]
- 新增功能 (圖表設定): 新增「圖表設定...」按鈕，可呼叫 IVPlotSettingsDialog。
- 新增功能 (即時套用): 對話框中的 settings_applied 會即時套用到 IVPlotWidget。
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QScrollArea,
    QPushButton,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QCloseEvent

import config
from .widgets.iv_plot_widget import IVPlotWidget
from .widgets.iv_meta_widget import IVMetaWidget
from .widgets.iv_analysis_widget import IVAnalysisWidget
from .widgets.iv_plot_settings_dialog import IVPlotSettingsDialog

try:
    from pyqtgraph.exporters import ImageExporter
    _HAS_PYQTGRAPH = True
except ImportError:
    _HAS_PYQTGRAPH = False

logger = logging.getLogger(__name__)


class IVMonitorWindow(QWidget):
    """
    A container window that assembles the IV plot, metadata, and analysis
    widgets into a single, cohesive interface. It acts as a command center,
    delegating data to the appropriate sub-widget.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ReliabilityX Pro - 實時 IV 曲線戰情室")
        self.setMinimumSize(1200, 800)

        self._last_area = 1.0
        self._plot_settings_dialog = None

        self._init_ui()
        self._connect_signals()
        self.clear_buffer()

    def closeEvent(self, event: QCloseEvent):
        """
        Overrides the default close event to hide the window instead of closing it,
        preserving its state.
        """
        self.hide()
        event.ignore()

    def _sanitize_name(self, name, max_len=50):
        """Helper to create valid path components from user input."""
        if not isinstance(name, str):
            name = str(name)
        name = re.sub(r'[\\/:*?"<>| ]', "_", name)
        name = re.sub(r"[^\w\u4e00-\u9fff.-]", "", name)
        name = re.sub(r"_+", "_", name)
        name = name[:max_len]
        name = name.strip("._ ")
        return name or "unnamed_item"

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left side: Plotting Widget
        self.plot_widget = IVPlotWidget()
        splitter.addWidget(self.plot_widget)

        # Right side: Scrollable Information Panel
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        right_container = QWidget()
        scroll_area.setWidget(right_container)
        self.right_layout = QVBoxLayout(right_container)

        # --- Error Notification Area ---
        self.lbl_error = QLabel("HARDWARE FAILURE - CHECK LOGS")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setStyleSheet(
            "background-color: #D32F2F; color: white; font-weight: bold; "
            "font-size: 14pt; padding: 8px; border-radius: 4px;"
        )
        self.lbl_error.hide()
        self.right_layout.addWidget(self.lbl_error)

        # --- Metadata and Analysis Widgets ---
        self.meta_widget = IVMetaWidget()
        self.analysis_widget = IVAnalysisWidget()

        self.right_layout.addWidget(self.meta_widget)
        self.right_layout.addWidget(self.analysis_widget)
        self.right_layout.addStretch()

        # --- Buttons ---
        button_layout = QHBoxLayout()

        self.btn_plot_settings = QPushButton("圖表設定...")
        self.btn_save_plot = QPushButton("儲存圖表...")

        button_layout.addWidget(self.btn_plot_settings)
        button_layout.addWidget(self.btn_save_plot)

        self.right_layout.addLayout(button_layout)

        splitter.addWidget(scroll_area)
        splitter.setSizes([700, 500])

    def _connect_signals(self):
        """Connects signals for the widgets in this window."""
        self.btn_save_plot.clicked.connect(self._on_save_plot_clicked)
        self.btn_plot_settings.clicked.connect(self._on_plot_settings_clicked)

    @pyqtSlot()
    def _on_plot_settings_clicked(self):
        """
        Opens the IV plot settings dialog and connects its applied settings
        to the current plot widget.
        """
        try:
            current_settings = self.plot_widget.get_current_plot_settings()
        except Exception as e:
            logger.warning("無法從 plot_widget 取得目前設定，改用預設流程開啟 dialog: %s", e)
            current_settings = None

        dlg = IVPlotSettingsDialog(settings=current_settings, parent=self)
        dlg.settings_applied.connect(self.plot_widget.apply_plot_settings)

        # 保存 reference，避免在某些情況下被提早回收
        self._plot_settings_dialog = dlg
        dlg.exec()
        self._plot_settings_dialog = None

    @pyqtSlot()
    def _on_save_plot_clicked(self):
        if not _HAS_PYQTGRAPH:
            QMessageBox.warning(self, "功能缺失", "未找到 pyqtgraph 函式庫，無法匯出圖表。")
            return

        plot_item = self.plot_widget.get_plot_item()
        if plot_item is None:
            QMessageBox.warning(self, "錯誤", "無法獲取圖表物件，無法匯出。")
            return

        try:
            # --- Create a descriptive default filename ---
            ch_id_str = self.meta_widget.meta_labels["Channel"].text()
            dev_name = self.meta_widget.meta_labels["Device"].text()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            try:
                ch_id = int(ch_id_str)
                ch_str = f"CH{ch_id:02d}"
            except (ValueError, TypeError):
                ch_str = "CH_XX"

            dev_str = (
                self._sanitize_name(dev_name)
                if dev_name and dev_name != "--"
                else "UnknownDevice"
            )

            default_format = "png"
            default_filename = f"IV_Curve_{ch_str}_{dev_str}_{timestamp}.{default_format}"

            file_filter = (
                "PNG 圖片 (*.png);;"
                "JPEG 圖片 (*.jpg);;"
                "TIFF 圖片 (*.tif);;"
                "BMP 圖片 (*.bmp);;"
                "所有檔案 (*)"
            )

            fileName, _ = QFileDialog.getSaveFileName(
                self,
                "儲存 IV 曲線圖",
                default_filename,
                file_filter,
            )

            if fileName:
                exporter = ImageExporter(plot_item)
                exporter.export(fileName)
                QMessageBox.information(self, "成功", f"圖表已成功儲存至:\n{fileName}")

        except Exception as e:
            logger.error("儲存 IV 曲線圖失敗: %s", e)
            QMessageBox.critical(self, "錯誤", f"儲存圖表時發生錯誤:\n{e}")

    @pyqtSlot()
    def clear_buffer(self):
        """Clears the display by calling the clear methods of child widgets."""
        if hasattr(self, "lbl_error"):
            self.lbl_error.hide()

        if hasattr(self, "plot_widget"):
            self.plot_widget.clear_plot()
        if hasattr(self, "meta_widget"):
            self.meta_widget.clear()
        if hasattr(self, "analysis_widget"):
            self.analysis_widget.clear()

    @pyqtSlot(dict)
    def prepare_for_scan(self, config_data):
        """
        Pre-loads metadata for an upcoming scan. This method enriches the
        config data with predicted path and calibrated resistance before display.
        """
        self.clear_buffer()

        # --- Enrich config_data with R_line and predicted path ---

        # 1. Retrieve Line Resistance
        pos = config_data.get("relay_pos")
        neg = config_data.get("relay_neg")
        if pos is not None and neg is not None:
            cal_settings = config.load_json_file(config.CALIBRATION_SETTINGS_FILE)
            cal_map = cal_settings.get("line_resistance_map", {})
            key = f"{pos}_{neg}"
            res_info = cal_map.get(key)

            if isinstance(res_info, dict):
                config_data["line_res"] = res_info.get("value")
                config_data["line_res_date"] = res_info.get("time", "")
            elif isinstance(res_info, (int, float)):
                config_data["line_res"] = res_info
                config_data["line_res_date"] = "N/A"

        # 2. Predict Save Path
        user = self._sanitize_name(config_data.get("user", "default_user"))
        project = self._sanitize_name(config_data.get("project", "default_project"))
        device = self._sanitize_name(config_data.get("device_name", "Device"))

        predicted_path = Path("data") / user / project / device
        config_data["file_path"] = str(predicted_path) + "/"

        # --- Update UI ---
        self.meta_widget.update_metadata(config_data)

        # Cache the area for the upcoming plot's Jsc calculation
        self._last_area = config_data.get("area", 1.0)

    @pyqtSlot(dict)
    def update_plot(self, point):
        """
        Receives real-time point data and delegates it to the plot widget.
        It also injects the last known area for plotting mode conversions.
        """
        point_with_area = {**point, "area": self._last_area}
        self.plot_widget.update_plot(point_with_area)

    @pyqtSlot(dict)
    def show_final_params(self, results):
        """
        Receives the final results dictionary and delegates its parts to the
        metadata and analysis widgets.
        """
        # Cache the area for the next plot's Jsc calculation
        self._last_area = results.get("area", 1.0)

        # Delegate data to child widgets
        self.meta_widget.update_metadata(results)
        self.analysis_widget.update_results(results)

    @pyqtSlot(dict)
    def handle_status_update(self, status_data):
        """Receives all status updates and shows an error if one occurs."""
        message = status_data.get("message", "").upper()
        if "FAIL" in message or "ERROR" in message:
            error_text = f"錯誤: {status_data.get('message', 'Unknown')}"
            self.lbl_error.setText(error_text)
            self.lbl_error.show()
            logger.error("IVMonitor received hardware failure status: %s", error_text)