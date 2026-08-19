"""
TrendPlotWidget: dual-subplot trend chart widget for ReliabilityX Pro.

功能：
- 上方主指標圖 / 下方環境子圖，共用 X 軸
- 未顯示環境時，主圖自動吃滿 100% 高度
- 支援 config/trend_plot_settings.json 樣式設定
- 支援精準 tooltip 與可見曲線管理
- 支援整個圖區匯出為圖片
"""

from __future__ import annotations

import copy
import html
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    import pyqtgraph as pg
    _HAS_PYQTGRAPH = True
except ImportError:
    pg = None
    _HAS_PYQTGRAPH = False

logger = logging.getLogger(__name__)


class TrendPlotWidget(QWidget):
    LINE_STYLE_MAP = {
        "solid": Qt.PenStyle.SolidLine,
        "dash": Qt.PenStyle.DashLine,
        "dot": Qt.PenStyle.DotLine,
        "dashdot": Qt.PenStyle.DashDotLine,
        "dashdotdot": Qt.PenStyle.DashDotDotLine,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot_settings: Dict[str, Any] = self.load_plot_settings()
        self._series_items: Dict[str, Dict[str, Any]] = {}
        self._series_order: List[str] = []
        self._last_labels = {
            "title": None,
            "x_label": None,
            "y_label": None,
            "y2_label": None,
        }
        self._legend = None
        self._tooltip = None
        self._env_temp_curve = None
        self._env_hum_curve = None
        self._show_env_subplot = False
        self._has_env_data = False

        self._init_ui()
        self.apply_plot_settings(self.plot_settings)

    @classmethod
    def default_plot_settings(cls) -> Dict[str, Any]:
        return {
            "general": {
                "title": "Trend Monitor",
                "background_color": "#FFFFFF",
                "show_tooltip": True,
                "tooltip_background_color": "#FFFFFF",
                "tooltip_text_color": "#000000",
            },
            "font": {
                "title_size": 14,
                "x_axis_title_size": 12,
                "left_y_axis_title_size": 12,
                "right_y_axis_title_size": 12,
                "tick_size": 10,
                "legend_size": 10,
                "tooltip_size": 10,
            },
            "axis": {
                "auto_range": True,
                "x_min": 0.0,
                "x_max": 100.0,
                "left_y_min": 0.0,
                "left_y_max": 100.0,
                "right_y_min": 0.0,
                "right_y_max": 100.0,
                "show_right_axis": True,
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
                "include_env_curves": True,
                "use_full_device_name": True,
            },
            "curves": {
                "device": {
                    "default_line_width": 2,
                    "default_line_style": "solid",
                    "show_symbols": True,
                    "symbol_size": 8,
                    "auto_color": True,
                    "allow_per_curve_override": False,
                },
                "env_temp": {
                    "visible": True,
                    "name": "Temp",
                    "color": "#FFA07A",
                    "width": 2,
                    "line_style": "dash",
                },
                "env_hum": {
                    "visible": True,
                    "name": "Hum",
                    "color": "#ADD8E6",
                    "width": 2,
                    "line_style": "dash",
                },
            },
            "export": {
                "format": "png",
                "dpi": 150,
                "use_current_view_range": True,
                "filename_pattern": "Trend_{timestamp}",
            },
        }

    def _resolve_settings_file(self) -> Path:
        try:
            current_file = Path(__file__).resolve()
            project_root = current_file.parents[2]
        except Exception:
            project_root = Path.cwd()
        config_dir = project_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "trend_plot_settings.json"

    def load_plot_settings(self) -> Dict[str, Any]:
        defaults = self.default_plot_settings()
        settings_file = self._resolve_settings_file()
        if not settings_file.exists():
            settings_file.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")
            return defaults

        try:
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Trend plot settings 讀取失敗，改用預設值: %s", exc)
            return defaults

        merged = copy.deepcopy(defaults)
        self._deep_update(merged, loaded if isinstance(loaded, dict) else {})
        return merged

    def get_current_plot_settings(self) -> Dict[str, Any]:
        return copy.deepcopy(self.plot_settings)

    def _deep_update(self, base: Dict[str, Any], override: Dict[str, Any]):
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if not _HAS_PYQTGRAPH:
            layout.addWidget(QLabel("pyqtgraph 未安裝，無法顯示趨勢圖。"))
            self.main_plot_widget = None
            self.env_plot_widget = None
            self.p1 = None
            self.env_plot_item = None
            return

        self.main_plot_widget = pg.PlotWidget()
        self.env_plot_widget = pg.PlotWidget()
        self.p1 = self.main_plot_widget.getPlotItem()
        self.env_plot_item = self.env_plot_widget.getPlotItem()

        layout.addWidget(self.main_plot_widget, stretch=2)
        layout.addWidget(self.env_plot_widget, stretch=1)

        self.env_plot_widget.setXLink(self.main_plot_widget)

        self._tooltip = pg.TextItem(anchor=(0, 1))
        self._tooltip.hide()
        self.p1.addItem(self._tooltip)

        self._env_temp_curve = self.env_plot_item.plot([], [], pen=pg.mkPen("#FFA07A", width=2))
        self._env_hum_curve = self.env_plot_item.plot([], [], pen=pg.mkPen("#ADD8E6", width=2))

        self.toggle_env_axis(False)

    def apply_plot_settings(self, settings: Dict[str, Any]):
        self.plot_settings = copy.deepcopy(self.default_plot_settings())
        self._deep_update(self.plot_settings, settings or {})

        if not _HAS_PYQTGRAPH or self.p1 is None:
            return

        bg = self.plot_settings["general"].get("background_color", "#FFFFFF")
        self.main_plot_widget.setBackground(bg)
        self.env_plot_widget.setBackground(bg)

        grid = self.plot_settings.get("grid", {})
        show_x = bool(grid.get("show_x", True))
        show_y = bool(grid.get("show_y", True))
        alpha = int(grid.get("alpha", 30))
        self.main_plot_widget.showGrid(x=show_x, y=show_y, alpha=alpha / 255.0)
        self.env_plot_widget.showGrid(x=show_x, y=show_y, alpha=alpha / 255.0)

        self._apply_axis_ranges()
        self._refresh_all_curve_styles()
        self._apply_labels()

    def _apply_axis_ranges(self):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return

        axis = self.plot_settings.get("axis", {})
        auto_range = bool(axis.get("auto_range", True))
        if auto_range:
            self.main_plot_widget.enableAutoRange()
            self.env_plot_widget.enableAutoRange()
            return

        try:
            self.main_plot_widget.setXRange(float(axis.get("x_min", 0.0)), float(axis.get("x_max", 100.0)), padding=0)
            self.main_plot_widget.setYRange(float(axis.get("left_y_min", 0.0)), float(axis.get("left_y_max", 100.0)), padding=0)
            self.env_plot_widget.setYRange(float(axis.get("right_y_min", 0.0)), float(axis.get("right_y_max", 100.0)), padding=0)
        except Exception:
            logger.exception("套用 Trend plot range 失敗")

    def _apply_labels(self):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return

        title = self._last_labels.get("title") or self.plot_settings["general"].get("title", "Trend Monitor")
        x_label = self._last_labels.get("x_label") or ""
        y_label = self._last_labels.get("y_label") or ""
        y2_label = self._last_labels.get("y2_label") or ""
        font = self.plot_settings.get("font", {})

        title_style = {"size": f"{font.get('title_size', 14)}pt"}
        axis_style = {"font-size": f"{font.get('x_axis_title_size', 12)}pt"}
        y_style = {"font-size": f"{font.get('left_y_axis_title_size', 12)}pt"}
        env_style = {"font-size": f"{font.get('right_y_axis_title_size', 12)}pt"}

        self.p1.setTitle(title, **title_style)
        self.p1.setLabel("left", y_label, **y_style)
        self.env_plot_item.setLabel("left", y2_label, **env_style)

        if self._show_env_subplot:
            self.p1.hideAxis("bottom")
            self.env_plot_item.showAxis("bottom")
            self.env_plot_item.setLabel("bottom", x_label, **axis_style)
        else:
            self.p1.showAxis("bottom")
            self.p1.setLabel("bottom", x_label, **axis_style)
            self.env_plot_item.hideAxis("bottom")

    def set_labels(self, title=None, x_label=None, y_label=None, y2_label=None):
        self._last_labels = {
            "title": title,
            "x_label": x_label,
            "y_label": y_label,
            "y2_label": y2_label,
        }
        self._apply_labels()

    def _get_series_pen(self, color: QColor, style_name: str = "solid", width: Optional[int] = None):
        width = int(width or self.plot_settings["curves"]["device"].get("default_line_width", 2))
        style = self.LINE_STYLE_MAP.get(style_name or "solid", Qt.PenStyle.SolidLine)
        return pg.mkPen(color, width=width, style=style)

    def _refresh_all_curve_styles(self):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return
        for key, item in self._series_items.items():
            color = item.get("color") or QColor("#1f77b4")
            pen = self._get_series_pen(color)
            item["curve"].setPen(pen)
            item["scatter"].setBrush(pg.mkBrush(color))
            item["scatter"].setPen(pg.mkPen(color))
            item["scatter"].setSize(self.plot_settings["curves"]["device"].get("symbol_size", 8))

        env_temp_cfg = self.plot_settings["curves"].get("env_temp", {})
        env_hum_cfg = self.plot_settings["curves"].get("env_hum", {})
        self._env_temp_curve.setPen(pg.mkPen(env_temp_cfg.get("color", "#FFA07A"), width=int(env_temp_cfg.get("width", 2)), style=self.LINE_STYLE_MAP.get(env_temp_cfg.get("line_style", "dash"), Qt.PenStyle.DashLine)))
        self._env_hum_curve.setPen(pg.mkPen(env_hum_cfg.get("color", "#ADD8E6"), width=int(env_hum_cfg.get("width", 2)), style=self.LINE_STYLE_MAP.get(env_hum_cfg.get("line_style", "dash"), Qt.PenStyle.DashLine)))

    def _ensure_series_item(self, series_key: str):
        if series_key in self._series_items:
            return self._series_items[series_key]

        color = pg.intColor(len(self._series_order), hues=16)
        curve = self.p1.plot([], [], pen=self._get_series_pen(color), name=str(series_key))
        scatter = pg.ScatterPlotItem([], [], size=self.plot_settings["curves"]["device"].get("symbol_size", 8), brush=pg.mkBrush(color), pen=pg.mkPen(color))
        self.p1.addItem(scatter)

        item = {
            "curve": curve,
            "scatter": scatter,
            "color": QColor(color.name()),
            "label": str(series_key),
            "x": [],
            "y": [],
            "payloads": [],
            "visible": False,
        }
        self._series_items[series_key] = item
        self._series_order.append(series_key)
        return item

    def update_device_plot(self, series_key: str, x_vals: Iterable[float], y_vals: Iterable[float], label: str, visible: bool, point_payloads: Optional[List[Dict[str, Any]]] = None):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return

        item = self._ensure_series_item(series_key)
        x_list = list(x_vals or [])
        y_list = list(y_vals or [])
        payloads = list(point_payloads or [])

        item["label"] = str(label)
        item["x"] = x_list
        item["y"] = y_list
        item["payloads"] = payloads
        item["visible"] = bool(visible and x_list and y_list)

        if item["visible"]:
            item["curve"].setData(x_list, y_list)
            item["curve"].show()

            show_symbols = bool(self.plot_settings["curves"]["device"].get("show_symbols", True))
            if show_symbols:
                item["scatter"].setData(x=x_list, y=y_list, data=payloads)
                item["scatter"].show()
            else:
                item["scatter"].setData([], [])
                item["scatter"].hide()
        else:
            item["curve"].setData([], [])
            item["curve"].hide()
            item["scatter"].setData([], [])
            item["scatter"].hide()

    def refresh_builtin_legend(self, entries: List[Tuple[str, str]], include_env: bool = False):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return

        legend_cfg = self.plot_settings.get("legend", {})
        if self._legend is not None:
            try:
                self._legend.scene().removeItem(self._legend)
            except Exception:
                pass
            self._legend = None

        if not bool(legend_cfg.get("show", True)):
            return

        self._legend = self.p1.addLegend(offset=(10, 10))
        for series_key, label in entries:
            item = self._series_items.get(series_key)
            if item and item.get("visible"):
                self._legend.addItem(item["curve"], label)

        if include_env and self._show_env_subplot and self._has_env_data and bool(legend_cfg.get("include_env_curves", True)):
            temp_name = self.plot_settings["curves"].get("env_temp", {}).get("name", "Temp")
            hum_name = self.plot_settings["curves"].get("env_hum", {}).get("name", "Hum")
            self._legend.addItem(self._env_temp_curve, temp_name)
            self._legend.addItem(self._env_hum_curve, hum_name)

    def update_env_curves(self, x_vals: Iterable[float], y_temp: Iterable[float], y_hum: Iterable[float], placeholder_text: str = ""):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return

        x_list = list(x_vals or [])
        temp_list = list(y_temp or [])
        hum_list = list(y_hum or [])
        self._has_env_data = bool(x_list and (temp_list or hum_list))

        if self._has_env_data:
            self._env_temp_curve.setData(x_list, temp_list)
            self._env_hum_curve.setData(x_list, hum_list)
            self.env_plot_item.setTitle("")
        else:
            self._env_temp_curve.setData([], [])
            self._env_hum_curve.setData([], [])
            self.env_plot_item.setTitle(placeholder_text or "環境資料尚未導入", color="#666666")

    def update_env_plot(self, payload: Optional[Dict[str, Any]] = None):
        """Compatibility wrapper used by TrendChartWindow."""
        payload = payload or {}
        temp = payload.get("temp") or {}
        hum = payload.get("hum") or {}
        x_vals = temp.get("x") or hum.get("x") or []
        y_temp = temp.get("y") or []
        y_hum = hum.get("y") or []
        placeholder = payload.get("placeholder") or "環境資料尚未導入"
        self.update_env_curves(x_vals, y_temp, y_hum, placeholder)

    def pick_nearest_point(self, scene_pos):
        """Compatibility wrapper used by TrendChartWindow."""
        result = self.find_hover_target(scene_pos, self._series_order)
        if not result:
            return None
        payload, x_val, y_val = result
        return {"payload": payload, "x": x_val, "y": y_val}

    def show_tooltip(self, scene_pos, text: str):
        """Compatibility wrapper used by TrendChartWindow."""
        point = self.pick_nearest_point(scene_pos)
        if point:
            self.update_tooltip(text, point.get("x", 0.0), point.get("y", 0.0))
            return

        vb = self.get_main_viewbox()
        if vb is None:
            self.hide_tooltip()
            return
        view_pos = vb.mapSceneToView(scene_pos)
        self.update_tooltip(text, float(view_pos.x()), float(view_pos.y()))

    def toggle_env_axis(self, show_env: bool):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return
        self._show_env_subplot = bool(show_env)
        self.env_plot_widget.setVisible(self._show_env_subplot)
        self._apply_labels()

    def get_plot_items(self):
        return {key: value["curve"] for key, value in self._series_items.items()}

    def get_main_viewbox(self):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return None
        return self.p1.vb

    def get_series_color(self, series_key: str) -> Optional[QColor]:
        item = self._series_items.get(series_key)
        return item.get("color") if item else None

    def find_hover_target(self, scene_pos, visible_series_keys: Iterable[str], radius_px: float = 12.0):
        if not _HAS_PYQTGRAPH or self.p1 is None:
            return None

        vb = self.get_main_viewbox()
        if vb is None or not vb.sceneBoundingRect().contains(scene_pos):
            return None

        best = None
        best_distance = float("inf")

        for series_key in visible_series_keys:
            item = self._series_items.get(series_key)
            if not item or not item.get("visible"):
                continue

            for x_val, y_val, payload in zip(item.get("x", []), item.get("y", []), item.get("payloads", [])):
                scene_point = vb.mapViewToScene(QPointF(float(x_val), float(y_val)))
                dist = ((scene_point.x() - scene_pos.x()) ** 2 + (scene_point.y() - scene_pos.y()) ** 2) ** 0.5
                if dist < best_distance:
                    best_distance = dist
                    best = (payload, float(x_val), float(y_val))

        if best is None or best_distance > float(radius_px):
            return None
        return best

    def update_tooltip(self, text: str, data_x: float, data_y: float):
        if not _HAS_PYQTGRAPH or self._tooltip is None:
            return
        if not self.plot_settings["general"].get("show_tooltip", True):
            self.hide_tooltip()
            return

        bg = self.plot_settings["general"].get("tooltip_background_color", "#FFFFFF")
        fg = self.plot_settings["general"].get("tooltip_text_color", "#000000")
        size = int(self.plot_settings["font"].get("tooltip_size", 10))
        escaped = html.escape(text).replace("\n", "<br>")
        self._tooltip.setHtml(
            f"<div style='background:{bg}; color:{fg}; padding:6px; border:1px solid #888; font-size:{size}pt;'>"
            f"{escaped}</div>"
        )
        self._tooltip.setPos(float(data_x), float(data_y))
        self._tooltip.show()

    def hide_tooltip(self):
        if self._tooltip is not None:
            self._tooltip.hide()

    def export_plot(self, file_path: str) -> bool:
        try:
            pixmap = self.grab()
            return pixmap.save(file_path)
        except Exception:
            logger.exception("匯出趨勢圖失敗")
            return False
