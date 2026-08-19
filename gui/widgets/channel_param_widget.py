"""gui/widgets/channel_param_widget.py

Stage 2.5.3 update:
- Add a measurement recipe combo box on top of the existing IV parameter fields.
- Keep the older parameter behavior.
- Align the label column width with the other channel dialog widgets.
"""

from PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QGridLayout, QComboBox
from PyQt6.QtGui import QDoubleValidator, QIntValidator

LABEL_WIDTH = 150


class ChannelParamWidget(QWidget):
    """Measurement parameter widget with recipe-prefill support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        layout = QGridLayout(self)

        self.combo_measurement_recipe = QComboBox()
        self.edit_v_start = QLineEdit()
        self.edit_v_stop = QLineEdit()
        self.edit_v_step = QLineEdit()
        self.edit_delay = QLineEdit()
        self.edit_interval = QLineEdit()
        self.edit_current_limit = QLineEdit()
        self.edit_area = QLineEdit()

        self.edit_v_start.setValidator(QDoubleValidator(-100.0, 100.0, 3))
        self.edit_v_stop.setValidator(QDoubleValidator(-100.0, 100.0, 3))
        self.edit_v_step.setValidator(QDoubleValidator(0.001, 100.0, 3))
        self.edit_delay.setValidator(QIntValidator(0, 60000))
        self.edit_interval.setValidator(QIntValidator(0, 1440))
        self.edit_current_limit.setValidator(QDoubleValidator(0.0, 1.0, 5))
        self.edit_area.setValidator(QDoubleValidator(0.0, 10000.0, 5))

        label_texts = [
            "Measurement Recipe:",
            "電壓起始值 (V):",
            "電壓結束值 (V):",
            "電壓步階 (V):",
            "延遲時間 (ms):",
            "量測間隔 (分鐘):",
            "電流量測限制 (A):",
            "元件面積 (cm²):",
        ]
        labels = [QLabel(text) for text in label_texts]
        for label in labels:
            label.setFixedWidth(LABEL_WIDTH)

        row = 0
        layout.addWidget(labels[0], row, 0)
        layout.addWidget(self.combo_measurement_recipe, row, 1)
        row += 1
        layout.addWidget(labels[1], row, 0)
        layout.addWidget(self.edit_v_start, row, 1)
        row += 1
        layout.addWidget(labels[2], row, 0)
        layout.addWidget(self.edit_v_stop, row, 1)
        row += 1
        layout.addWidget(labels[3], row, 0)
        layout.addWidget(self.edit_v_step, row, 1)
        row += 1
        layout.addWidget(labels[4], row, 0)
        layout.addWidget(self.edit_delay, row, 1)
        row += 1
        layout.addWidget(labels[5], row, 0)
        layout.addWidget(self.edit_interval, row, 1)
        row += 1
        layout.addWidget(labels[6], row, 0)
        layout.addWidget(self.edit_current_limit, row, 1)
        row += 1
        layout.addWidget(labels[7], row, 0)
        layout.addWidget(self.edit_area, row, 1)

        layout.setColumnStretch(1, 1)

    def set_measurement_recipes(self, recipe_names):
        """Populate the measurement recipe combo box."""
        current_text = self.combo_measurement_recipe.currentText()
        self.combo_measurement_recipe.blockSignals(True)
        self.combo_measurement_recipe.clear()
        self.combo_measurement_recipe.addItem("-- 選擇 Recipe --")
        for name in recipe_names or []:
            if name:
                self.combo_measurement_recipe.addItem(str(name))
        if current_text and self.combo_measurement_recipe.findText(current_text) >= 0:
            self.combo_measurement_recipe.setCurrentText(current_text)
        else:
            self.combo_measurement_recipe.setCurrentIndex(0)
        self.combo_measurement_recipe.blockSignals(False)

    def get_data(self):
        def get_float_or_none(editor):
            text = editor.text()
            try:
                return float(text) if text else None
            except ValueError:
                return None

        def get_int_or_none(editor):
            text = editor.text()
            try:
                return int(text) if text else None
            except ValueError:
                return None

        recipe_text = self.combo_measurement_recipe.currentText().strip()
        if recipe_text == "-- 選擇 Recipe --":
            recipe_text = ""

        return {
            "measurement_recipe": recipe_text,
            "v_start": get_float_or_none(self.edit_v_start),
            "v_stop": get_float_or_none(self.edit_v_stop),
            "v_step": get_float_or_none(self.edit_v_step),
            "delay_time": get_int_or_none(self.edit_delay),
            "interval_min": get_int_or_none(self.edit_interval),
            "i_limit": get_float_or_none(self.edit_current_limit),
            "area": get_float_or_none(self.edit_area),
        }

    def set_data(self, data):
        data = data or {}

        def set_text_or_clear(editor, value):
            if value is not None and value != "":
                editor.setText(str(value))
            else:
                editor.clear()

        recipe_name = str(data.get("measurement_recipe", "") or "")
        if recipe_name and self.combo_measurement_recipe.findText(recipe_name) >= 0:
            self.combo_measurement_recipe.setCurrentText(recipe_name)
        elif self.combo_measurement_recipe.count() > 0:
            self.combo_measurement_recipe.setCurrentIndex(0)

        set_text_or_clear(self.edit_v_start, data.get("v_start"))
        set_text_or_clear(self.edit_v_stop, data.get("v_stop"))
        set_text_or_clear(self.edit_v_step, data.get("v_step"))
        set_text_or_clear(self.edit_delay, data.get("delay_time"))
        set_text_or_clear(self.edit_interval, data.get("interval_min"))
        set_text_or_clear(self.edit_current_limit, data.get("i_limit"))
        set_text_or_clear(self.edit_area, data.get("area"))
