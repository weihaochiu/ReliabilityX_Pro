"""gui/config_tabs/environment_recipe_editors/base_environment_recipe_editor.py

Stage 3.0 skeleton:
- Provide shared recipe editor fields for all environment recipe types.
- View layer only. No JSON IO and no hardware control.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QFormLayout, QLineEdit, QTextEdit, QWidget


class BaseEnvironmentRecipeEditor(QWidget):
    """Shared editor fields for all environment recipe types.

    Attributes:
        environment_type: Fixed environment type label supplied by subclasses.
    """

    environment_type = ""

    def __init__(self, parent=None) -> None:
        """Initialize the shared editor UI."""
        super().__init__(parent)
        self.form = QFormLayout(self)

        self.edit_id = QLineEdit()
        self.edit_name = QLineEdit()
        self.edit_environment_type = QLineEdit()
        self.edit_environment_type.setReadOnly(True)
        self.edit_description = QTextEdit()
        self.edit_description.setFixedHeight(80)
        self.chk_enabled = QCheckBox("啟用")

        self.form.addRow("Recipe ID", self.edit_id)
        self.form.addRow("名稱", self.edit_name)
        self.form.addRow("Environment Type", self.edit_environment_type)
        self.form.addRow("說明", self.edit_description)
        self.form.addRow("狀態", self.chk_enabled)

        self.edit_environment_type.setText(self.environment_type)

    def set_recipe_data(self, data: dict) -> None:
        """Populate shared fields from a recipe dictionary.

        Args:
            data: Recipe dictionary.
        """
        data = data or {}
        self.edit_id.setText(str(data.get("id", "") or ""))
        self.edit_name.setText(str(data.get("name", "") or ""))
        self.edit_environment_type.setText(
            str(data.get("environment_type", self.environment_type) or self.environment_type)
        )
        self.edit_description.setPlainText(str(data.get("description", "") or ""))
        self.chk_enabled.setChecked(bool(data.get("enabled", True)))

    def get_recipe_data(self) -> dict:
        """Return shared fields as a recipe dictionary.

        Returns:
            dict: Shared recipe data.
        """
        return {
            "id": self.edit_id.text().strip(),
            "name": self.edit_name.text().strip(),
            "environment_type": self.edit_environment_type.text().strip(),
            "description": self.edit_description.toPlainText().strip(),
            "enabled": self.chk_enabled.isChecked(),
        }
