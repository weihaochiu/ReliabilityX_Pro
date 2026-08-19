"""
IVAnalysisWidget: A widget for displaying IV analysis results in a table.
"""
import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt6.QtCore import pyqtSlot, Qt

from core.measurement_schema import IV_PARAMETER_KEYS, SUMMARY_SUB_HEADERS
from core.numeric_utils import parse_float_or_none

logger = logging.getLogger(__name__)

class IVAnalysisWidget(QWidget):
    """
    專業版 IV 分析結果顯示組件。
    確保電流 (mA) 與電流密度 (mA/cm²) 與存檔報表完全對齊。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        param_group = QGroupBox("分析結果矩陣")
        param_group.setStyleSheet("""
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
        """)
        param_layout = QVBoxLayout(param_group)
        
        # 建立表格：11 列參數, 4 欄維度
        self.table = QTableWidget(11, 4)
        self.table.setHorizontalHeaderLabels(["Forward Raw", "Reversed Raw", "Forward Corr", "Reversed Corr"])
        
        params_labels = SUMMARY_SUB_HEADERS
        self.table.setVerticalHeaderLabels(params_labels)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        param_layout.addWidget(self.table)
        layout.addWidget(param_group)

    @pyqtSlot(dict)
    def update_results(self, results):
        """
        Populates the analysis table from a results dictionary.
        This widget now expects pre-formatted, standardized data.
        """
        params = IV_PARAMETER_KEYS
        suffixes = ["F_Raw", "R_Raw", "F_Corr", "R_Corr"]

        for row, param_key in enumerate(params):
            for col, suffix in enumerate(suffixes):
                val = results.get(f"{param_key}_{suffix}", None)
                display_text = "--"
                if val is not None:
                    number = parse_float_or_none(val)
                    if number is not None:
                        display_text = f"{number:.4f}"
                
                item = QTableWidgetItem(display_text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

    def clear(self):
        """清空表格數據"""
        self.table.clearContents()
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                self.table.setItem(row, col, QTableWidgetItem("--"))