"""gui/widgets/channel_info_widget.py

Stage 2.5.3 update:
- Keep the existing personnel/project linkage logic.
- Align the label column width with the other channel dialog widgets.

Dynamic channel update:
- The enabled checkbox explicitly means start/pause cyclic measurement.
- A confirmation dialog is shown before user-driven start/pause changes.
"""

import re
import json
import logging
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QGridLayout,
    QVBoxLayout,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSignal
import config

LABEL_WIDTH = 150


class ChannelInfoWidget(QWidget):
    """Channel identity / metadata widget."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_project_map = {}
        self._suppress_enable_confirm = False
        self._last_enabled_state = False
        self.setupUi()
        self._load_personnel_data()
        self._connect_signals()

    def setupUi(self):
        layout = QVBoxLayout(self)
        grid_layout = QGridLayout()

        self.chk_enabled = QCheckBox("暫停循環量測")
        self.combo_user = QComboBox()
        self.combo_project = QComboBox()
        self.edit_device_name = QLineEdit()
        self.label_path_preview = QLabel("路徑預覽...")

        labels = [
            QLabel("循環量測:"),
            QLabel("使用者:"),
            QLabel("專案:"),
            QLabel("元件名稱:"),
        ]
        for label in labels:
            label.setFixedWidth(LABEL_WIDTH)

        grid_layout.addWidget(labels[0], 0, 0)
        grid_layout.addWidget(self.chk_enabled, 0, 1)
        grid_layout.addWidget(labels[1], 1, 0)
        grid_layout.addWidget(self.combo_user, 1, 1)
        grid_layout.addWidget(labels[2], 2, 0)
        grid_layout.addWidget(self.combo_project, 2, 1)
        grid_layout.addWidget(labels[3], 3, 0)
        grid_layout.addWidget(self.edit_device_name, 3, 1)

        grid_layout.setColumnStretch(1, 1)

        layout.addLayout(grid_layout)
        layout.addWidget(self.label_path_preview)

    def _connect_signals(self):
        self.chk_enabled.toggled.connect(self._confirm_enable_toggle)
        self.combo_user.currentTextChanged.connect(self._update_project_options)
        self.combo_project.currentTextChanged.connect(self._update_path_preview)
        self.edit_device_name.textChanged.connect(self._update_path_preview)

    def _load_personnel_data(self):
        try:
            with open(config.PERSONNEL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.user_project_map = data.get("USER_PROJECT_MAP", {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"無法載入或解析 personnel_tab.json: {e}")
            QMessageBox.warning(self, "讀取錯誤", "無法載入人員設定檔，將使用空列表。")
            self.user_project_map = {}

        self.combo_user.addItems(self.user_project_map.keys())


    def _set_enabled_checkbox_text(self):
        """Update the checkbox wording to show start/pause semantics."""
        if self.chk_enabled.isChecked():
            self.chk_enabled.setText("開始循環量測")
        else:
            self.chk_enabled.setText("暫停循環量測")

    def _confirm_enable_toggle(self, checked: bool):
        """Double-check user-driven changes to cyclic measurement state."""
        if self._suppress_enable_confirm:
            self._last_enabled_state = checked
            self._set_enabled_checkbox_text()
            self._update_path_preview()
            return

        title = "確認開始循環量測" if checked else "確認暫停循環量測"
        action = "開始納入循環量測排程" if checked else "暫停循環量測排程"
        detail = (
            "此操作只會改變此 Channel 是否納入循環量測；"
            "不會刪除設定、釋放 relay 或移除既有量測資料。"
        )
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(title)
        msg.setText(f"確定要{action}嗎？")
        msg.setInformativeText(detail)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            self._suppress_enable_confirm = True
            self.chk_enabled.setChecked(self._last_enabled_state)
            self._suppress_enable_confirm = False
            self._set_enabled_checkbox_text()
            self._update_path_preview()
            return

        self._last_enabled_state = checked
        self._set_enabled_checkbox_text()
        self._update_path_preview()

    def _update_project_options(self, user):
        current_project = self.combo_project.currentText()
        self.combo_project.clear()
        projects = self.user_project_map.get(user, [])
        self.combo_project.addItems(projects)

        if current_project in projects:
            self.combo_project.setCurrentText(current_project)

        self._update_path_preview()

    def _sanitize_name(self, name):
        sanitized = re.sub(r'[\\/:*?"<>|]', "_", name)
        return sanitized[:50]

    def _update_path_preview(self):
        user = self.combo_user.currentText()
        project = self.combo_project.currentText()
        device_name = self.edit_device_name.text()

        sanitized_device_name = self._sanitize_name(device_name)
        if device_name != sanitized_device_name:
            self.edit_device_name.setText(sanitized_device_name)
            return

        if self.chk_enabled.isChecked() and user and project and sanitized_device_name:
            path = f"data/{user}/{project}/{sanitized_device_name}/"
            self.label_path_preview.setText(f"路徑預覽: {path}")
        else:
            self.label_path_preview.setText("路徑預覽...")
        self.changed.emit()

    def get_data(self):
        return {
            "enabled": self.chk_enabled.isChecked(),
            "user": self.combo_user.currentText(),
            "project": self.combo_project.currentText(),
            "device_name": self.edit_device_name.text(),
        }

    def set_data(self, data):
        data = data or {}

        self._suppress_enable_confirm = True
        self.chk_enabled.setChecked(bool(data.get("enabled", False)))
        self._last_enabled_state = self.chk_enabled.isChecked()
        self._set_enabled_checkbox_text()
        self._suppress_enable_confirm = False

        user = data.get("user")
        if user and self.combo_user.findText(user) != -1:
            self.combo_user.setCurrentText(user)
        else:
            self.combo_user.setCurrentIndex(-1)

        projects = self.user_project_map.get(self.combo_user.currentText(), [])
        self.combo_project.clear()
        self.combo_project.addItems(projects)

        project = data.get("project")
        if project and self.combo_project.findText(project) != -1:
            self.combo_project.setCurrentText(project)
        else:
            self.combo_project.setCurrentIndex(-1)

        self.edit_device_name.setText(data.get("device_name") or "")
        self._update_path_preview()
