"""gui/config_tabs/rline_diagnostics_tab.py

R-line calibration diagnostics for ReliabilityX Pro.

The tab evaluates only active channel relay pairs for readiness, and provides an
environment-filtered 3D R-line surface/scatter view where X = SMU+ relay, Y =
SMU- relay, and Z = measured line resistance.  Matplotlib is optional; if it is
not available, the diagnostic table remains fully functional.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

import config
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:  # pragma: no cover - optional plotting dependency
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover
    FigureCanvas = None
    Figure = None


class RLineDiagnosticsTab(QWidget):
    """Display active R-line readiness and environment-filtered R-line 3D map."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the diagnostics tab."""
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        """Build the diagnostics UI."""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        hint = QLabel(
            "R-line readiness 只檢查目前 active channel cards 實際使用的 relay pair。\n"
            "3D 圖以環境做動態切分：X = SMU+ relay，Y = SMU− relay，Z = R-line Ω，用來快速找出異常接點或異常線段。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555555;")
        root.addWidget(hint)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Environment:"))
        self.combo_environment = QComboBox()
        controls.addWidget(self.combo_environment)
        self.chk_active_only = QCheckBox("只顯示 active channel pairs")
        self.chk_active_only.setChecked(True)
        controls.addWidget(self.chk_active_only)
        self.btn_refresh = QPushButton("Refresh")
        controls.addWidget(self.btn_refresh)
        controls.addStretch(1)
        root.addLayout(controls)

        self.summary_label = QLabel("--")
        self.summary_label.setStyleSheet("font-weight: 700; color: #1F1F1F;")
        root.addWidget(self.summary_label)

        top_row = QHBoxLayout()
        top_row.addWidget(self._build_active_table_group(), 3)
        top_row.addWidget(self._build_chart_group(), 4)
        root.addLayout(top_row, 3)
        root.addWidget(self._build_matrix_table_group(), 2)

        self.btn_refresh.clicked.connect(self.refresh)
        self.combo_environment.currentTextChanged.connect(lambda _text: self._refresh_plot_and_matrix())
        self.chk_active_only.stateChanged.connect(lambda _state: self._refresh_plot_and_matrix())

    def _build_active_table_group(self) -> QGroupBox:
        """Build active channel readiness table."""
        group = QGroupBox("Active Channel R-line Readiness")
        layout = QVBoxLayout(group)
        self.active_table = QTableWidget(0, 8)
        self.active_table.setHorizontalHeaderLabels(["Channel", "Env", "SMU+", "SMU−", "R-line Ω", "Age d", "Status", "Device"])
        self.active_table.verticalHeader().setVisible(False)
        self.active_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.active_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.active_table)
        return group

    def _build_chart_group(self) -> QGroupBox:
        """Build optional 3D chart area."""
        group = QGroupBox("3D R-line Map")
        layout = QVBoxLayout(group)
        if FigureCanvas is not None and Figure is not None:
            self.figure = Figure(figsize=(5, 4))
            self.canvas = FigureCanvas(self.figure)
            layout.addWidget(self.canvas)
            self.chart_placeholder = None
        else:
            self.figure = None
            self.canvas = None
            self.chart_placeholder = QLabel("Matplotlib 未安裝；仍可使用下方 table 進行 R-line 診斷。")
            self.chart_placeholder.setWordWrap(True)
            self.chart_placeholder.setStyleSheet("color: #B36B00;")
            layout.addWidget(self.chart_placeholder)
        return group

    def _build_matrix_table_group(self) -> QGroupBox:
        """Build calibrated pair matrix detail table."""
        group = QGroupBox("Calibrated Pair Details by Environment")
        layout = QVBoxLayout(group)
        self.matrix_table = QTableWidget(0, 8)
        self.matrix_table.setHorizontalHeaderLabels(["Env", "SMU+", "SMU−", "R-line Ω", "Age d", "Status", "Outlier", "Time"])
        self.matrix_table.verticalHeader().setVisible(False)
        self.matrix_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.matrix_table)
        return group

    def refresh(self) -> None:
        """Refresh environment list, active readiness, and 3D diagnostics."""
        self._populate_environment_filter()
        self._populate_active_readiness()
        self._refresh_plot_and_matrix()

    def _populate_environment_filter(self) -> None:
        """Populate environment filter from environment_profiles.json."""
        profiles = config.load_environment_profiles()
        current_data = self.combo_environment.currentData()
        self.combo_environment.blockSignals(True)
        self.combo_environment.clear()
        for env_id, item in (profiles.get("instances", {}) or {}).items():
            self.combo_environment.addItem(f"{item.get('title', env_id)} ({env_id})", env_id)
        if current_data:
            idx = self.combo_environment.findData(current_data)
            if idx >= 0:
                self.combo_environment.setCurrentIndex(idx)
        self.combo_environment.blockSignals(False)

    def _populate_active_readiness(self) -> None:
        """Fill active channel R-line readiness table."""
        rows = config.evaluate_active_rline_readiness()
        missing = sum(1 for row in rows if row.get("status") == "Missing")
        expired = sum(1 for row in rows if row.get("status") == "Expired")
        valid = sum(1 for row in rows if row.get("status") == "Valid")
        self.summary_label.setText(f"Active pairs: {len(rows)} | Valid: {valid} | Missing: {missing} | Expired: {expired}")
        self.active_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row.get("channel_label", ""),
                row.get("environment_instance", ""),
                row.get("pos_pin", ""),
                row.get("neg_pin", ""),
                "" if row.get("value") is None else f"{float(row.get('value')):.4f}",
                "" if row.get("age_days") is None else f"{float(row.get('age_days')):.1f}",
                row.get("status", ""),
                row.get("device_name", ""),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c in {2, 3, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.active_table.setItem(r, c, item)

    def _selected_environment_id(self) -> str:
        """Return selected environment id."""
        return str(self.combo_environment.currentData() or "")

    def _environment_ranges(self, env_id: str) -> Tuple[range, range]:
        """Return plus/minus ranges for an environment."""
        item = (config.load_environment_profiles().get("instances", {}) or {}).get(env_id, {})
        try:
            plus = range(int(item.get("smu_plus_start")), int(item.get("smu_plus_end")) + 1)
            minus = range(int(item.get("smu_minus_start")), int(item.get("smu_minus_end")) + 1)
            return plus, minus
        except (TypeError, ValueError):
            return range(0), range(0)

    def _load_rline_points(self) -> List[Dict[str, Any]]:
        """Load R-line points filtered by selected environment and active-only mode."""
        env_id = self._selected_environment_id()
        plus_range, minus_range = self._environment_ranges(env_id)
        calibration = config.load_json_file(config.CALIBRATION_SETTINGS_FILE)
        line_map = calibration.get("line_resistance_map", {}) if isinstance(calibration, dict) else {}
        active_pairs = set()
        if self.chk_active_only.isChecked():
            for record in config.get_active_channel_records():
                try:
                    active_pairs.add((int(record.get("relay_pos")), int(record.get("relay_neg"))))
                except (TypeError, ValueError):
                    continue
        points = []
        for key, raw in (line_map or {}).items():
            try:
                pos_s, neg_s = str(key).split("_", 1)
                pos, neg = int(pos_s), int(neg_s)
            except (ValueError, TypeError):
                continue
            if pos not in plus_range or neg not in minus_range:
                continue
            if active_pairs and (pos, neg) not in active_pairs:
                continue
            status = config.evaluate_rline_calibration(pos, neg, calibration_data=calibration)
            if status.get("value") is None:
                continue
            points.append({
                "environment_id": env_id,
                "pos": pos,
                "neg": neg,
                "value": float(status.get("value")),
                "age_days": status.get("age_days"),
                "expired": status.get("expired"),
                "time": (status.get("record") or {}).get("time", ""),
            })
        return points

    def _flag_outliers(self, points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flag R-line outliers relative to the environment median."""
        if not points:
            return points
        values = [float(item["value"]) for item in points]
        median = statistics.median(values)
        for item in points:
            value = float(item["value"])
            if median <= 0:
                level = "Normal"
            else:
                delta_ratio = abs(value - median) / median
                if delta_ratio > 0.50:
                    level = "Critical"
                elif delta_ratio > 0.20:
                    level = "Warning"
                else:
                    level = "Normal"
            item["outlier"] = level
            item["median"] = median
        return points

    def _refresh_plot_and_matrix(self) -> None:
        """Refresh the 3D plot and calibrated-pair table."""
        points = self._flag_outliers(self._load_rline_points())
        self._populate_matrix_table(points)
        self._plot_points(points)

    def _populate_matrix_table(self, points: List[Dict[str, Any]]) -> None:
        """Render detailed calibrated-pair table."""
        self.matrix_table.setRowCount(len(points))
        for r, point in enumerate(points):
            status = "Expired" if point.get("expired") else "Valid"
            values = [
                point.get("environment_id", ""),
                point.get("pos", ""),
                point.get("neg", ""),
                f"{point.get('value', 0):.4f}",
                "" if point.get("age_days") is None else f"{float(point.get('age_days')):.1f}",
                status,
                point.get("outlier", ""),
                point.get("time", ""),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c in {1, 2, 3, 4}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.matrix_table.setItem(r, c, item)

    def _plot_points(self, points: List[Dict[str, Any]]) -> None:
        """Draw the optional 3D R-line scatter plot."""
        if self.figure is None or self.canvas is None:
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111, projection="3d")
        ax.set_xlabel("SMU+ Relay")
        ax.set_ylabel("SMU− Relay")
        ax.set_zlabel("R-line (Ω)")
        if points:
            xs = [p["pos"] for p in points]
            ys = [p["neg"] for p in points]
            zs = [p["value"] for p in points]
            ax.scatter(xs, ys, zs)
        ax.set_title("Environment-filtered R-line map")
        self.canvas.draw_idle()
