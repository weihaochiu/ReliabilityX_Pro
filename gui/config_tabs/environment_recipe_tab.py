"""gui/config_tabs/environment_recipe_tab.py

Stage 3.0 skeleton:
- Independent Environment Recipe editor page.
- Main entry point should be a dedicated SystemConfigDialog tab.
- Climate / Glovebox / Indoor tabs only provide shortcut buttons that jump to
  this shared editor page.
"""

from __future__ import annotations

import json
import os
from typing import Any

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import config
from .environment_recipe_editors.climate_recipe_editor import ClimateRecipeEditor
from .environment_recipe_editors.glovebox_recipe_editor import GloveboxRecipeEditor
from .environment_recipe_editors.indoor_recipe_editor import IndoorRecipeEditor


class EnvironmentRecipeTab(QWidget):
    """Independent environment recipe editor page.

    This stage provides:
    - type filter
    - recipe list
    - new / duplicate / delete skeleton buttons
    - right-side stacked editor by environment type
    - JSON load/save persistence for environment_control_recipes.json

    This stage intentionally does not apply recipe values to hardware.
    """

    def __init__(self, parent=None) -> None:
        """Initialize the recipe editor tab."""
        super().__init__(parent)
        self.recipes: list[dict[str, Any]] = []

        self._build_ui()
        self._connect_signals()
        self.load_settings()

    def _build_ui(self) -> None:
        """Build the recipe-management UI."""
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["all", "climate", "glovebox", "indoor"])
        self.list_recipes = QListWidget()

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("新增")
        self.btn_duplicate = QPushButton("複製")
        self.btn_delete = QPushButton("刪除")
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_duplicate)
        btn_row.addWidget(self.btn_delete)

        left.addWidget(QLabel("Environment Type Filter"))
        left.addWidget(self.combo_filter)
        left.addWidget(self.list_recipes, 1)
        left.addLayout(btn_row)

        right = QVBoxLayout()
        self.editor_stack = QStackedWidget()
        self.editor_climate = ClimateRecipeEditor()
        self.editor_glovebox = GloveboxRecipeEditor()
        self.editor_indoor = IndoorRecipeEditor()
        self.editor_stack.addWidget(self.editor_climate)
        self.editor_stack.addWidget(self.editor_glovebox)
        self.editor_stack.addWidget(self.editor_indoor)

        save_row = QHBoxLayout()
        self.btn_save = QPushButton("儲存 Recipe")
        self.btn_reload = QPushButton("重新載入")
        save_row.addStretch()
        save_row.addWidget(self.btn_reload)
        save_row.addWidget(self.btn_save)

        right.addWidget(self.editor_stack, 1)
        right.addLayout(save_row)

        root.addLayout(left, 2)
        root.addLayout(right, 3)

    def _connect_signals(self) -> None:
        """Connect UI signals."""
        self.combo_filter.currentTextChanged.connect(self._refresh_recipe_list)
        self.list_recipes.currentRowChanged.connect(self._load_selected_recipe_into_editor)
        self.btn_new.clicked.connect(self._create_recipe)
        self.btn_duplicate.clicked.connect(self._duplicate_recipe)
        self.btn_delete.clicked.connect(self._delete_recipe)
        self.btn_save.clicked.connect(self._save_current_recipe)
        self.btn_reload.clicked.connect(self.load_settings)

    def _resource_recipe_path(self) -> str:
        """Return recipe JSON path via config.get_resource_path when available."""
        path = "config/environment_control_recipes.json"
        resolver = getattr(config, "get_resource_path", None)
        return resolver(path) if callable(resolver) else path

    def _load_recipe_json(self) -> dict:
        """Load environment recipe JSON safely."""
        path = self._resource_recipe_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                return payload if isinstance(payload, dict) else {"recipes": []}
        except Exception:
            return {"recipes": []}

    def _save_recipe_json(self, payload: dict) -> None:
        """Save environment recipe JSON safely."""
        path = self._resource_recipe_path()
        try:
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            raise IOError(f"無法寫入 environment_control_recipes.json: {exc}") from exc

    def load_settings(self, _settings=None) -> None:
        """Load recipes from JSON and refresh the list."""
        payload = self._load_recipe_json()
        self.recipes = payload.get("recipes", []) if isinstance(payload, dict) else []
        if not isinstance(self.recipes, list):
            self.recipes = []
        self._refresh_recipe_list()

    def get_settings(self) -> dict:
        """Return current in-memory recipe payload."""
        return {"recipes": self.recipes}

    def open_with_environment_type(self, environment_type: str) -> None:
        """Preselect recipe filter when entering from shortcut buttons."""
        if environment_type in {"climate", "glovebox", "indoor"}:
            self.combo_filter.setCurrentText(environment_type)
        else:
            self.combo_filter.setCurrentText("all")

    def _refresh_recipe_list(self) -> None:
        """Refresh visible recipes using the current environment filter."""
        current_filter = self.combo_filter.currentText()
        self.list_recipes.clear()
        for recipe in self.recipes:
            if not isinstance(recipe, dict):
                continue
            env_type = str(recipe.get("environment_type", "") or "")
            if current_filter != "all" and env_type != current_filter:
                continue
            label = f"{recipe.get('id', '')} | {recipe.get('name', '')}"
            self.list_recipes.addItem(label)
        if self.list_recipes.count() > 0:
            self.list_recipes.setCurrentRow(0)

    def _visible_recipes(self) -> list[dict]:
        """Return currently filtered recipes."""
        current_filter = self.combo_filter.currentText()
        items = []
        for recipe in self.recipes:
            if not isinstance(recipe, dict):
                continue
            env_type = str(recipe.get("environment_type", "") or "")
            if current_filter != "all" and env_type != current_filter:
                continue
            items.append(recipe)
        return items

    def _editor_for_type(self, environment_type: str):
        """Return editor widget and stack index by environment type."""
        mapping = {
            "climate": (self.editor_climate, 0),
            "glovebox": (self.editor_glovebox, 1),
            "indoor": (self.editor_indoor, 2),
        }
        return mapping.get(environment_type, (self.editor_climate, 0))

    def _load_selected_recipe_into_editor(self, row: int) -> None:
        """Load selected recipe into the matching editor."""
        visible = self._visible_recipes()
        if row < 0 or row >= len(visible):
            return
        recipe = visible[row]
        env_type = str(recipe.get("environment_type", "climate") or "climate")
        editor, index = self._editor_for_type(env_type)
        self.editor_stack.setCurrentIndex(index)
        editor.set_recipe_data(recipe)

    def _create_recipe(self) -> None:
        """Create a new recipe skeleton under the current filter."""
        env_type = self.combo_filter.currentText()
        if env_type == "all":
            env_type = "climate"

        new_recipe = {
            "id": f"{env_type}_new",
            "name": f"New {env_type.title()} Recipe",
            "environment_type": env_type,
            "description": "",
            "enabled": True,
        }
        self.recipes.append(new_recipe)
        self._refresh_recipe_list()
        self.list_recipes.setCurrentRow(self.list_recipes.count() - 1)

    def _duplicate_recipe(self) -> None:
        """Duplicate the selected recipe."""
        row = self.list_recipes.currentRow()
        visible = self._visible_recipes()
        if row < 0 or row >= len(visible):
            return
        original = dict(visible[row])
        original["id"] = f"{original.get('id', 'recipe')}_copy"
        original["name"] = f"{original.get('name', 'Recipe')} Copy"
        self.recipes.append(original)
        self._refresh_recipe_list()
        self.list_recipes.setCurrentRow(self.list_recipes.count() - 1)

    def _delete_recipe(self) -> None:
        """Delete the selected recipe."""
        row = self.list_recipes.currentRow()
        visible = self._visible_recipes()
        if row < 0 or row >= len(visible):
            return
        target = visible[row]
        self.recipes.remove(target)
        self._refresh_recipe_list()

    def _save_current_recipe(self) -> None:
        """Save current editor content back to memory and JSON."""
        row = self.list_recipes.currentRow()
        visible = self._visible_recipes()
        if row < 0 or row >= len(visible):
            QMessageBox.warning(self, "提醒", "請先選擇一筆 Environment Recipe。")
            return

        target = visible[row]
        env_type = str(target.get("environment_type", "climate") or "climate")
        editor, _ = self._editor_for_type(env_type)
        updated = editor.get_recipe_data()

        idx = self.recipes.index(target)
        self.recipes[idx] = updated

        try:
            self._save_recipe_json({"recipes": self.recipes})
            self._refresh_recipe_list()
            QMessageBox.information(self, "成功", "Environment Recipe 已儲存。")
        except Exception as exc:
            QMessageBox.critical(self, "錯誤", str(exc))
