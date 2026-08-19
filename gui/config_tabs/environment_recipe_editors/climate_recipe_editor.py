"""gui/config_tabs/environment_recipe_editors/climate_recipe_editor.py

Stage 3.0 skeleton:
- Climate recipe editor field model only.
- No hardware control is executed in this editor.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox

from .base_environment_recipe_editor import BaseEnvironmentRecipeEditor


class ClimateRecipeEditor(BaseEnvironmentRecipeEditor):
    """Editor for climate environment recipes."""

    environment_type = "climate"

    def __init__(self, parent=None) -> None:
        """Initialize climate-specific fields."""
        super().__init__(parent)

        self.spin_temperature_c = QDoubleSpinBox()
        self.spin_temperature_c.setRange(-40.0, 150.0)
        self.spin_temperature_c.setSuffix(" °C")

        self.spin_humidity_rh = QDoubleSpinBox()
        self.spin_humidity_rh.setRange(0.0, 100.0)
        self.spin_humidity_rh.setSuffix(" %RH")

        self.spin_illuminance_lux = QDoubleSpinBox()
        self.spin_illuminance_lux.setRange(0.0, 200000.0)
        self.spin_illuminance_lux.setSuffix(" Lux")

        self.chk_light_on = QCheckBox("Light On")

        self.form.addRow("溫度", self.spin_temperature_c)
        self.form.addRow("濕度", self.spin_humidity_rh)
        self.form.addRow("照度", self.spin_illuminance_lux)
        self.form.addRow("燈控", self.chk_light_on)

    def set_recipe_data(self, data: dict) -> None:
        """Populate editor fields from recipe data."""
        super().set_recipe_data(data)
        data = data or {}
        self.spin_temperature_c.setValue(float(data.get("temperature_c", 25.0)))
        self.spin_humidity_rh.setValue(float(data.get("humidity_rh", 50.0)))
        self.spin_illuminance_lux.setValue(float(data.get("illuminance_lux", 1000.0)))
        self.chk_light_on.setChecked(bool(data.get("light_on", False)))

    def get_recipe_data(self) -> dict:
        """Return full climate recipe data."""
        data = super().get_recipe_data()
        data.update({
            "temperature_c": self.spin_temperature_c.value(),
            "humidity_rh": self.spin_humidity_rh.value(),
            "illuminance_lux": self.spin_illuminance_lux.value(),
            "light_on": self.chk_light_on.isChecked(),
        })
        return data
