"""gui/config_tabs/station_recipe_tab.py

Unified Environment / Station recipe editor for ReliabilityX Pro.

This module intentionally removes SMU/Relay/Chamber connection fields from the
recipe editor.  Recipes now describe the station procedure a scientist cares
about: required environment, light / hotplate / chamber / vacuum setpoints,
time-based actions, and safety limits.  Low-level ports remain in Hardware
Connection; relay ranges remain in Relay / Channel Mapping.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional

import config
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class StationRecipeTab(QWidget):
    """Editor for unified Environment / Station recipe library."""

    recipesChanged = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the station recipe editor."""
        super().__init__(parent)
        self._recipes: List[Dict[str, Any]] = []
        self._is_loading = False
        self._build_ui()
        self.load_settings(config.load_station_recipes())

    def _build_ui(self) -> None:
        """Build the station recipe list and editor layout."""
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(16)

        left_box = QGroupBox("Environment / Station Recipe 清單")
        left_layout = QVBoxLayout(left_box)
        self.recipe_list = QListWidget()
        self.recipe_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recipe_list.currentRowChanged.connect(self._on_recipe_selected)
        left_layout.addWidget(self.recipe_list)
        list_btn_row = QHBoxLayout()
        self.btn_add = QPushButton("新增")
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_delete = QPushButton("刪除")
        for btn in (self.btn_add, self.btn_duplicate, self.btn_delete):
            btn.setMinimumHeight(34)
            list_btn_row.addWidget(btn)
        left_layout.addLayout(list_btn_row)

        right_box = QGroupBox("Environment / Station Recipe 內容")
        right_layout = QVBoxLayout(right_box)
        hint = QLabel(
            "這裡只描述環境/站台程序：何時開關燈、hotplate 溫度、chamber/vacuum setpoint 與安全上限。\n"
            "不包含 SMU VISA、Relay COM port 或 relay pin mapping；那些設定屬於 Hardware Connection 與 Relay / Channel Mapping。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555555;")
        right_layout.addWidget(hint)

        basic_group = QGroupBox("基本資訊")
        basic_form = QFormLayout(basic_group)
        self.edit_name = QLineEdit()
        self.combo_environment_type = QComboBox()
        self.combo_environment_type.addItems(["indoor", "climate", "glovebox", "vacuum", "custom"])
        self.chk_enabled = QCheckBox("啟用此 recipe")
        basic_form.addRow("Recipe 名稱", self.edit_name)
        basic_form.addRow("環境類型", self.combo_environment_type)
        basic_form.addRow("狀態", self.chk_enabled)
        right_layout.addWidget(basic_group)

        hardware_group = QGroupBox("本 recipe 需要的站台硬體")
        hardware_layout = QHBoxLayout(hardware_group)
        self.chk_need_env_sensor = QCheckBox("環境感測器")
        self.chk_need_light = QCheckBox("Light controller")
        self.chk_need_hotplate = QCheckBox("Hotplate")
        self.chk_need_chamber = QCheckBox("Chamber")
        self.chk_need_vacuum = QCheckBox("Vacuum")
        for chk in (self.chk_need_env_sensor, self.chk_need_light, self.chk_need_hotplate, self.chk_need_chamber, self.chk_need_vacuum):
            hardware_layout.addWidget(chk)
        hardware_layout.addStretch(1)
        right_layout.addWidget(hardware_group)

        setpoint_group = QGroupBox("Setpoints / 安全限制")
        setpoint_form = QFormLayout(setpoint_group)
        self.spin_temperature = self._make_double_spin(-100.0, 250.0, 1, 5.0)
        self.spin_humidity = self._make_double_spin(0.0, 100.0, 1, 5.0)
        self.spin_pressure = self._make_double_spin(-101.3, 500.0, 1, 5.0)
        self.spin_light = self._make_double_spin(0.0, 200.0, 1, 10.0)
        self.spin_hotplate = self._make_double_spin(0.0, 250.0, 1, 5.0)
        self.spin_max_temp = self._make_double_spin(0.0, 300.0, 1, 5.0)
        self.spin_max_rh = self._make_double_spin(0.0, 100.0, 1, 5.0)
        setpoint_form.addRow("環境溫度 (°C)", self.spin_temperature)
        setpoint_form.addRow("濕度 (%RH, 不用可填 0)", self.spin_humidity)
        setpoint_form.addRow("壓力 / 真空 (kPa, 不用可填 0)", self.spin_pressure)
        setpoint_form.addRow("光強 (%)", self.spin_light)
        setpoint_form.addRow("Hotplate 溫度 (°C, 不用可填 0)", self.spin_hotplate)
        setpoint_form.addRow("安全上限溫度 (°C)", self.spin_max_temp)
        setpoint_form.addRow("安全上限濕度 (%RH)", self.spin_max_rh)
        right_layout.addWidget(setpoint_group)

        timeline_group = QGroupBox("Timeline / Step Table")
        timeline_layout = QVBoxLayout(timeline_group)
        self.timeline_table = QTableWidget(0, 6)
        self.timeline_table.setHorizontalHeaderLabels(["time_s", "action", "target", "value", "duration_s", "notes"])
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        timeline_layout.addWidget(self.timeline_table)
        timeline_buttons = QHBoxLayout()
        self.btn_add_step = QPushButton("新增 Step")
        self.btn_remove_step = QPushButton("刪除 Step")
        timeline_buttons.addWidget(self.btn_add_step)
        timeline_buttons.addWidget(self.btn_remove_step)
        timeline_buttons.addStretch(1)
        timeline_layout.addLayout(timeline_buttons)
        right_layout.addWidget(timeline_group, 1)

        trace_group = QGroupBox("Traceability / Notes")
        trace_layout = QFormLayout(trace_group)
        self.edit_calibration_profile = QLineEdit("latest")
        self.edit_notification_profile = QLineEdit("default")
        self.edit_notes = QTextEdit()
        self.edit_notes.setFixedHeight(80)
        trace_layout.addRow("Calibration Profile", self.edit_calibration_profile)
        trace_layout.addRow("Notification Profile", self.edit_notification_profile)
        trace_layout.addRow("Notes", self.edit_notes)
        right_layout.addWidget(trace_group)

        status_row = QHBoxLayout()
        self.lbl_status = QLabel("已載入 / Loaded")
        self.lbl_status.setStyleSheet("color: #555555;")
        self.btn_save = QPushButton("儲存 Recipe")
        self.btn_reload = QPushButton("重新載入")
        for btn in (self.btn_save, self.btn_reload):
            btn.setMinimumHeight(36)
        status_row.addWidget(self.lbl_status, 1)
        status_row.addWidget(self.btn_reload)
        status_row.addWidget(self.btn_save)
        right_layout.addLayout(status_row)

        root.addWidget(left_box, 2)
        root.addWidget(right_box, 5)

        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_duplicate.clicked.connect(self._on_duplicate_clicked)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_save.clicked.connect(self.save_current_recipe)
        self.btn_reload.clicked.connect(self._reload_from_disk)
        self.btn_add_step.clicked.connect(self._add_step)
        self.btn_remove_step.clicked.connect(self._remove_selected_step)
        self._connect_dirty_signals()

    def _make_double_spin(self, minimum: float, maximum: float, decimals: int, step: float) -> QDoubleSpinBox:
        """Create a consistent double spin box."""
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setKeyboardTracking(False)
        return spin

    def _connect_dirty_signals(self) -> None:
        """Connect editor changes to dirty-state label updates."""
        widgets = [
            self.edit_name,
            self.combo_environment_type,
            self.chk_enabled,
            self.chk_need_env_sensor,
            self.chk_need_light,
            self.chk_need_hotplate,
            self.chk_need_chamber,
            self.chk_need_vacuum,
            self.spin_temperature,
            self.spin_humidity,
            self.spin_pressure,
            self.spin_light,
            self.spin_hotplate,
            self.spin_max_temp,
            self.spin_max_rh,
            self.edit_calibration_profile,
            self.edit_notification_profile,
            self.edit_notes,
            self.timeline_table,
        ]
        for widget in widgets:
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._mark_dirty)
            elif hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self._mark_dirty)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._mark_dirty)
            elif hasattr(widget, "stateChanged"):
                widget.stateChanged.connect(self._mark_dirty)
            elif hasattr(widget, "itemChanged"):
                widget.itemChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *_args) -> None:
        """Mark current editor state as changed."""
        if self._is_loading:
            return
        self.lbl_status.setText("尚未儲存到主設定視窗 / Unsaved")
        self.lbl_status.setStyleSheet("color: #B36B00;")

    def _reload_from_disk(self) -> None:
        """Reload recipe library from disk."""
        self.load_settings(config.load_station_recipes())

    def load_settings(self, settings: Optional[Dict[str, Any]]) -> None:
        """Load station recipes into the list widget."""
        self._is_loading = True
        try:
            normalized = config.load_station_recipes() if settings is None else self._normalize_settings(settings)
            self._recipes = [copy.deepcopy(item) for item in normalized.get("recipes", [])]
            self.recipe_list.clear()
            for recipe in self._recipes:
                self.recipe_list.addItem(QListWidgetItem(str(recipe.get("name", "Station Recipe"))))
            if self._recipes:
                self.recipe_list.setCurrentRow(0)
            else:
                self._clear_editor()
            self.lbl_status.setText("已載入 / Loaded")
            self.lbl_status.setStyleSheet("color: #555555;")
        finally:
            self._is_loading = False
        self.recipesChanged.emit(self.get_recipe_dicts())

    def _normalize_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw settings through config helpers."""
        recipe_items = settings.get("recipes", []) if isinstance(settings, dict) else []
        normalized = []
        for idx, item in enumerate(recipe_items, start=1):
            entry = config._normalize_station_recipe_entry(item, idx)
            if entry is not None:
                normalized.append(entry)
        return {"recipes": normalized} if normalized else config.load_station_recipes()

    def get_settings(self) -> Dict[str, Any]:
        """Return station recipes for aggregate saving."""
        return {"recipes": self.get_recipe_dicts()}

    def get_recipe_dicts(self) -> List[Dict[str, Any]]:
        """Return a deep copy of current station recipes."""
        return [copy.deepcopy(item) for item in self._recipes]

    def _clear_editor(self) -> None:
        """Populate editor with default recipe values."""
        default_recipe = config._get_default_station_recipes()["recipes"][0]
        self._load_recipe_into_editor(default_recipe)

    def _on_recipe_selected(self, row: int) -> None:
        """Load the selected station recipe into the editor."""
        self._is_loading = True
        try:
            if row < 0 or row >= len(self._recipes):
                self._clear_editor()
                return
            self._load_recipe_into_editor(self._recipes[row])
            self.lbl_status.setText("已載入 / Loaded")
            self.lbl_status.setStyleSheet("color: #555555;")
        finally:
            self._is_loading = False

    def _set_spin_value_or_zero(self, spin: QDoubleSpinBox, value: Any) -> None:
        """Set spin value, treating None as zero for UI clarity."""
        try:
            spin.setValue(float(value if value is not None else 0.0))
        except (TypeError, ValueError):
            spin.setValue(0.0)

    def _load_recipe_into_editor(self, recipe: Dict[str, Any]) -> None:
        """Copy one recipe dictionary into editor widgets."""
        req = recipe.get("required_hardware", {}) if isinstance(recipe.get("required_hardware"), dict) else {}
        setpoints = recipe.get("setpoints", {}) if isinstance(recipe.get("setpoints"), dict) else {}
        safety = recipe.get("safety_limits", {}) if isinstance(recipe.get("safety_limits"), dict) else {}
        self.edit_name.setText(str(recipe.get("name", "")))
        self.combo_environment_type.setCurrentText(str(recipe.get("environment_type", "indoor")))
        self.chk_enabled.setChecked(bool(recipe.get("enabled", True)))
        self.chk_need_env_sensor.setChecked(bool(req.get("environment_sensor", True)))
        self.chk_need_light.setChecked(bool(req.get("light_controller", False)))
        self.chk_need_hotplate.setChecked(bool(req.get("hotplate", False)))
        self.chk_need_chamber.setChecked(bool(req.get("chamber", False)))
        self.chk_need_vacuum.setChecked(bool(req.get("vacuum", False)))
        self._set_spin_value_or_zero(self.spin_temperature, setpoints.get("temperature_c"))
        self._set_spin_value_or_zero(self.spin_humidity, setpoints.get("humidity_rh"))
        self._set_spin_value_or_zero(self.spin_pressure, setpoints.get("pressure_kpa"))
        self._set_spin_value_or_zero(self.spin_light, setpoints.get("light_intensity_percent"))
        self._set_spin_value_or_zero(self.spin_hotplate, setpoints.get("hotplate_temperature_c"))
        self._set_spin_value_or_zero(self.spin_max_temp, safety.get("max_temperature_c"))
        self._set_spin_value_or_zero(self.spin_max_rh, safety.get("max_humidity_rh"))
        self.edit_calibration_profile.setText(str(recipe.get("calibration_profile", "latest")))
        self.edit_notification_profile.setText(str(recipe.get("notification_profile", "default")))
        self.edit_notes.setPlainText(str(recipe.get("notes", "")))
        self._load_timeline(recipe.get("timeline", []))

    def _load_timeline(self, timeline: List[Dict[str, Any]]) -> None:
        """Render timeline rows into the editable table."""
        self.timeline_table.blockSignals(True)
        self.timeline_table.setRowCount(0)
        for step in timeline or []:
            self._add_step(step)
        if self.timeline_table.rowCount() == 0:
            self._add_step({"time_s": 0, "action": "note", "target": "", "value": "", "duration_s": "", "notes": ""})
        self.timeline_table.blockSignals(False)

    def _add_step(self, step: Optional[Dict[str, Any]] = None) -> None:
        """Append one timeline row."""
        step = step if isinstance(step, dict) else {"time_s": 0, "action": "note", "target": "", "value": "", "duration_s": "", "notes": ""}
        row = self.timeline_table.rowCount()
        self.timeline_table.insertRow(row)
        values = [
            step.get("time_s", 0),
            step.get("action", "note"),
            step.get("target", ""),
            step.get("value", ""),
            step.get("duration_s", ""),
            step.get("notes", ""),
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem("" if value is None else str(value))
            if col == 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.timeline_table.setItem(row, col, item)
        self._mark_dirty()

    def _remove_selected_step(self) -> None:
        """Remove selected timeline row."""
        row = self.timeline_table.currentRow()
        if row >= 0:
            self.timeline_table.removeRow(row)
            self._mark_dirty()

    def _timeline_from_table(self) -> List[Dict[str, Any]]:
        """Build timeline list from the editable table."""
        timeline: List[Dict[str, Any]] = []
        for row in range(self.timeline_table.rowCount()):
            def _text(col: int) -> str:
                item = self.timeline_table.item(row, col)
                return item.text().strip() if item else ""
            try:
                time_s = int(float(_text(0) or 0))
            except ValueError:
                time_s = 0
            duration_raw = _text(4)
            try:
                duration = int(float(duration_raw)) if duration_raw else None
            except ValueError:
                duration = None
            timeline.append({
                "time_s": max(0, time_s),
                "action": _text(1) or "note",
                "target": _text(2),
                "value": _text(3),
                "duration_s": duration,
                "notes": _text(5),
            })
        return timeline

    def _none_if_zero(self, value: float) -> Optional[float]:
        """Treat zero as intentionally unused for optional setpoints."""
        return None if abs(float(value)) < 1e-12 else float(value)

    def _build_recipe_from_editor(self) -> Dict[str, Any]:
        """Build one normalized station recipe dictionary from editor widgets."""
        name = self.edit_name.text().strip()
        if not name:
            raise ValueError("Environment / Station Recipe 名稱不可為空。")
        raw = {
            "name": name,
            "environment_type": self.combo_environment_type.currentText(),
            "enabled": self.chk_enabled.isChecked(),
            "required_hardware": {
                "smu": True,
                "relay": True,
                "environment_sensor": self.chk_need_env_sensor.isChecked(),
                "light_controller": self.chk_need_light.isChecked(),
                "hotplate": self.chk_need_hotplate.isChecked(),
                "chamber": self.chk_need_chamber.isChecked(),
                "vacuum": self.chk_need_vacuum.isChecked(),
            },
            "setpoints": {
                "temperature_c": self._none_if_zero(self.spin_temperature.value()),
                "humidity_rh": self._none_if_zero(self.spin_humidity.value()),
                "pressure_kpa": self._none_if_zero(self.spin_pressure.value()),
                "light_intensity_percent": self._none_if_zero(self.spin_light.value()),
                "hotplate_temperature_c": self._none_if_zero(self.spin_hotplate.value()),
            },
            "timeline": self._timeline_from_table(),
            "safety_limits": {
                "max_temperature_c": self._none_if_zero(self.spin_max_temp.value()),
                "max_humidity_rh": self._none_if_zero(self.spin_max_rh.value()),
            },
            "calibration_profile": self.edit_calibration_profile.text().strip() or "latest",
            "notification_profile": self.edit_notification_profile.text().strip() or "default",
            "notes": self.edit_notes.toPlainText().strip(),
        }
        normalized = config._normalize_station_recipe_entry(raw, self.recipe_list.currentRow() + 1)
        if normalized is None:
            raise ValueError("Environment / Station Recipe 格式無法解析。")
        return normalized

    def save_current_recipe(self) -> None:
        """Save the editor contents into the in-memory recipe list."""
        try:
            recipe = self._build_recipe_from_editor()
        except ValueError as exc:
            QMessageBox.warning(self, "Environment / Station Recipe", str(exc))
            return

        row = self.recipe_list.currentRow()
        if row < 0 or row >= len(self._recipes):
            self._recipes.append(recipe)
            self.recipe_list.addItem(QListWidgetItem(recipe["name"]))
            self.recipe_list.setCurrentRow(len(self._recipes) - 1)
        else:
            self._recipes[row] = recipe
            self.recipe_list.item(row).setText(recipe["name"])

        self.lbl_status.setText("已寫入主設定視窗，按『儲存並套用』才會落盤 / Ready to save")
        self.lbl_status.setStyleSheet("color: #2E7D32;")
        self.recipesChanged.emit(self.get_recipe_dicts())

    def _on_add_clicked(self) -> None:
        """Create a new station recipe from defaults."""
        default_recipe = copy.deepcopy(config._get_default_station_recipes()["recipes"][0])
        default_recipe["name"] = f"Environment Station Recipe {len(self._recipes) + 1}"
        self._recipes.append(default_recipe)
        self.recipe_list.addItem(QListWidgetItem(default_recipe["name"]))
        self.recipe_list.setCurrentRow(len(self._recipes) - 1)
        self._mark_dirty()

    def _on_duplicate_clicked(self) -> None:
        """Duplicate the selected station recipe."""
        row = self.recipe_list.currentRow()
        if row < 0 or row >= len(self._recipes):
            return
        recipe = copy.deepcopy(self._recipes[row])
        recipe["name"] = f"{recipe.get('name', 'Environment Station Recipe')} Copy"
        self._recipes.append(recipe)
        self.recipe_list.addItem(QListWidgetItem(recipe["name"]))
        self.recipe_list.setCurrentRow(len(self._recipes) - 1)
        self._mark_dirty()

    def _on_delete_clicked(self) -> None:
        """Delete the selected station recipe after confirmation."""
        row = self.recipe_list.currentRow()
        if row < 0 or row >= len(self._recipes):
            return
        if len(self._recipes) <= 1:
            QMessageBox.warning(self, "Environment / Station Recipe", "至少需保留一組 recipe。")
            return
        name = self._recipes[row].get("name", "Environment Station Recipe")
        reply = QMessageBox.question(
            self,
            "刪除 Recipe",
            f"確定要刪除 '{name}'？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._recipes.pop(row)
        self.recipe_list.takeItem(row)
        self.recipe_list.setCurrentRow(min(row, len(self._recipes) - 1))
        self._mark_dirty()
        self.recipesChanged.emit(self.get_recipe_dicts())
