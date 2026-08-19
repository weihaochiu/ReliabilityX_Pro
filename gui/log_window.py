import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPlainTextEdit, 
                             QPushButton, QHBoxLayout, QLabel)
from PyQt6.QtGui import (QTextCharFormat, QColor, QFont, QTextCursor)
from PyQt6.QtCore import pyqtSlot, Qt
import config

class LogWindow(QWidget):
    """
    ReliabilityX Pro 系統即時日誌視窗
    提供深色終端風格的事件監控介面
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ReliabilityX Pro - 系統執行稽核日誌")
        self.setMinimumSize(600, 400)
        self.init_ui()

    def closeEvent(self, event):
        """覆寫關閉事件，改為隱藏視窗。"""
        self.hide()
        event.ignore()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # --- 1. 日誌顯示區域 ---
        self.log_display = QPlainTextEdit()
        self.log_display.setObjectName("log_display") # For QSS styling
        self.log_display.setReadOnly(True)
        self.log_display.setUndoRedoEnabled(False)
        layout.addWidget(self.log_display)

        # --- 2. 控制按鈕區域 ---
        btn_layout = QHBoxLayout()
        
        self.lbl_status = QLabel("系統狀態: 監控中")
        self.lbl_status.setObjectName("log_status_label") # For QSS styling
        
        self.btn_clear = QPushButton("清除畫面")
        self.btn_clear.setFixedWidth(100)
        self.btn_clear.clicked.connect(self.log_display.clear)
        
        self.btn_export = QPushButton("匯出當前日誌")
        self.btn_export.setFixedWidth(100)
        self.btn_export.clicked.connect(self.export_visible_log)

        btn_layout.addWidget(self.lbl_status)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addWidget(self.btn_export)
        
        layout.addLayout(btn_layout)

    @pyqtSlot(str, str)
    def append_log(self, level, message):
        """
        接收來自 MeasureEngine 的信號並格式化輸出
        :param level: INFO, WARNING, ERROR, CRITICAL
        :param message: 日誌訊息內容
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        fmt = QTextCharFormat()
        
        # NOTE: Dynamic line-by-line coloring is kept, as it's not suitable for a static stylesheet.
        # The QSS handles the widget's chrome (background, border, default font).
        if level == "INFO":
            fmt.setForeground(QColor("#D4D4D4"))
        elif level == "SUCCESS":
            fmt.setForeground(QColor(config.COLORS["SUCCESS"]))
        elif level == "WARNING":
            fmt.setForeground(QColor(config.COLORS["WARNING"]))
        elif level == "ERROR":
            fmt.setForeground(QColor(config.COLORS["ERROR"]))
        elif level == "CRITICAL":
            fmt.setForeground(QColor(config.COLORS["ERROR"]))
            fmt.setFontWeight(QFont.Weight.Bold)
            
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_display.setTextCursor(cursor)
        
        self.log_display.setCurrentCharFormat(fmt)
        prefix = f"[{timestamp}] [{level}] "
        self.log_display.insertPlainText(f"{prefix}{message}\n")
        
        self.log_display.ensureCursorVisible()

    def export_visible_log(self):
        """將目前視窗看到的內容另存為文字檔"""
        try:
            filename = f"exported_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            save_path = config.BASE_LOG_DIR / filename
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(self.log_display.toPlainText())
            self.append_log("SUCCESS", f"日誌已成功導出至: {filename}")
        except Exception as e:
            self.append_log("ERROR", f"導出失敗: {e}")