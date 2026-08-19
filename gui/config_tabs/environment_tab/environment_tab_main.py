"""gui/config_tabs/environment_tab/environment_tab_main.py

Bugfix update:
- Keep this file as the single authoritative EnvironmentTab entry point.
- Provide the shared recipe-editor routing signal expected by
  ``SystemConfigDialog``.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from core.environment_manager import EnvironmentManager
from .climate_chamber_tab import ClimateChamberTab
from .indoor_environment_tab import IndoorEnvironmentTab
from .vacuum_glovebox_tab import VacuumGloveboxTab


class EnvironmentTab(QWidget):
    """Parent environment tab hosting three fixed child subtabs."""

    open_environment_recipe_requested = pyqtSignal(str)

    def __init__(
        self,
        environment_manager: EnvironmentManager | None = None,
        engine=None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Environment tab.

        Args:
            environment_manager: Optional injected core manager.
            engine: Optional engine reference for climate chamber integration.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.engine = engine
        self.environment_manager = environment_manager or EnvironmentManager(
            environment_profiles_path=Path("config/environment_profiles.json"),
            environment_control_recipes_path=Path("config/environment_control_recipes.json"),
        )

        self.lbl_header = QLabel(
            "Environment 設定頁面：固定分成 Climate Chamber / Vacuum Glovebox / Indoor Environment。"
        )
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(
            "QTabBar::tab { background: #3A3A3A; color: #F2F2F2; padding: 8px 16px; "
            "min-height: 28px; font-weight: 700; border: 1px solid #666666; }"
            "QTabBar::tab:selected { background: #0B73D9; color: white; border: 2px solid #9FD0FF; }"
            "QTabBar::tab:!selected { margin-top: 3px; }"
        )
        self.climate_tab = ClimateChamberTab(
            environment_manager=self.environment_manager,
            engine=self.engine,
            parent=self,
        )
        self.glovebox_tab = VacuumGloveboxTab(
            environment_manager=self.environment_manager,
            parent=self,
        )
        self.indoor_tab = IndoorEnvironmentTab(
            environment_manager=self.environment_manager,
            parent=self,
        )

        for tab in (self.climate_tab, self.glovebox_tab, self.indoor_tab):
            if hasattr(tab, "open_environment_recipe_requested"):
                tab.open_environment_recipe_requested.connect(
                    self.open_environment_recipe_requested.emit
                )

        self._build_ui()

    def _build_ui(self) -> None:
        """Build parent tab UI."""
        root = QVBoxLayout(self)
        self.lbl_header.setWordWrap(True)
        root.addWidget(self.lbl_header)
        self.tab_widget.addTab(self.climate_tab, "Climate Chamber")
        self.tab_widget.addTab(self.glovebox_tab, "Vacuum Glovebox")
        self.tab_widget.addTab(self.indoor_tab, "Indoor Environment")
        root.addWidget(self.tab_widget)

    def load_settings(self, _settings=None) -> None:
        """Compatibility entry for SystemConfigDialog."""
        self.reload_all()

    def reload_all(self) -> None:
        """Reload manager state and refresh child tabs."""
        self.environment_manager.reload_all()
        self.climate_tab.load_from_manager()
        self.glovebox_tab.load_from_manager()
        self.indoor_tab.load_from_manager()

    def get_settings(self) -> dict:
        """Persist current subtab settings.

        Returns:
            dict: Lightweight summary payload for dialog compatibility.
        """
        self.climate_tab.save_current_instance()
        self.glovebox_tab.save_current_instance()
        self.indoor_tab.save_current_instance()
        return {}

    def set_visibility(self, is_visible: bool) -> None:
        """Compatibility hook for dialog tab switching.

        Args:
            is_visible: Whether this tab is currently visible.
        """
        self.setUpdatesEnabled(is_visible)

    def cleanup(self) -> None:
        """Release child resources when the dialog closes."""
        if hasattr(self.climate_tab, "cleanup"):
            self.climate_tab.cleanup()
