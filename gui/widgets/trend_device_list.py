"""
TrendDeviceListWidget: scope filter + device visibility list + grouped legend panel.
"""
from __future__ import annotations

from typing import Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TrendDeviceListWidget(QWidget):
    """
    Left-side scope/filter widget for the Trend window.

    設計原則：
    - 不靠 scope/legend 的 stretch 比例硬切高度
    - 讓左側外層 QScrollArea 接管高度不足時的捲動
    - 在本 widget 內只定義自然內容高度與必要的最小高度
    - 明確指定深色主題樣式，避免 QComboBox 文字在深色背景下不可見
    """

    visibilityChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scope_entries: Dict[str, Dict] = {}
        self._checked_state: Dict[str, bool] = {}
        self._device_checkboxes: Dict[str, QCheckBox] = {}
        self._is_rebuilding = False
        self._init_ui()

    # =========================================================
    # UI helpers
    # =========================================================
    def _group_style(self) -> str:
        return """
            QGroupBox {
                font-weight: bold;
                border: 1px solid silver;
                border-radius: 5px;
                margin-top: 10px;
                color: #E8E8E8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 600; color: #DADADA; padding: 0 0 2px 0;")
        return label

    def _combo_style(self) -> str:
        return """
            QComboBox {
                color: #F2F2F2;
                background-color: #343434;
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                padding: 6px 28px 6px 10px;
                selection-background-color: #555555;
                selection-color: #FFFFFF;
            }
            QComboBox:hover {
                border: 1px solid #777777;
            }
            QComboBox::drop-down {
                width: 24px;
                border: none;
                background: transparent;
            }
            QComboBox QAbstractItemView {
                color: #F2F2F2;
                background-color: #2D2D2D;
                border: 1px solid #666666;
                selection-background-color: #4F4F4F;
                selection-color: #FFFFFF;
                outline: 0;
            }
        """

    def _panel_style(self) -> str:
        return """
            QFrame {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 4px;
            }
            QLabel, QCheckBox {
                color: #E6E6E6;
            }
            QCheckBox {
                padding: 2px 0;
            }
        """

    def _tree_style(self) -> str:
        return """
            QTreeWidget {
                background-color: rgba(255, 255, 255, 0.03);
                color: #EAEAEA;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 4px;
                padding: 4px;
            }
            QTreeWidget::item {
                padding: 2px 0;
            }
            QTreeWidget::item:selected {
                background-color: rgba(255, 255, 255, 0.08);
                color: #FFFFFF;
            }
        """

    def _style_combo(self, combo: QComboBox):
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumHeight(38)
        combo.setMinimumContentsLength(12)
        combo.setStyleSheet(self._combo_style())
        try:
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        except Exception:
            pass

    def _build_field_block(self, label_text: str, widget: QWidget) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._section_label(label_text))
        layout.addWidget(widget)
        return block

    def _init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        # -----------------------------------------------------
        # Scope filter group
        # -----------------------------------------------------
        scope_group = QGroupBox("範圍選擇")
        scope_group.setStyleSheet(self._group_style())
        scope_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        scope_layout = QVBoxLayout(scope_group)
        scope_layout.setContentsMargins(14, 18, 14, 14)
        scope_layout.setSpacing(10)

        self.cb_user = QComboBox()
        self.cb_project = QComboBox()
        self._style_combo(self.cb_user)
        self._style_combo(self.cb_project)
        self.cb_user.currentTextChanged.connect(self._on_user_changed)
        self.cb_project.currentTextChanged.connect(self._on_project_changed)

        scope_layout.addWidget(self._build_field_block("使用者", self.cb_user))
        scope_layout.addWidget(self._build_field_block("專案", self.cb_project))

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("color: rgba(255,255,255,0.18);")
        scope_layout.addWidget(divider)

        scope_layout.addWidget(self._section_label("電池代號"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_check_all = QPushButton("全選")
        self.btn_uncheck_all = QPushButton("全不選")
        for btn in (self.btn_check_all, self.btn_uncheck_all):
            btn.setMinimumHeight(38)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_check_all.clicked.connect(self._on_check_all_clicked)
        self.btn_uncheck_all.clicked.connect(self._on_uncheck_all_clicked)
        btn_row.addWidget(self.btn_check_all)
        btn_row.addWidget(self.btn_uncheck_all)
        scope_layout.addLayout(btn_row)

        self.device_panel = QFrame()
        self.device_panel.setStyleSheet(self._panel_style())
        self.device_panel.setMinimumHeight(200)
        self.device_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        self.device_layout = QVBoxLayout(self.device_panel)
        self.device_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.device_layout.setContentsMargins(10, 10, 10, 10)
        self.device_layout.setSpacing(6)

        scope_layout.addWidget(self.device_panel)
        root.addWidget(scope_group)

        # -----------------------------------------------------
        # Grouped legend group
        # -----------------------------------------------------
        legend_group = QGroupBox("目前可見曲線")
        legend_group.setStyleSheet(self._group_style())
        legend_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        legend_layout = QVBoxLayout(legend_group)
        legend_layout.setContentsMargins(14, 18, 14, 14)

        self.legend_tree = QTreeWidget()
        self.legend_tree.setHeaderHidden(True)
        self.legend_tree.setRootIsDecorated(True)
        self.legend_tree.setUniformRowHeights(False)
        self.legend_tree.setIndentation(16)
        self.legend_tree.setMinimumHeight(220)
        self.legend_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.legend_tree.setStyleSheet(self._tree_style())
        legend_layout.addWidget(self.legend_tree)

        root.addWidget(legend_group)
        root.addStretch(1)

        self._reset_filter_combos()

    # =========================================================
    # Public API
    # =========================================================
    def _reset_filter_combos(self):
        self.cb_user.blockSignals(True)
        self.cb_project.blockSignals(True)
        self.cb_user.clear()
        self.cb_project.clear()
        self.cb_user.addItem("全部")
        self.cb_project.addItem("全部")
        self.cb_user.blockSignals(False)
        self.cb_project.blockSignals(False)

    def set_scope_entries(self, entries: List[Dict]):
        self._scope_entries = {}
        new_checked_state: Dict[str, bool] = {}

        for entry in entries:
            entry = dict(entry)
            key = str(entry["series_key"])
            self._scope_entries[key] = entry
            new_checked_state[key] = self._checked_state.get(key, True)

        self._checked_state = new_checked_state
        self._rebuild_filter_combos()
        self._rebuild_device_checkboxes()
        self.set_grouped_legend({})
        self.visibilityChanged.emit()

    def clear_scope(self):
        self._scope_entries.clear()
        self._checked_state.clear()
        self._clear_device_checkboxes()
        self._reset_filter_combos()
        self.set_grouped_legend({})
        self.visibilityChanged.emit()

    def get_filter_state(self) -> Dict[str, str]:
        return {
            "user": self.cb_user.currentText() or "全部",
            "project": self.cb_project.currentText() or "全部",
        }

    def get_filtered_entries(self) -> List[Dict]:
        user = self.cb_user.currentText() or "全部"
        project = self.cb_project.currentText() or "全部"

        entries = []
        for entry in self._scope_entries.values():
            if user != "全部" and entry.get("user") != user:
                continue
            if project != "全部" and entry.get("project") != project:
                continue
            entries.append(entry)

        entries.sort(
            key=lambda item: (
                str(item.get("user", "")),
                str(item.get("project", "")),
                str(item.get("display_label", "")),
                int(item.get("ch_id", 0) or 0),
            )
        )
        return entries

    def get_visible_series_keys(self) -> List[str]:
        keys = []
        for entry in self.get_filtered_entries():
            key = str(entry["series_key"])
            if self._checked_state.get(key, True):
                keys.append(key)
        return keys

    def get_visible_devices(self) -> Dict[str, bool]:
        visible = {key: False for key in self._scope_entries.keys()}
        for key in self.get_visible_series_keys():
            visible[key] = True
        return visible

    def set_grouped_legend(self, grouped_entries: Dict[str, List[Dict]]):
        self.legend_tree.clear()
        for group_label, children in grouped_entries.items():
            top = QTreeWidgetItem([group_label])
            top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.legend_tree.addTopLevelItem(top)

            for child in children:
                label = str(child.get("display_label") or child.get("label") or "")
                item = QTreeWidgetItem([label])
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                color = child.get("color")
                if color is not None:
                    try:
                        item.setForeground(0, QBrush(QColor(color)))
                    except Exception:
                        pass
                top.addChild(item)

            top.setExpanded(True)

    # =========================================================
    # Internal rebuild helpers
    # =========================================================
    def _rebuild_filter_combos(self):
        current_user = self.cb_user.currentText() or "全部"
        current_project = self.cb_project.currentText() or "全部"

        users = sorted({str(entry.get("user", "")) for entry in self._scope_entries.values() if entry.get("user")})

        self.cb_user.blockSignals(True)
        self.cb_user.clear()
        self.cb_user.addItem("全部")
        self.cb_user.addItems(users)
        if current_user in [self.cb_user.itemText(i) for i in range(self.cb_user.count())]:
            self.cb_user.setCurrentText(current_user)
        self.cb_user.blockSignals(False)

        self._rebuild_project_combo(preferred=current_project)

    def _rebuild_project_combo(self, preferred: str = "全部"):
        current_user = self.cb_user.currentText() or "全部"
        if current_user == "全部":
            projects = sorted({str(entry.get("project", "")) for entry in self._scope_entries.values() if entry.get("project")})
        else:
            projects = sorted(
                {
                    str(entry.get("project", ""))
                    for entry in self._scope_entries.values()
                    if entry.get("user") == current_user and entry.get("project")
                }
            )

        self.cb_project.blockSignals(True)
        self.cb_project.clear()
        self.cb_project.addItem("全部")
        self.cb_project.addItems(projects)
        if preferred in [self.cb_project.itemText(i) for i in range(self.cb_project.count())]:
            self.cb_project.setCurrentText(preferred)
        self.cb_project.blockSignals(False)

    def _clear_device_checkboxes(self):
        while self.device_layout.count():
            item = self.device_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._device_checkboxes.clear()

    def _rebuild_device_checkboxes(self):
        self._is_rebuilding = True
        try:
            filtered_entries = self.get_filtered_entries()
            self._clear_device_checkboxes()

            if not filtered_entries:
                placeholder = QLabel("目前沒有正在執行中的電池。")
                placeholder.setWordWrap(True)
                placeholder.setStyleSheet("color: #A8A8A8; padding: 8px 4px;")
                self.device_layout.addWidget(placeholder)
                return

            for entry in filtered_entries:
                key = str(entry["series_key"])
                checkbox = QCheckBox(str(entry.get("display_label") or key))
                checkbox.setChecked(self._checked_state.get(key, True))
                checkbox.setMinimumHeight(26)
                checkbox.setStyleSheet("color: #EAEAEA;")
                checkbox.toggled.connect(
                    lambda checked, series_key=key: self._on_device_toggled(series_key, checked)
                )
                self.device_layout.addWidget(checkbox)
                self._device_checkboxes[key] = checkbox
        finally:
            self._is_rebuilding = False

    # =========================================================
    # Slots / callbacks
    # =========================================================
    def _on_user_changed(self):
        if self._is_rebuilding:
            return
        self._rebuild_project_combo(preferred="全部")
        self._rebuild_device_checkboxes()
        self.visibilityChanged.emit()

    def _on_project_changed(self):
        if self._is_rebuilding:
            return
        self._rebuild_device_checkboxes()
        self.visibilityChanged.emit()

    def _on_device_toggled(self, series_key: str, checked: bool):
        self._checked_state[str(series_key)] = bool(checked)
        if not self._is_rebuilding:
            self.visibilityChanged.emit()

    def _set_filtered_check_state(self, checked: bool):
        filtered_keys = [str(entry["series_key"]) for entry in self.get_filtered_entries()]
        for key in filtered_keys:
            self._checked_state[key] = checked
        self._rebuild_device_checkboxes()
        self.visibilityChanged.emit()

    def _on_check_all_clicked(self):
        self._set_filtered_check_state(True)

    def _on_uncheck_all_clicked(self):
        self._set_filtered_check_state(False)
