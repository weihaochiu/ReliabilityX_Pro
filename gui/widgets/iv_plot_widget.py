from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    import pyqtgraph as pg

    _HAS_PYQTGRAPH = True
except ImportError:
    pg = None
    _HAS_PYQTGRAPH = False

logger = logging.getLogger(__name__)


class _DummyCurve:
    """Fallback curve object when pyqtgraph is unavailable."""

    def setData(self, *args, **kwargs):
        pass

    def clear(self):
        pass

    def setPen(self, *args, **kwargs):
        pass

    def setVisible(self, *args, **kwargs):
        pass


class IVPlotWidget(QWidget):
    """
    IVPlotWidget: A dedicated widget for displaying IV curve plots using pyqtgraph.

    修正版重點：
    - 保留目前 settings / y_mode / direction 相容邏輯
    - 即時更新時只做 append + setData，不再每點重建 legend
    - legend 只在初始化 / 套用設定 / 重畫全圖時重建
    - 降低 pyqtgraph TextItem / legend label 動態操作導致的繪圖異常風險
    """

    export_requested = pyqtSignal()

    CURVE_KEYS = ("fwd_raw", "fwd_corr", "rev_raw", "rev_corr")

    CURVE_DEFAULT_NAMES = {
        "fwd_raw": "正掃 (原始)",
        "fwd_corr": "正掃 (修正)",
        "rev_raw": "逆掃 (原始)",
        "rev_corr": "逆掃 (修正)",
    }

    LINE_STYLE_MAP = {
        "solid": Qt.PenStyle.SolidLine,
        "dash": Qt.PenStyle.DashLine,
        "dot": Qt.PenStyle.DotLine,
        "dashdot": Qt.PenStyle.DashDotLine,
        "dashdotdot": Qt.PenStyle.DashDotDotLine,
    }

    LEGEND_ANCHOR_MAP = {
        "top_right": ((1, 0), (1, 0), (-10, 10)),
        "top_left": ((0, 0), (0, 0), (10, 10)),
        "bottom_right": ((1, 1), (1, 1), (-10, -10)),
        "bottom_left": ((0, 1), (0, 1), (10, -10)),
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.plot_settings: Dict[str, Any] = self.load_plot_settings()
        self._legend = None
        self._plot_item = None
        self._tick_font = None
        self._last_area: float = 1.0

        # 每個點保存為 (voltage[V], current[A])
        self.data_store: Dict[str, List[Tuple[float, float]]] = {
            "fwd_raw": [],
            "fwd_corr": [],
            "rev_raw": [],
            "rev_corr": [],
        }

        self._init_ui()
        self.apply_plot_settings(self.plot_settings)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _HAS_PYQTGRAPH:
            self.plot_widget = pg.PlotWidget()
            self._plot_item = self.plot_widget.getPlotItem()

            self.curves = {
                "fwd_raw": self.plot_widget.plot([], []),
                "fwd_corr": self.plot_widget.plot([], []),
                "rev_raw": self.plot_widget.plot([], []),
                "rev_corr": self.plot_widget.plot([], []),
            }
        else:
            logger.warning("pyqtgraph is not installed. Plotting functionality will be disabled.")
            self.plot_widget = QLabel("pyqtgraph 未安裝，圖表功能已停用。")
            self.plot_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.curves = {k: _DummyCurve() for k in self.CURVE_KEYS}

        layout.addWidget(self.plot_widget)

    @classmethod
    def default_plot_settings(cls) -> Dict[str, Any]:
        return {
            "general": {
                "title": "實時 I-V 曲線掃描",
                "background_color": "#FFFFFF",
            },
            "font": {
                "title_size": 14,
                "axis_title_size": 12,
                "tick_size": 10,
                "legend_size": 10,
            },
            "axis": {
                "auto_range": True,
                "x_min": -0.2,
                "x_max": 1.2,
                "y_min": -30.0,
                "y_max": 5.0,
                "lock_fourth_quadrant": False,
                "y_mode": "current_density",
            },
            "grid": {
                "show_x": True,
                "show_y": True,
                "color": "#BFBFBF",
                "alpha": 30,
                "line_style": "solid",
            },
            "legend": {
                "show": True,
                "position": "top_right",
            },
            "curves": {
                "fwd_raw": {
                    "visible": True,
                    "name": "正掃 (原始)",
                    "color": "#A0C4FF",
                    "width": 1,
                    "line_style": "dash",
                },
                "fwd_corr": {
                    "visible": True,
                    "name": "正掃 (修正)",
                    "color": "#0078D4",
                    "width": 3,
                    "line_style": "solid",
                },
                "rev_raw": {
                    "visible": True,
                    "name": "逆掃 (原始)",
                    "color": "#FFADAD",
                    "width": 1,
                    "line_style": "dash",
                },
                "rev_corr": {
                    "visible": True,
                    "name": "逆掃 (修正)",
                    "color": "#D32F2F",
                    "width": 3,
                    "line_style": "solid",
                },
            },
            "export": {
                "format": "png",
                "dpi": 150,
            },
        }

    def _resolve_settings_file(self) -> Path:
        """
        目標：project_root / config / iv_plot_settings.json
        本檔通常位於 gui/widgets/iv_plot_widget.py
        """
        try:
            current_file = Path(__file__).resolve()
            project_root = current_file.parents[2]
        except Exception:
            project_root = Path.cwd()

        config_dir = project_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "iv_plot_settings.json"

    def load_plot_settings(self) -> Dict[str, Any]:
        defaults = self.default_plot_settings()
        settings_file = self._resolve_settings_file()

        if not settings_file.exists():
            return defaults

        try:
            with settings_file.open("r", encoding="utf-8") as f:
                loaded = json.load(f)

            if not isinstance(loaded, dict):
                return defaults

            merged = copy.deepcopy(defaults)
            self._deep_update(merged, loaded)
            return merged

        except Exception as e:
            logger.warning("Failed to load iv_plot_settings.json: %s", e)
            return defaults

    @staticmethod
    def _deep_update(base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        for key, value in incoming.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                IVPlotWidget._deep_update(base[key], value)
            else:
                base[key] = value

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _get_curve_cfg(self, curve_key: str) -> Dict[str, Any]:
        curve_cfg = self.plot_settings.get("curves", {}).get(curve_key, {})
        return {
            "visible": bool(curve_cfg.get("visible", True)),
            "name": str(curve_cfg.get("name", self.CURVE_DEFAULT_NAMES.get(curve_key, curve_key))),
            "color": str(curve_cfg.get("color", "#000000")),
            "width": int(curve_cfg.get("width", 2)),
            "line_style": str(curve_cfg.get("line_style", "solid")),
        }

    def _make_pen(self, color: str, width: int, line_style: str):
        if not _HAS_PYQTGRAPH:
            return None

        qt_style = self.LINE_STYLE_MAP.get(str(line_style).lower(), Qt.PenStyle.SolidLine)
        return pg.mkPen(color=color, width=max(1, int(width)), style=qt_style)

    def _get_y_axis_label(self) -> str:
        mode = self.plot_settings.get("axis", {}).get("y_mode", "current_density")
        if mode == "current":
            return "Current (mA)"
        if mode == "power":
            return "Power (mW)"
        return "Current Density (mA/cm²)"

    def _convert_y_value(self, voltage: float, current: float, area: float) -> float:
        """
        current: A
        voltage: V
        回傳：
        - current: mA
        - current_density: mA/cm²
        - power: mW
        """
        mode = self.plot_settings.get("axis", {}).get("y_mode", "current_density")

        voltage = self._safe_float(voltage, 0.0)
        current = self._safe_float(current, 0.0)
        area = self._safe_float(area, 1.0)

        if area == 0:
            area = 1.0

        if mode == "current":
            return current * 1000.0

        if mode == "power":
            return voltage * current * 1000.0

        return (current / area) * 1000.0

    def _set_title(self):
        if not _HAS_PYQTGRAPH:
            return

        general_cfg = self.plot_settings.get("general", {})
        font_cfg = self.plot_settings.get("font", {})

        title = str(general_cfg.get("title", "實時 I-V 曲線掃描"))
        title_size = int(font_cfg.get("title_size", 14))

        try:
            self._plot_item.setTitle(title, color="#222222", size=f"{title_size}pt")
        except Exception as e:
            logger.debug("Failed to set title: %s", e)

    def _set_background(self):
        if not _HAS_PYQTGRAPH:
            return

        general_cfg = self.plot_settings.get("general", {})
        bg = str(general_cfg.get("background_color", "#FFFFFF"))
        try:
            self.plot_widget.setBackground(bg)
        except Exception as e:
            logger.debug("Failed to set background color: %s", e)

    def _set_axis_fonts_and_labels(self):
        if not _HAS_PYQTGRAPH:
            return

        font_cfg = self.plot_settings.get("font", {})
        axis_title_size = int(font_cfg.get("axis_title_size", 12))
        tick_size = int(font_cfg.get("tick_size", 10))

        label_style = {
            "color": "#333333",
            "font-size": f"{axis_title_size}pt",
        }

        try:
            self._plot_item.setLabel("left", self._get_y_axis_label(), **label_style)
            self._plot_item.setLabel("bottom", "Voltage (V)", **label_style)
        except Exception as e:
            logger.debug("Failed to set axis labels: %s", e)

        try:
            from PyQt6.QtGui import QFont

            self._tick_font = QFont()
            self._tick_font.setPointSize(tick_size)

            for axis_name in ("left", "bottom"):
                axis = self._plot_item.getAxis(axis_name)
                axis.setStyle(tickFont=self._tick_font)
                axis.setTextPen(pg.mkPen("#333333"))
                axis.setPen(pg.mkPen("#333333"))
        except Exception as e:
            logger.debug("Failed to set axis fonts: %s", e)

    def _set_grid(self):
        if not _HAS_PYQTGRAPH:
            return

        grid_cfg = self.plot_settings.get("grid", {})
        show_x = bool(grid_cfg.get("show_x", True))
        show_y = bool(grid_cfg.get("show_y", True))
        alpha_percent = int(grid_cfg.get("alpha", 30))
        alpha_01 = max(0.0, min(1.0, alpha_percent / 100.0))

        try:
            self.plot_widget.showGrid(x=show_x, y=show_y, alpha=alpha_01)
        except Exception as e:
            logger.debug("Failed to set grid: %s", e)

    def _apply_curve_styles(self):
        if not _HAS_PYQTGRAPH:
            return

        for curve_key in self.CURVE_KEYS:
            cfg = self._get_curve_cfg(curve_key)
            curve = self.curves[curve_key]
            try:
                curve.setPen(self._make_pen(cfg["color"], cfg["width"], cfg["line_style"]))
                curve.setVisible(cfg["visible"])
            except Exception as e:
                logger.debug("Failed to apply style to %s: %s", curve_key, e)

    def _clear_legend(self):
        if not _HAS_PYQTGRAPH:
            return

        if self._legend is not None:
            try:
                scene = self._legend.scene()
                if scene is not None:
                    scene.removeItem(self._legend)
            except Exception:
                pass
            self._legend = None

    def _rebuild_legend(self):
        """
        只在初始化 / 套用設定 / 全圖重畫時重建 legend。
        不在每個點更新時重建，避免 pyqtgraph TextItem / repaint 異常。
        """
        if not _HAS_PYQTGRAPH:
            return

        legend_cfg = self.plot_settings.get("legend", {})
        show_legend = bool(legend_cfg.get("show", True))
        position = str(legend_cfg.get("position", "top_right"))

        self._clear_legend()

        if not show_legend:
            return

        try:
            self._legend = self.plot_widget.addLegend()
        except Exception as e:
            logger.debug("Failed to create legend: %s", e)
            self._legend = None
            return

        for curve_key in self.CURVE_KEYS:
            cfg = self._get_curve_cfg(curve_key)
            if not cfg["visible"]:
                continue

            try:
                self._legend.addItem(self.curves[curve_key], cfg["name"])
            except Exception as e:
                logger.debug("Failed to add legend item for %s: %s", curve_key, e)

        anchor = self.LEGEND_ANCHOR_MAP.get(position, self.LEGEND_ANCHOR_MAP["top_right"])
        try:
            self._legend.anchor(
                itemPos=anchor[0],
                parentPos=anchor[1],
                offset=anchor[2],
            )
        except Exception as e:
            logger.debug("Failed to position legend: %s", e)

        # 這裡故意不再逐項操作 label.setAttr("color"/"size")
        # 以避免不同 pyqtgraph 版本下 TextItem/brush 異常。

    def _apply_axis_range(self):
        if not _HAS_PYQTGRAPH:
            return

        axis_cfg = self.plot_settings.get("axis", {})
        auto_range = bool(axis_cfg.get("auto_range", True))
        y_mode = str(axis_cfg.get("y_mode", "current_density"))
        lock_fourth = bool(axis_cfg.get("lock_fourth_quadrant", False))

        if auto_range:
            try:
                self._plot_item.enableAutoRange()
                self._plot_item.vb.autoRange()
            except Exception as e:
                logger.debug("Failed to enable auto range: %s", e)
            return

        try:
            self._plot_item.disableAutoRange()
        except Exception:
            pass

        x_min = self._safe_float(axis_cfg.get("x_min", -0.2), -0.2)
        x_max = self._safe_float(axis_cfg.get("x_max", 1.2), 1.2)
        y_min = self._safe_float(axis_cfg.get("y_min", -30.0), -30.0)
        y_max = self._safe_float(axis_cfg.get("y_max", 5.0), 5.0)

        if lock_fourth and y_mode in ("current", "current_density"):
            x_min = 0.0
            y_max = 0.0

        if x_min >= x_max:
            x_min, x_max = -0.2, 1.2
        if y_min >= y_max:
            y_min, y_max = -30.0, 5.0

        try:
            self._plot_item.setXRange(x_min, x_max, padding=0.0)
            self._plot_item.setYRange(y_min, y_max, padding=0.0)
        except Exception as e:
            logger.debug("Failed to set axis range: %s", e)

    def _extract_xy_for_curve(self, curve_key: str) -> Tuple[List[float], List[float]]:
        points = self.data_store.get(curve_key, [])
        xs: List[float] = []
        ys: List[float] = []

        for v, i in points:
            xs.append(v)
            ys.append(self._convert_y_value(v, i, self._last_area))

        return xs, ys

    def _update_single_curve(self, curve_key: str):
        if not _HAS_PYQTGRAPH:
            return

        x_data, y_data = self._extract_xy_for_curve(curve_key)
        try:
            self.curves[curve_key].setData(x_data, y_data)
        except Exception as e:
            logger.debug("Failed to update %s: %s", curve_key, e)

    def refresh_plot_from_store(self):
        """
        根據目前 data_store 與 plot_settings 重畫全部曲線。
        只在 clear / settings apply / y_mode 切換時使用。
        """
        if not _HAS_PYQTGRAPH:
            return

        for curve_key in self.CURVE_KEYS:
            self._update_single_curve(curve_key)

        self._set_title()
        self._set_background()
        self._set_axis_fonts_and_labels()
        self._set_grid()
        self._apply_curve_styles()
        self._rebuild_legend()
        self._apply_axis_range()

    @pyqtSlot(dict)
    def apply_plot_settings(self, settings: Dict[str, Any]):
        """
        套用新的 plot settings。
        settings 格式需對應 iv_plot_settings.json。
        """
        if not isinstance(settings, dict):
            return

        merged = self.default_plot_settings()
        self._deep_update(merged, settings)
        self.plot_settings = merged

        if not _HAS_PYQTGRAPH:
            return

        self.refresh_plot_from_store()

    @pyqtSlot()
    def clear_plot(self):
        """Clears all data from the plot."""
        self.data_store = {
            "fwd_raw": [],
            "fwd_corr": [],
            "rev_raw": [],
            "rev_corr": [],
        }
        self._last_area = 1.0

        for curve in self.curves.values():
            try:
                curve.setData([], [])
            except Exception:
                pass

        if _HAS_PYQTGRAPH:
            # 清空後仍保持目前外觀設定
            self._set_title()
            self._set_background()
            self._set_axis_fonts_and_labels()
            self._set_grid()
            self._apply_curve_styles()
            self._rebuild_legend()
            self._apply_axis_range()

    def _normalize_direction(self, direction: Any) -> str:
        """
        保留修改前可正常出線版本的方向判斷相容性：
        - 只要包含 fwd -> forward
        - 其他大多落到 reverse
        """
        text = str(direction or "").strip().lower()

        if "fwd" in text:
            return "fwd"

        if text in {"f", "forward", "for", "正掃", "正向"}:
            return "fwd"

        if "rev" in text or "reverse" in text:
            return "rev"

        if text in {"r", "backward", "back", "逆掃", "反掃", "反向"}:
            return "rev"

        if "forw" in text:
            return "fwd"

        if "back" in text:
            return "rev"

        return "rev"

    @pyqtSlot(dict)
    def update_plot(self, point: Dict[str, Any]):
        """
        Receives and plots a single data point.

        point fields expected:
        - direction
        - v_src
        - i_msd
        - v_corr
        - i_corr
        - area (optional)
        """
        if not isinstance(point, dict):
            return

        direction = self._normalize_direction(point.get("direction", "fwd"))

        area = self._safe_float(
            point.get("area", self._last_area if self._last_area != 0 else 1.0),
            1.0,
        )
        if area == 0:
            area = 1.0
        self._last_area = area

        v_src = self._safe_float(point.get("v_src", 0.0), 0.0)
        i_msd = self._safe_float(point.get("i_msd", 0.0), 0.0)
        v_corr = self._safe_float(point.get("v_corr", v_src), v_src)
        i_corr = self._safe_float(point.get("i_corr", i_msd), i_msd)

        if direction == "fwd":
            self.data_store["fwd_raw"].append((v_src, i_msd))
            self.data_store["fwd_corr"].append((v_corr, i_corr))

            self._update_single_curve("fwd_raw")
            self._update_single_curve("fwd_corr")
        else:
            self.data_store["rev_raw"].append((v_src, i_msd))
            self.data_store["rev_corr"].append((v_corr, i_corr))

            self._update_single_curve("rev_raw")
            self._update_single_curve("rev_corr")

        if _HAS_PYQTGRAPH:
            # 即時更新時不重建 legend、不重套整套樣式，只視需要更新座標範圍
            self._apply_axis_range()

    def get_plot_item(self):
        """Returns the main PlotItem for exporting or direct manipulation."""
        return self.plot_widget.getPlotItem() if _HAS_PYQTGRAPH else None

    def get_current_plot_settings(self) -> Dict[str, Any]:
        return copy.deepcopy(self.plot_settings)

    def on_export_triggered(self):
        """Emits a signal to request exporting the plot."""
        self.export_requested.emit()