"""gui/config_tabs/environment_tab/climate_chamber_widgets/chamber_status_widget.py

Stage 2.6 update:
- Split the old chamber_tab status monitor section into a reusable widget.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QGroupBox, QLabel


class ChamberStatusWidget(QGroupBox):
    """Status monitor widget for chamber PV/SV display."""

    def __init__(self, parent=None) -> None:
        super().__init__("狀態監控", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the status grid."""
        status_grid = QGridLayout(self)

        self.temp_pv_label = self._create_label_for_grid("--.- °C", "temp_pv")
        self.temp_sv_label = self._create_label_for_grid("--.- °C", "temp_sv")
        self.hum_pv_label = self._create_label_for_grid("--.- %", "hum_pv")
        self.hum_sv_label = self._create_label_for_grid("--.- %", "hum_sv")

        status_grid.addWidget(QLabel("溫度 T (°C)"), 0, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)
        status_grid.addWidget(QLabel("濕度 H (%)"), 0, 2, 1, 2, Qt.AlignmentFlag.AlignCenter)
        status_grid.addWidget(QLabel("PV (實際)"), 1, 0)
        status_grid.addWidget(QLabel("SV (設定)"), 1, 1)
        status_grid.addWidget(QLabel("PV (實際)"), 1, 2)
        status_grid.addWidget(QLabel("SV (設定)"), 1, 3)
        status_grid.addWidget(self.temp_pv_label, 2, 0)
        status_grid.addWidget(self.temp_sv_label, 2, 1)
        status_grid.addWidget(self.hum_pv_label, 2, 2)
        status_grid.addWidget(self.hum_sv_label, 2, 3)

    def _create_label_for_grid(self, text: str, prop: str) -> QLabel:
        """Create one centered status label."""
        label = QLabel(text)
        label.setProperty("display", prop)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _format_value(value, suffix: str, missing_text: str) -> str:
        """Format one status value and tolerate None sentinel fields.

        Args:
            value: Numeric status value or None when the chamber reports an
                unused analog field such as ``7FFF``.
            suffix: Display suffix.
            missing_text: Text to show for unavailable values.

        Returns:
            Safe label text.
        """
        if value is None:
            return missing_text
        try:
            return f"{float(value):.1f}{suffix}"
        except (TypeError, ValueError):
            return missing_text

    def update_status(self, temp_pv, temp_sv, hum_pv, hum_sv) -> None:
        """Update displayed chamber status values without formatting None."""
        self.temp_pv_label.setText(self._format_value(temp_pv, " °C", "ERR °C"))
        self.temp_sv_label.setText(self._format_value(temp_sv, " °C", "--.- °C"))
        self.hum_pv_label.setText(self._format_value(hum_pv, " %", "ERR %"))
        self.hum_sv_label.setText(self._format_value(hum_sv, " %", "--.- %"))

    def show_error(self) -> None:
        """Show error state when read_status fails."""
        self.temp_pv_label.setText("ERR °C")
        self.temp_sv_label.setText("--.- °C")
        self.hum_pv_label.setText("ERR %")
        self.hum_sv_label.setText("--.- %")
