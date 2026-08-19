"""gui/config_tabs/personnel_tab.py

Unified user/project ownership editor for ReliabilityX Pro.

This tab keeps the simple project ownership rule requested by the operator:
projects are grouped under one user and ChannelSettingDialog lists all projects
for the selected user.  Per-user report routing metadata (email / CC list) is
stored separately in USER_PROFILES so notifications can route a user's project
reports without adding an unnecessary active-project state machine.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PersonnelTab(QWidget):
    """Edit user-owned projects plus per-user report CC information."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the personnel tab."""
        super().__init__(parent)
        self.user_project_map_editor: Dict[str, List[str]] = {}
        self.user_profiles_editor: Dict[str, Dict[str, object]] = {}
        self._is_loading = False
        self.init_ui()

    def init_ui(self) -> None:
        """Build the pure-Python UI; avoids uic.loadUi for packaging safety."""
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(16)

        user_group = QGroupBox("使用者 / Users")
        user_layout = QVBoxLayout(user_group)
        self.user_list = QListWidget()
        self.user_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        user_layout.addWidget(self.user_list)
        user_buttons = QHBoxLayout()
        self.add_user_btn = QPushButton("新增使用者")
        self.remove_user_btn = QPushButton("刪除使用者")
        user_buttons.addWidget(self.add_user_btn)
        user_buttons.addWidget(self.remove_user_btn)
        user_layout.addLayout(user_buttons)

        project_group = QGroupBox("此使用者的 Project / Projects Owned by Selected User")
        project_layout = QVBoxLayout(project_group)
        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        project_layout.addWidget(self.project_list)
        project_buttons = QHBoxLayout()
        self.add_project_btn = QPushButton("新增 Project")
        self.remove_project_btn = QPushButton("刪除 Project")
        project_buttons.addWidget(self.add_project_btn)
        project_buttons.addWidget(self.remove_project_btn)
        project_layout.addLayout(project_buttons)

        profile_group = QGroupBox("報告收件資訊 / Report Routing")
        profile_layout = QVBoxLayout(profile_group)
        hint = QLabel(
            "Project 仍然只掛在使用者底下；不另外維護 active project。\n"
            "Email 與 CC list 用於日報、PDF 或 Telegram/Email report routing。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555555;")
        profile_layout.addWidget(hint)
        form = QFormLayout()
        self.edit_email = QLineEdit()
        self.edit_cc = QTextEdit()
        self.edit_cc.setPlaceholderText("每行一個 email，或用逗號/分號分隔。")
        self.edit_cc.setFixedHeight(90)
        self.edit_notes = QTextEdit()
        self.edit_notes.setPlaceholderText("角色、常用報告時間、主管或實驗備註。")
        self.edit_notes.setFixedHeight(80)
        form.addRow("Email", self.edit_email)
        form.addRow("CC 給誰", self.edit_cc)
        form.addRow("Notes", self.edit_notes)
        profile_layout.addLayout(form)
        self.lbl_status = QLabel("已載入 / Loaded")
        self.lbl_status.setStyleSheet("color: #555555;")
        profile_layout.addWidget(self.lbl_status)
        profile_layout.addStretch(1)

        root.addWidget(user_group, 2)
        root.addWidget(project_group, 2)
        root.addWidget(profile_group, 3)

        self.user_list.currentItemChanged.connect(self._on_user_selected)
        self.add_user_btn.clicked.connect(self._add_user)
        self.remove_user_btn.clicked.connect(self._remove_user)
        self.add_project_btn.clicked.connect(self._add_project)
        self.remove_project_btn.clicked.connect(self._remove_project)
        self.edit_email.textChanged.connect(self._save_current_profile)
        self.edit_cc.textChanged.connect(self._save_current_profile)
        self.edit_notes.textChanged.connect(self._save_current_profile)

    def load_settings(self, settings: dict) -> None:
        """Load user/project/profile settings into the editor."""
        self._is_loading = True
        try:
            self.user_project_map_editor = json.loads(json.dumps(settings.get("USER_PROJECT_MAP", {})))
            self.user_profiles_editor = json.loads(json.dumps(settings.get("USER_PROFILES", {})))
            for user_name in self.user_project_map_editor:
                self.user_profiles_editor.setdefault(user_name, {"email": "", "cc": [], "notes": ""})
            self.user_list.clear()
            for user_name in sorted(self.user_project_map_editor.keys()):
                self.user_list.addItem(QListWidgetItem(user_name))
            if self.user_list.count() > 0:
                self.user_list.setCurrentRow(0)
            else:
                self.project_list.clear()
                self._load_profile_widgets("")
            self.lbl_status.setText("已載入 / Loaded")
            self.lbl_status.setStyleSheet("color: #555555;")
        finally:
            self._is_loading = False

    def get_settings(self) -> dict:
        """Return edited user/project map and per-user report profiles."""
        self._save_current_profile()
        return {
            "USER_PROJECT_MAP": self.user_project_map_editor,
            "USER_PROFILES": self.user_profiles_editor,
        }

    def _current_user_name(self) -> str:
        item = self.user_list.currentItem()
        return item.text() if item else ""

    def _on_user_selected(self, current, _previous) -> None:
        """Refresh projects and report profile when a user is selected."""
        self._is_loading = True
        try:
            self.project_list.clear()
            if current:
                user = current.text()
                self.project_list.addItems(sorted(self.user_project_map_editor.get(user, [])))
                self._load_profile_widgets(user)
            else:
                self._load_profile_widgets("")
        finally:
            self._is_loading = False

    def _load_profile_widgets(self, user_name: str) -> None:
        """Populate email/CC fields for one user."""
        profile = self.user_profiles_editor.get(user_name, {}) if user_name else {}
        self.edit_email.setText(str(profile.get("email", "")))
        cc_values = profile.get("cc", [])
        if isinstance(cc_values, list):
            self.edit_cc.setPlainText("\n".join(str(item) for item in cc_values))
        else:
            self.edit_cc.setPlainText(str(cc_values or ""))
        self.edit_notes.setPlainText(str(profile.get("notes", "")))

    def _parse_cc_text(self) -> List[str]:
        """Parse the CC editor into a clean recipient list."""
        text = self.edit_cc.toPlainText().replace(";", ",").replace("\n", ",")
        return [part.strip() for part in text.split(",") if part.strip()]

    def _save_current_profile(self) -> None:
        """Persist current profile widgets into the in-memory model."""
        if self._is_loading:
            return
        user = self._current_user_name()
        if not user:
            return
        self.user_profiles_editor[user] = {
            "email": self.edit_email.text().strip(),
            "cc": self._parse_cc_text(),
            "report_times": self.user_profiles_editor.get(user, {}).get("report_times", []),
            "notes": self.edit_notes.toPlainText().strip(),
        }
        self.lbl_status.setText("已更新，按『儲存並套用』落盤 / Ready to save")
        self.lbl_status.setStyleSheet("color: #2E7D32;")

    def _add_user(self) -> None:
        """Create a user and empty project list."""
        text, ok = QInputDialog.getText(self, "新增使用者", "使用者名稱:")
        user_name = text.strip() if ok and text else ""
        if not user_name:
            return
        if user_name in self.user_project_map_editor:
            QMessageBox.information(self, "使用者已存在", f"'{user_name}' 已在清單中。")
            return
        self.user_project_map_editor[user_name] = []
        self.user_profiles_editor[user_name] = {"email": "", "cc": [], "report_times": [], "notes": ""}
        self.user_list.addItem(QListWidgetItem(user_name))
        matches = self.user_list.findItems(user_name, Qt.MatchFlag.MatchExactly)
        if matches:
            self.user_list.setCurrentItem(matches[0])
        self._save_current_profile()

    def _remove_user(self) -> None:
        """Remove selected user after confirmation."""
        current_item = self.user_list.currentItem()
        if not current_item:
            return
        if len(self.user_project_map_editor) <= 1:
            QMessageBox.warning(self, "警告", "至少需保留一位使用者。")
            return
        user_name = current_item.text()
        reply = QMessageBox.question(
            self,
            "確認刪除",
            f"確定要刪除使用者 '{user_name}' 與其 project 清單？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.user_project_map_editor.pop(user_name, None)
        self.user_profiles_editor.pop(user_name, None)
        self.user_list.takeItem(self.user_list.row(current_item))
        self.project_list.clear()

    def _add_project(self) -> None:
        """Add a project under the selected user."""
        user_name = self._current_user_name()
        if not user_name:
            QMessageBox.warning(self, "提示", "請先選擇一位使用者。")
            return
        text, ok = QInputDialog.getText(self, "新增專案", f"為 '{user_name}' 新增專案:")
        project_name = text.strip() if ok and text else ""
        if not project_name:
            return
        projects = self.user_project_map_editor.setdefault(user_name, [])
        if project_name in projects:
            QMessageBox.information(self, "Project 已存在", f"'{project_name}' 已在此使用者底下。")
            return
        projects.append(project_name)
        self.project_list.addItem(QListWidgetItem(project_name))

    def _remove_project(self) -> None:
        """Remove the selected project from the selected user."""
        user_name = self._current_user_name()
        current_project = self.project_list.currentItem()
        if not user_name or not current_project:
            QMessageBox.warning(self, "提示", "請先選擇一位使用者和一個專案。")
            return
        project_name = current_project.text()
        reply = QMessageBox.question(
            self,
            "確認刪除",
            f"確定要刪除專案 '{project_name}'？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        projects = self.user_project_map_editor.get(user_name, [])
        if project_name in projects:
            projects.remove(project_name)
        self.project_list.takeItem(self.project_list.row(current_project))
