"""Measurement recipe settings tab for ReliabilityX Pro.

此 tab 只負責維護 measurement recipe library，供 ChannelSettingDialog
快速帶入量測欄位使用。它不處理 relay pin，不參與 runtime 量測。"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

import config
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
    QVBoxLayout,
    QWidget,
)


@dataclass
class MeasurementRecipe:
    name: str
    v_start: float
    v_stop: float
    v_step: float
    delay_time_ms: int
    measurement_interval_min: int
    current_limit_a: float
    area_cm2: float


class RecipeTab(QWidget):
    """集中管理可重複使用的量測 recipe。"""

    recipesChanged = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._recipes: List[MeasurementRecipe] = []
        self._is_loading = False
        self._init_ui()
        self.load_settings(config.load_measurement_recipes())

    def _init_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(16)

        left_box = QGroupBox("Measurement Recipe 清單 / Measurement Recipes")
        left_layout = QVBoxLayout(left_box)
        self.recipe_list = QListWidget()
        self.recipe_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recipe_list.currentRowChanged.connect(self._on_recipe_selected)
        left_layout.addWidget(self.recipe_list)

        list_btn_row = QHBoxLayout()
        self.btn_add = QPushButton("新增")
        self.btn_duplicate = QPushButton("複製")
        self.btn_delete = QPushButton("刪除")
        for btn in (self.btn_add, self.btn_duplicate, self.btn_delete):
            btn.setMinimumHeight(36)
            list_btn_row.addWidget(btn)
        left_layout.addLayout(list_btn_row)

        right_box = QGroupBox("Measurement Recipe 內容 / IV Scan Recipe")
        right_layout = QVBoxLayout(right_box)

        hint = QLabel(
            "Recipe 只作為 channel 量測欄位的快速填值模板。\n"
            "不包含 hw_pos / hw_neg。最後仍需按主視窗右下角『儲存並套用』才會寫入檔案。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555555;")
        right_layout.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.edit_name = QLineEdit()
        self.sb_v_start = self._make_double_spin(-100.0, 100.0, 3, 0.01)
        self.sb_v_stop = self._make_double_spin(-100.0, 100.0, 3, 0.01)
        self.sb_v_step = self._make_double_spin(0.0001, 100.0, 4, 0.01)
        self.sb_delay_ms = self._make_int_spin(0, 3600000, 10)
        self.sb_interval_min = self._make_int_spin(0, 525600, 10)
        self.sb_current_limit = self._make_double_spin(0.0, 100.0, 6, 0.01)
        self.sb_area = self._make_double_spin(0.0, 1000.0, 6, 0.01)

        form.addRow("Measurement Recipe 名稱", self.edit_name)
        form.addRow("電壓起始值 (V)", self.sb_v_start)
        form.addRow("電壓結束值 (V)", self.sb_v_stop)
        form.addRow("電壓步階 (V)", self.sb_v_step)
        form.addRow("延遲時間 (ms)", self.sb_delay_ms)
        form.addRow("量測間隔 (分鐘)", self.sb_interval_min)
        form.addRow("電流量測限制 (A)", self.sb_current_limit)
        form.addRow("元件面積 (cm²)", self.sb_area)
        right_layout.addLayout(form)

        self.lbl_status = QLabel("已載入")
        self.lbl_status.setStyleSheet("color: #555555;")
        right_layout.addWidget(self.lbl_status)

        editor_btn_row = QHBoxLayout()
        self.btn_save = QPushButton("儲存 Measurement Recipe")
        self.btn_reload = QPushButton("重新載入")
        for btn in (self.btn_save, self.btn_reload):
            btn.setMinimumHeight(38)
            editor_btn_row.addWidget(btn)
        editor_btn_row.addStretch(1)
        right_layout.addLayout(editor_btn_row)
        right_layout.addStretch(1)

        root.addWidget(left_box, 2)
        root.addWidget(right_box, 3)

        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_duplicate.clicked.connect(self._on_duplicate_clicked)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_save.clicked.connect(self.save_current_recipe)
        self.btn_reload.clicked.connect(self._reload_from_disk)

        for widget in (
            self.edit_name,
            self.sb_v_start,
            self.sb_v_stop,
            self.sb_v_step,
            self.sb_delay_ms,
            self.sb_interval_min,
            self.sb_current_limit,
            self.sb_area,
        ):
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._mark_dirty)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._mark_dirty)

    def _make_double_spin(self, minimum: float, maximum: float, decimals: int, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setMinimumHeight(34)
        spin.setKeyboardTracking(False)
        return spin

    def _make_int_spin(self, minimum: int, maximum: int, step: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setMinimumHeight(34)
        spin.setKeyboardTracking(False)
        return spin

    def _mark_dirty(self, *_args) -> None:
        if self._is_loading:
            return
        self.lbl_status.setText("尚未儲存到主設定視窗")
        self.lbl_status.setStyleSheet("color: #B36B00;")

    def _reload_from_disk(self) -> None:
        self.load_settings(config.load_measurement_recipes())

    def load_settings(self, settings: Optional[dict]) -> None:
        self._is_loading = True
        try:
            normalized = config.load_measurement_recipes() if settings is None else self._normalize_settings(settings)
            self._recipes = [MeasurementRecipe(**item) for item in normalized.get("recipes", [])]
            self.recipe_list.clear()
            for recipe in self._recipes:
                self.recipe_list.addItem(QListWidgetItem(recipe.name))
            if self._recipes:
                self.recipe_list.setCurrentRow(0)
            else:
                self._clear_editor()
            self.lbl_status.setText("已載入")
            self.lbl_status.setStyleSheet("color: #555555;")
        finally:
            self._is_loading = False
        self.recipesChanged.emit(self.get_recipe_dicts())

    def _normalize_settings(self, settings: dict) -> dict:
        recipes = settings.get("recipes", []) if isinstance(settings, dict) else []
        return config.load_measurement_recipes() if not recipes else {"recipes": [config._normalize_recipe_entry(item, idx) for idx, item in enumerate(recipes, start=1) if config._normalize_recipe_entry(item, idx) is not None]}

    def get_settings(self) -> dict:
        return {"recipes": self.get_recipe_dicts()}

    def get_recipe_dicts(self) -> list:
        return [asdict(recipe) for recipe in self._recipes]

    def _clear_editor(self) -> None:
        defaults = config._get_default_measurement_recipes()["recipes"][0]
        self.edit_name.setText(defaults["name"])
        self.sb_v_start.setValue(defaults["v_start"])
        self.sb_v_stop.setValue(defaults["v_stop"])
        self.sb_v_step.setValue(defaults["v_step"])
        self.sb_delay_ms.setValue(defaults["delay_time_ms"])
        self.sb_interval_min.setValue(defaults["measurement_interval_min"])
        self.sb_current_limit.setValue(defaults["current_limit_a"])
        self.sb_area.setValue(defaults["area_cm2"])

    def _on_recipe_selected(self, row: int) -> None:
        self._is_loading = True
        try:
            if row < 0 or row >= len(self._recipes):
                self._clear_editor()
                return
            recipe = self._recipes[row]
            self.edit_name.setText(recipe.name)
            self.sb_v_start.setValue(recipe.v_start)
            self.sb_v_stop.setValue(recipe.v_stop)
            self.sb_v_step.setValue(recipe.v_step)
            self.sb_delay_ms.setValue(recipe.delay_time_ms)
            self.sb_interval_min.setValue(recipe.measurement_interval_min)
            self.sb_current_limit.setValue(recipe.current_limit_a)
            self.sb_area.setValue(recipe.area_cm2)
            self.lbl_status.setText("已載入")
            self.lbl_status.setStyleSheet("color: #555555;")
        finally:
            self._is_loading = False

    def _build_recipe_from_editor(self) -> MeasurementRecipe:
        """Build and validate one measurement recipe from editor widgets."""
        name = self.edit_name.text().strip()
        if not name:
            raise ValueError("Measurement Recipe 名稱不可為空。")

        v_start = float(self.sb_v_start.value())
        v_stop = float(self.sb_v_stop.value())
        v_step = max(float(self.sb_v_step.value()), 0.0001)
        current_limit = max(float(self.sb_current_limit.value()), 0.0)
        area = max(float(self.sb_area.value()), 0.0)

        safety = getattr(config, "GLOBAL_SAFETY", {}) if isinstance(getattr(config, "GLOBAL_SAFETY", {}), dict) else {}
        v_max = float(safety.get("V_MAX", 20.0))
        i_max = float(safety.get("I_MAX", 0.5))
        if max(abs(v_start), abs(v_stop)) > v_max:
            raise ValueError(f"Recipe 電壓範圍不可超過全域 V_MAX={v_max:g} V。")
        if current_limit > i_max:
            raise ValueError(f"Recipe 電流限制不可超過全域 I_MAX={i_max:g} A。")
        if area <= 0:
            raise ValueError("元件面積 area_cm2 必須大於 0。")

        return MeasurementRecipe(
            name=name,
            v_start=v_start,
            v_stop=v_stop,
            v_step=v_step,
            delay_time_ms=max(int(self.sb_delay_ms.value()), 0),
            measurement_interval_min=max(int(self.sb_interval_min.value()), 0),
            current_limit_a=current_limit,
            area_cm2=area,
        )

    def _ensure_unique_name(self, candidate: str, current_row: int) -> str:
        existing = {recipe.name for idx, recipe in enumerate(self._recipes) if idx != current_row}
        if candidate not in existing:
            return candidate
        suffix = 2
        new_name = f"{candidate} ({suffix})"
        while new_name in existing:
            suffix += 1
            new_name = f"{candidate} ({suffix})"
        return new_name

    def save_current_recipe(self) -> None:
        try:
            recipe = self._build_recipe_from_editor()
        except ValueError as exc:
            QMessageBox.warning(self, "Recipe 無法儲存", str(exc))
            return

        row = self.recipe_list.currentRow()
        if row < 0:
            row = len(self._recipes)
        recipe.name = self._ensure_unique_name(recipe.name, row if row < len(self._recipes) else -1)

        if row >= len(self._recipes):
            self._recipes.append(recipe)
            self.recipe_list.addItem(QListWidgetItem(recipe.name))
            self.recipe_list.setCurrentRow(len(self._recipes) - 1)
        else:
            self._recipes[row] = recipe
            item = self.recipe_list.item(row)
            if item is not None:
                item.setText(recipe.name)

        self.lbl_status.setText("Recipe 已更新，待按『儲存並套用』寫入檔案")
        self.lbl_status.setStyleSheet("color: #2E7D32;")
        self.recipesChanged.emit(self.get_recipe_dicts())

    def _on_add_clicked(self) -> None:
        self.recipe_list.clearSelection()
        self.recipe_list.setCurrentRow(-1)
        self._clear_editor()
        self.edit_name.setText(self._ensure_unique_name("New Recipe", -1))
        self.lbl_status.setText("新增中")
        self.lbl_status.setStyleSheet("color: #B36B00;")

    def _on_duplicate_clicked(self) -> None:
        row = self.recipe_list.currentRow()
        if row < 0 or row >= len(self._recipes):
            QMessageBox.information(self, "無法複製", "請先選擇一個 recipe。")
            return
        base = self._recipes[row]
        copied = MeasurementRecipe(**asdict(base))
        copied.name = self._ensure_unique_name(f"{base.name} Copy", -1)
        self._recipes.append(copied)
        self.recipe_list.addItem(QListWidgetItem(copied.name))
        self.recipe_list.setCurrentRow(len(self._recipes) - 1)
        self.lbl_status.setText("已建立副本，待按『儲存並套用』寫入檔案")
        self.lbl_status.setStyleSheet("color: #2E7D32;")
        self.recipesChanged.emit(self.get_recipe_dicts())

    def _on_delete_clicked(self) -> None:
        row = self.recipe_list.currentRow()
        if row < 0 or row >= len(self._recipes):
            QMessageBox.information(self, "無法刪除", "請先選擇一個 recipe。")
            return

        recipe_name = self._recipes[row].name
        reply = QMessageBox.question(
            self,
            "確認刪除",
            f"確定要刪除 recipe『{recipe_name}』嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        del self._recipes[row]
        item = self.recipe_list.takeItem(row)
        del item
        if self._recipes:
            self.recipe_list.setCurrentRow(min(row, len(self._recipes) - 1))
        else:
            self._clear_editor()
        self.lbl_status.setText("Recipe 已刪除，待按『儲存並套用』寫入檔案")
        self.lbl_status.setStyleSheet("color: #2E7D32;")
        self.recipesChanged.emit(self.get_recipe_dicts())
