"""gui/config_tabs/environment_tab/base_environment_tab.py

Stage 2.6 update:
- Shared top section for instance / relay assignment / environment recipe.
- Used by climate, glovebox, and indoor subtabs.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.environment_manager import EnvironmentManager


class BaseEnvironmentTab(QWidget):
    """Shared environment-tab base.

    Each fixed subtab still maps to one effective instance id, so the UI shows
    `Instance ID` as read-only text instead of an unnecessary dropdown.
    """

    environment_type = ""

    def __init__(self, environment_manager: EnvironmentManager, parent=None) -> None:
        super().__init__(parent)
        self.environment_manager = environment_manager

        self.lbl_instance = QLabel("-")
        self.combo_plus_start = QComboBox()
        self.combo_plus_end = QComboBox()
        self.combo_minus_start = QComboBox()
        self.combo_minus_end = QComboBox()
        self.combo_env_recipe = QComboBox()
        self.lbl_env_recipe_desc = QLabel("-")
        self.lbl_env_recipe_desc.setWordWrap(True)

        self._build_common_ui()
        self._connect_signals()
        self.load_from_manager()

    def _build_common_ui(self) -> None:
        """Build shared instance / relay / recipe UI."""
        root = QVBoxLayout(self)

        gb_instance = QGroupBox("Environment Instance")
        form_instance = QFormLayout(gb_instance)
        form_instance.addRow("Instance ID", self.lbl_instance)
        root.addWidget(gb_instance)

        gb_relay = QGroupBox("SMU Relay Assignment")
        form_relay = QFormLayout(gb_relay)

        for combo, start, end in [
            (self.combo_plus_start, 0, 31),
            (self.combo_plus_end, 0, 31),
            (self.combo_minus_start, 32, 63),
            (self.combo_minus_end, 32, 63),
        ]:
            combo.addItems([str(i) for i in range(start, end + 1)])

        form_relay.addRow("SMU+ 起始", self.combo_plus_start)
        form_relay.addRow("SMU+ 結束", self.combo_plus_end)
        form_relay.addRow("SMU- 起始", self.combo_minus_start)
        form_relay.addRow("SMU- 結束", self.combo_minus_end)
        root.addWidget(gb_relay)

        gb_recipe = QGroupBox("ISOS / 環境 Recipe")
        form_recipe = QFormLayout(gb_recipe)
        form_recipe.addRow("環境 Recipe", self.combo_env_recipe)
        form_recipe.addRow("說明", self.lbl_env_recipe_desc)
        root.addWidget(gb_recipe)

    def _connect_signals(self) -> None:
        """Wire up shared signals."""
        self.combo_env_recipe.currentTextChanged.connect(self._on_recipe_changed)

    def _on_recipe_changed(self, recipe_id: str) -> None:
        """Refresh recipe description label."""
        self.lbl_env_recipe_desc.setText(
            self.environment_manager.get_recipe_description(recipe_id) or "-"
        )

    def get_default_instance_id(self) -> str:
        """Return the first instance id for this environment type."""
        ids = self.environment_manager.list_instances(self.environment_type)
        return ids[0] if ids else ""

    def load_from_manager(self) -> None:
        """Load current instance and recipe data from EnvironmentManager."""
        self.environment_manager.reload_all()
        instance_id = self.get_default_instance_id()
        self.lbl_instance.setText(instance_id or "-")

        item = self.environment_manager.get_instance(instance_id) if instance_id else None
        if item is not None:
            self.combo_plus_start.setCurrentText(str(item.smu_plus_start))
            self.combo_plus_end.setCurrentText(str(item.smu_plus_end))
            self.combo_minus_start.setCurrentText(str(item.smu_minus_start))
            self.combo_minus_end.setCurrentText(str(item.smu_minus_end))

        current = self.combo_env_recipe.currentText()
        self.combo_env_recipe.clear()
        self.combo_env_recipe.addItem("")
        self.combo_env_recipe.addItems(
            self.environment_manager.get_environment_recipe_ids(self.environment_type)
        )
        if item is not None and item.default_env_recipe:
            self.combo_env_recipe.setCurrentText(item.default_env_recipe)
        elif current and self.combo_env_recipe.findText(current) >= 0:
            self.combo_env_recipe.setCurrentText(current)
        self._on_recipe_changed(self.combo_env_recipe.currentText())

    def save_current_instance(self) -> None:
        """Persist current instance relay assignment / recipe settings."""
        instance_id = self.get_default_instance_id()
        item = self.environment_manager.get_instance(instance_id)
        if item is None:
            return

        payload = {
            "type": item.env_type,
            "title": item.title,
            "smu_plus_start": int(self.combo_plus_start.currentText()),
            "smu_plus_end": int(self.combo_plus_end.currentText()),
            "smu_minus_start": int(self.combo_minus_start.currentText()),
            "smu_minus_end": int(self.combo_minus_end.currentText()),
            "default_env_recipe": self.combo_env_recipe.currentText().strip(),
        }
        self.environment_manager.update_instance(instance_id, payload)
