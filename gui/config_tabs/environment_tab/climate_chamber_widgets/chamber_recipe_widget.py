"""gui/config_tabs/environment_tab/climate_chamber_widgets/chamber_recipe_widget.py

Stage 2.6.2 update:
- Extract the climate tab top ISOS / environment recipe section into its own widget.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel


class ChamberRecipeWidget(QGroupBox):
    """Environment recipe widget for the climate chamber tab."""

    recipe_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("ISOS / 環境 Recipe", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the recipe controls."""
        form = QFormLayout(self)

        self.combo_env_recipe = QComboBox()
        self.lbl_env_recipe_desc = QLabel("-")
        self.lbl_env_recipe_desc.setWordWrap(True)

        form.addRow("環境 Recipe", self.combo_env_recipe)
        form.addRow("說明", self.lbl_env_recipe_desc)

        self.combo_env_recipe.currentTextChanged.connect(self.recipe_changed.emit)

    def set_recipe_options(self, recipe_ids: list[str]) -> None:
        """Populate available recipe ids."""
        current = self.combo_env_recipe.currentText()
        self.combo_env_recipe.blockSignals(True)
        self.combo_env_recipe.clear()
        self.combo_env_recipe.addItem("")
        self.combo_env_recipe.addItems(recipe_ids or [])
        if current and self.combo_env_recipe.findText(current) >= 0:
            self.combo_env_recipe.setCurrentText(current)
        self.combo_env_recipe.blockSignals(False)

    def set_current_recipe(self, recipe_id: str) -> None:
        """Set the current recipe if it exists."""
        if recipe_id and self.combo_env_recipe.findText(recipe_id) >= 0:
            self.combo_env_recipe.setCurrentText(recipe_id)

    def get_current_recipe(self) -> str:
        """Return current recipe id."""
        return self.combo_env_recipe.currentText().strip()

    def set_description(self, text: str) -> None:
        """Update recipe description."""
        self.lbl_env_recipe_desc.setText(text or "-")
