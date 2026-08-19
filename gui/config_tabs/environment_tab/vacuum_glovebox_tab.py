"""gui/config_tabs/environment_tab/vacuum_glovebox_tab.py

Stage 2.6.4 bugfix update:
- Persist relay assignment and default recipe through EnvironmentManager.
- Expose shortcut signal to the shared Environment Recipe editor.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from .environment_common_widgets.environment_recipe_widget import EnvironmentRecipeWidget
from .environment_common_widgets.relay_assignment_widget import RelayAssignmentWidget


class VacuumGloveboxTab(QWidget):
    """Vacuum glovebox environment tab skeleton."""

    environment_type = "glovebox"
    open_environment_recipe_requested = pyqtSignal(str)

    def __init__(self, environment_manager, parent=None) -> None:
        super().__init__(parent)
        self.environment_manager = environment_manager

        self.lbl_instance = QLabel("-")
        self.relay_widget = RelayAssignmentWidget()
        self.recipe_widget = EnvironmentRecipeWidget()

        self._build_ui()
        self._connect_signals()
        self.load_from_manager()

    def _build_ui(self) -> None:
        """Build glovebox skeleton UI."""
        root = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        gb_instance = QGroupBox("Environment Instance")
        form_instance = QFormLayout(gb_instance)
        form_instance.addRow("Instance ID", self.lbl_instance)
        content_layout.addWidget(gb_instance)

        content_layout.addWidget(self.relay_widget)
        content_layout.addWidget(self.recipe_widget)

        gb_pending = QGroupBox("Hardware Status")
        form_pending = QFormLayout(gb_pending)
        form_pending.addRow("Connection", QLabel("Not Ready Yet"))
        form_pending.addRow("Status", QLabel("Not Ready Yet"))
        form_pending.addRow("Control", QLabel("Not Ready Yet"))
        content_layout.addWidget(gb_pending)
        content_layout.addStretch()

        scroll.setWidget(content)

    def _connect_signals(self) -> None:
        """Wire up recipe selection display refresh."""
        self.recipe_widget.recipe_changed.connect(self._on_recipe_changed)

    def get_default_instance_id(self) -> str:
        """Return the first glovebox instance id."""
        ids = self.environment_manager.list_instances(self.environment_type)
        return ids[0] if ids else ""

    def load_from_manager(self) -> None:
        """Load glovebox instance relay and recipe settings."""
        self.environment_manager.reload_all()
        instance_id = self.get_default_instance_id()
        self.lbl_instance.setText(instance_id or "-")

        item = self.environment_manager.get_instance(instance_id) if instance_id else None
        if item is not None:
            self.relay_widget.set_ranges(
                plus_start=item.smu_plus_start,
                plus_end=item.smu_plus_end,
                minus_start=item.smu_minus_start,
                minus_end=item.smu_minus_end,
            )

        self.recipe_widget.set_recipe_options(
            self.environment_manager.get_environment_recipe_ids(self.environment_type)
        )
        if item is not None and item.default_env_recipe:
            self.recipe_widget.set_current_recipe(item.default_env_recipe)
        self._on_recipe_changed(self.recipe_widget.get_current_recipe())

    def save_current_instance(self) -> None:
        """Persist glovebox instance relay assignment and recipe settings."""
        instance_id = self.get_default_instance_id()
        item = self.environment_manager.get_instance(instance_id)
        if item is None:
            return

        payload = {
            "type": item.env_type,
            "title": item.title,
            "smu_plus_start": self.relay_widget.get_plus_start(),
            "smu_plus_end": self.relay_widget.get_plus_end(),
            "smu_minus_start": self.relay_widget.get_minus_start(),
            "smu_minus_end": self.relay_widget.get_minus_end(),
            "default_env_recipe": self.recipe_widget.get_current_recipe().strip(),
        }
        self.environment_manager.update_instance(instance_id, payload)

    def _on_recipe_changed(self, recipe_id: str) -> None:
        """Refresh recipe description."""
        self.recipe_widget.set_description(
            self.environment_manager.get_recipe_description(recipe_id) or "-"
        )
