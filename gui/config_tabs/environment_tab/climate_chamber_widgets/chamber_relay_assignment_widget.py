"""gui/config_tabs/environment_tab/climate_chamber_widgets/chamber_relay_assignment_widget.py

Stage 2.6.2 update:
- Extract the climate tab top SMU relay assignment section into its own widget.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFormLayout, QGroupBox


class ChamberRelayAssignmentWidget(QGroupBox):
    """SMU relay assignment widget for the climate chamber tab."""

    def __init__(self, parent=None) -> None:
        super().__init__("SMU Relay Assignment", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the relay assignment controls."""
        form = QFormLayout(self)

        self.combo_plus_start = QComboBox()
        self.combo_plus_end = QComboBox()
        self.combo_minus_start = QComboBox()
        self.combo_minus_end = QComboBox()

        for combo, start, end in [
            (self.combo_plus_start, 0, 31),
            (self.combo_plus_end, 0, 31),
            (self.combo_minus_start, 32, 63),
            (self.combo_minus_end, 32, 63),
        ]:
            combo.addItems([str(i) for i in range(start, end + 1)])

        form.addRow("SMU+ 起始", self.combo_plus_start)
        form.addRow("SMU+ 結束", self.combo_plus_end)
        form.addRow("SMU- 起始", self.combo_minus_start)
        form.addRow("SMU- 結束", self.combo_minus_end)

    def set_ranges(self, plus_start: int, plus_end: int, minus_start: int, minus_end: int) -> None:
        """Apply saved relay ranges."""
        self.combo_plus_start.setCurrentText(str(plus_start))
        self.combo_plus_end.setCurrentText(str(plus_end))
        self.combo_minus_start.setCurrentText(str(minus_start))
        self.combo_minus_end.setCurrentText(str(minus_end))

    def get_plus_start(self) -> int:
        """Return current SMU+ start relay number."""
        return int(self.combo_plus_start.currentText())

    def get_plus_end(self) -> int:
        """Return current SMU+ end relay number."""
        return int(self.combo_plus_end.currentText())

    def get_minus_start(self) -> int:
        """Return current SMU- start relay number."""
        return int(self.combo_minus_start.currentText())

    def get_minus_end(self) -> int:
        """Return current SMU- end relay number."""
        return int(self.combo_minus_end.currentText())
