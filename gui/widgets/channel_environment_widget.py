"""gui/widgets/channel_environment_widget.py

Stage 2.5.3 update:
- Extract the environment block from ChannelActionWidget.
- Provide environment dropdown and environment-recipe dropdown.
- Align the label column width with the other channel dialog widgets.
"""

from PyQt6.QtWidgets import QWidget, QLabel, QComboBox, QGridLayout

LABEL_WIDTH = 150


class ChannelEnvironmentWidget(QWidget):
    """Environment selection widget for one channel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        layout = QGridLayout(self)

        self.combo_environment = QComboBox()
        self.label_environment_type = QLabel("-")
        self.combo_environment_recipe = QComboBox()

        labels = [
            QLabel("Environment:"),
            QLabel("Environment Type:"),
            QLabel("環境 Recipe:"),
        ]
        for label in labels:
            label.setFixedWidth(LABEL_WIDTH)

        layout.addWidget(labels[0], 0, 0)
        layout.addWidget(self.combo_environment, 0, 1)

        layout.addWidget(labels[1], 1, 0)
        layout.addWidget(self.label_environment_type, 1, 1)

        layout.addWidget(labels[2], 2, 0)
        layout.addWidget(self.combo_environment_recipe, 2, 1)

        layout.setColumnStretch(1, 1)

    def set_environment_options(self, environment_list):
        """Populate environment combo options."""
        current = self.combo_environment.currentText()
        self.combo_environment.blockSignals(True)
        self.combo_environment.clear()
        for item in environment_list or []:
            self.combo_environment.addItem(str(item))
        if current and self.combo_environment.findText(current) >= 0:
            self.combo_environment.setCurrentText(current)
        elif self.combo_environment.count() > 0:
            self.combo_environment.setCurrentIndex(0)
        self.combo_environment.blockSignals(False)

    def set_environment_recipe_options(self, recipe_list):
        """Populate environment recipe combo options."""
        current = self.combo_environment_recipe.currentText()
        self.combo_environment_recipe.blockSignals(True)
        self.combo_environment_recipe.clear()
        self.combo_environment_recipe.addItem("")
        for item in recipe_list or []:
            if item:
                self.combo_environment_recipe.addItem(str(item))
        if current and self.combo_environment_recipe.findText(current) >= 0:
            self.combo_environment_recipe.setCurrentText(current)
        elif self.combo_environment_recipe.count() > 0:
            self.combo_environment_recipe.setCurrentIndex(0)
        self.combo_environment_recipe.blockSignals(False)

    def set_environment_meta(self, env_type):
        """Update environment type label."""
        self.label_environment_type.setText(str(env_type or "-"))

    def set_data(self, data):
        """Apply saved environment selection data."""
        data = data or {}
        env_instance = data.get("environment_instance")
        env_recipe = data.get("environment_recipe")

        if env_instance and self.combo_environment.findText(str(env_instance)) != -1:
            self.combo_environment.setCurrentText(str(env_instance))
        elif self.combo_environment.count() > 0 and self.combo_environment.currentIndex() < 0:
            self.combo_environment.setCurrentIndex(0)

        if env_recipe and self.combo_environment_recipe.findText(str(env_recipe)) != -1:
            self.combo_environment_recipe.setCurrentText(str(env_recipe))

    def get_data(self):
        """Return current environment selection."""
        return {
            "environment_instance": self.combo_environment.currentText().strip(),
            "environment_recipe": self.combo_environment_recipe.currentText().strip(),
        }
