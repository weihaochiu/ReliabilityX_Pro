from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class ColorButton(QPushButton):
    def __init__(self, color: str = "#FFFFFF", parent: QWidget | None = None):
        super().__init__(parent)
        self._color = "#FFFFFF"
        self.setFixedWidth(120)
        self.clicked.connect(self._choose_color)
        self.set_color(color)

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        qcolor = QColor(color)
        if not qcolor.isValid():
            qcolor = QColor("#FFFFFF")

        self._color = qcolor.name().upper()
        self.setText(self._color)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {self._color};
                border: 1px solid #888;
                border-radius: 4px;
                padding: 4px 8px;
                color: {"#000000" if qcolor.lightness() > 140 else "#FFFFFF"};
                font-weight: 600;
            }}
            """
        )

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "選擇顏色")
        if color.isValid():
            self.set_color(color.name())


class IVPlotSettingsDialog(QDialog):
    """
    IV Curve 圖表設定對話框

    功能：
    - 開啟時自動從 config/iv_plot_settings.json 讀取
    - JSON 不存在時自動建立預設檔
    - 套用：發送 settings_applied 信號，不關閉
    - 儲存：寫入 JSON，不關閉
    - 確定：套用 + 儲存 + 關閉
    - 取消：直接關閉，不套用、不儲存
    - 還原預設：回復內建預設值

    Y 軸模式：
    - current -> mA
    - current_density -> mA/cm²
    - power -> mW

    第四象限規則：
    - 只對 current / current_density 生效
    - power 模式沿用量測符號，不強制限制在第四象限
    """

    settings_applied = pyqtSignal(dict)

    CURVE_KEYS = ["fwd_raw", "fwd_corr", "rev_raw", "rev_corr"]

    CURVE_TITLES = {
        "fwd_raw": "Forward Raw",
        "fwd_corr": "Forward Corr",
        "rev_raw": "Reversed Raw",
        "rev_corr": "Reversed Corr",
    }

    LINE_STYLE_OPTIONS = {
        "Solid": "solid",
        "Dash": "dash",
        "Dot": "dot",
        "DashDot": "dashdot",
        "DashDotDot": "dashdotdot",
    }

    LEGEND_POSITION_OPTIONS = {
        "右上": "top_right",
        "左上": "top_left",
        "右下": "bottom_right",
        "左下": "bottom_left",
    }

    Y_MODE_OPTIONS = {
        "Current (mA)": "current",
        "Current Density (mA/cm²)": "current_density",
        "Power (mW)": "power",
    }

    EXPORT_FORMAT_OPTIONS = {
        "PNG": "png",
        "JPG": "jpg",
        "TIFF": "tif",
        "BMP": "bmp",
    }

    FONT_SIZE_OPTIONS = [6, 8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 26, 28, 32, 36, 40, 48, 56, 64, 72]
    ALPHA_OPTIONS = list(range(0, 101, 10))
    LINE_WIDTH_OPTIONS = list(range(1, 13))
    EXPORT_DPI_OPTIONS = [72, 96, 120, 150, 200, 300, 600]

    def __init__(
        self,
        settings: Dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("IV Curve 圖表設定")
        self.resize(940, 780)

        self._defaults = self.default_settings()
        self._widgets: Dict[str, Any] = {}
        self._settings_file = self._resolve_settings_file()

        self._build_ui()

        if settings is not None:
            merged = copy.deepcopy(self._defaults)
            self._deep_update(merged, settings)
            self.set_settings(merged)
        else:
            loaded = self.load_settings_from_json()
            self.set_settings(loaded)

    @classmethod
    def default_settings(cls) -> Dict[str, Any]:
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
        current_file = Path(__file__).resolve()
        project_root = current_file.parents[2]
        config_dir = project_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "iv_plot_settings.json"

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        root_layout.addWidget(self.tab_widget)

        self.tab_widget.addTab(self._build_general_tab(), "一般")
        self.tab_widget.addTab(self._build_font_tab(), "字型")
        self.tab_widget.addTab(self._build_axis_tab(), "座標軸")
        self.tab_widget.addTab(self._build_grid_tab(), "格線")
        self.tab_widget.addTab(self._build_legend_tab(), "圖例")
        self.tab_widget.addTab(self._build_curves_tab(), "曲線")
        self.tab_widget.addTab(self._build_export_tab(), "匯出")

        bottom_layout = QHBoxLayout()

        self.lbl_json_path = QLabel(f"設定檔：{self._settings_file}")
        self.lbl_json_path.setStyleSheet("color: #555;")
        self.lbl_json_path.setWordWrap(True)
        bottom_layout.addWidget(self.lbl_json_path, stretch=1)

        self.btn_reset = QPushButton("還原預設")
        self.btn_reset.clicked.connect(self._on_reset_defaults_clicked)
        bottom_layout.addWidget(self.btn_reset)

        self.btn_save = QPushButton("儲存")
        self.btn_save.clicked.connect(self._on_save_clicked)
        bottom_layout.addWidget(self.btn_save)

        self.button_box = QDialogButtonBox()
        self.btn_apply = self.button_box.addButton("套用", QDialogButtonBox.ButtonRole.ApplyRole)
        self.btn_ok = self.button_box.addButton("確定", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_cancel = self.button_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)

        self.btn_apply.clicked.connect(self._on_apply_clicked)
        self.btn_ok.clicked.connect(self._on_ok_clicked)
        self.btn_cancel.clicked.connect(self.reject)

        bottom_layout.addWidget(self.button_box)

        root_layout.addLayout(bottom_layout)

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("一般設定")
        form = QFormLayout(group)

        self._widgets["general.title"] = QLineEdit()
        self._widgets["general.background_color"] = ColorButton("#FFFFFF")

        form.addRow("圖表標題", self._widgets["general.title"])
        form.addRow("背景顏色", self._widgets["general.background_color"])

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _build_font_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("字型大小")
        form = QFormLayout(group)

        self._widgets["font.title_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.axis_title_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.tick_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.legend_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")

        form.addRow("標題字型大小", self._widgets["font.title_size"])
        form.addRow("座標軸字型大小", self._widgets["font.axis_title_size"])
        form.addRow("刻度字型大小", self._widgets["font.tick_size"])
        form.addRow("圖例字型大小", self._widgets["font.legend_size"])

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _build_axis_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("座標軸設定")
        form = QFormLayout(group)

        self._widgets["axis.auto_range"] = QCheckBox("啟用自動縮放")
        self._widgets["axis.lock_fourth_quadrant"] = QCheckBox("鎖定只顯示第四象限")
        self._widgets["axis.y_mode"] = QComboBox()
        self._populate_combo(self._widgets["axis.y_mode"], self.Y_MODE_OPTIONS)

        self._widgets["axis.x_min"] = self._make_double_spinbox(-99999, 99999, 3)
        self._widgets["axis.x_max"] = self._make_double_spinbox(-99999, 99999, 3)
        self._widgets["axis.y_min"] = self._make_double_spinbox(-99999, 99999, 3)
        self._widgets["axis.y_max"] = self._make_double_spinbox(-99999, 99999, 3)

        form.addRow(self._widgets["axis.auto_range"])
        form.addRow(self._widgets["axis.lock_fourth_quadrant"])
        form.addRow("Y 軸顯示模式", self._widgets["axis.y_mode"])
        form.addRow("X 最小值", self._widgets["axis.x_min"])
        form.addRow("X 最大值", self._widgets["axis.x_max"])
        form.addRow("Y 最小值", self._widgets["axis.y_min"])
        form.addRow("Y 最大值", self._widgets["axis.y_max"])

        note = QLabel(
            "說明：\n"
            "1. 第四象限鎖定只對 Current / Current Density 生效。\n"
            "2. Power 模式沿用量測符號，不強制限制在第四象限。\n"
            "3. 啟用第四象限且關閉自動縮放時，X 最小值固定為 0，Y 最大值固定為 0。"
        )
        note.setWordWrap(True)
        note.setFrameShape(QFrame.Shape.StyledPanel)
        note.setStyleSheet("padding: 8px; background: #F6F6F6; color: #333;")

        layout.addWidget(group)
        layout.addWidget(note)
        layout.addStretch()

        self._widgets["axis.auto_range"].toggled.connect(self._update_axis_enable_state)
        self._widgets["axis.lock_fourth_quadrant"].toggled.connect(self._update_axis_enable_state)
        self._widgets["axis.y_mode"].currentIndexChanged.connect(self._update_axis_enable_state)

        return tab

    def _build_grid_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("格線設定")
        form = QFormLayout(group)

        self._widgets["grid.show_x"] = QCheckBox("顯示 X 格線")
        self._widgets["grid.show_y"] = QCheckBox("顯示 Y 格線")
        self._widgets["grid.color"] = ColorButton("#BFBFBF")
        self._widgets["grid.alpha"] = self._make_value_combo(self.ALPHA_OPTIONS, " %")
        self._widgets["grid.line_style"] = QComboBox()
        self._populate_combo(self._widgets["grid.line_style"], self.LINE_STYLE_OPTIONS)

        form.addRow(self._widgets["grid.show_x"])
        form.addRow(self._widgets["grid.show_y"])
        form.addRow("格線顏色", self._widgets["grid.color"])
        form.addRow("格線透明度", self._widgets["grid.alpha"])
        form.addRow("格線線型", self._widgets["grid.line_style"])

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _build_legend_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("圖例設定")
        form = QFormLayout(group)

        self._widgets["legend.show"] = QCheckBox("顯示圖例")
        self._widgets["legend.position"] = QComboBox()
        self._populate_combo(self._widgets["legend.position"], self.LEGEND_POSITION_OPTIONS)

        form.addRow(self._widgets["legend.show"])
        form.addRow("圖例位置", self._widgets["legend.position"])

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _build_curves_tab(self) -> QWidget:
        tab = QWidget()
        outer_layout = QVBoxLayout(tab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)

        for curve_key in self.CURVE_KEYS:
            title = self.CURVE_TITLES.get(curve_key, curve_key)
            group = QGroupBox(title)
            grid = QGridLayout(group)

            visible = QCheckBox("是否顯示")
            name_edit = QLineEdit()
            color_btn = ColorButton("#FFFFFF")
            width_combo = self._make_value_combo(self.LINE_WIDTH_OPTIONS, " px")
            line_style_combo = QComboBox()
            self._populate_combo(line_style_combo, self.LINE_STYLE_OPTIONS)

            self._widgets[f"curves.{curve_key}.visible"] = visible
            self._widgets[f"curves.{curve_key}.name"] = name_edit
            self._widgets[f"curves.{curve_key}.color"] = color_btn
            self._widgets[f"curves.{curve_key}.width"] = width_combo
            self._widgets[f"curves.{curve_key}.line_style"] = line_style_combo

            grid.addWidget(visible, 0, 0, 1, 2)
            grid.addWidget(QLabel("名稱"), 1, 0)
            grid.addWidget(name_edit, 1, 1)
            grid.addWidget(QLabel("顏色"), 2, 0)
            grid.addWidget(color_btn, 2, 1)
            grid.addWidget(QLabel("線寬"), 3, 0)
            grid.addWidget(width_combo, 3, 1)
            grid.addWidget(QLabel("線型"), 4, 0)
            grid.addWidget(line_style_combo, 4, 1)

            layout.addWidget(group)

        layout.addStretch()
        return tab

    def _build_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("匯出設定")
        form = QFormLayout(group)

        self._widgets["export.format"] = QComboBox()
        self._populate_combo(self._widgets["export.format"], self.EXPORT_FORMAT_OPTIONS)

        self._widgets["export.dpi"] = self._make_value_combo(self.EXPORT_DPI_OPTIONS)

        form.addRow("格式", self._widgets["export.format"])
        form.addRow("解析度 (DPI)", self._widgets["export.dpi"])

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _make_value_combo(self, values: list[int], suffix: str = "") -> QComboBox:
        combo = QComboBox()
        for value in values:
            text = f"{value}{suffix}" if suffix else str(value)
            combo.addItem(text, value)
        return combo

    def _make_double_spinbox(self, minimum: float, maximum: float, decimals: int = 3) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setSingleStep(0.1)
        widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        widget.setAccelerated(True)
        return widget

    def _populate_combo(self, combo: QComboBox, options: Dict[str, Any]) -> None:
        combo.clear()
        for text, value in options.items():
            combo.addItem(text, value)

    def _set_combo_value(self, combo: QComboBox, value: Any) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _get_combo_value(self, combo: QComboBox) -> Any:
        return combo.currentData()

    def _update_axis_enable_state(self) -> None:
        auto_range = self._widgets["axis.auto_range"].isChecked()
        lock_fourth = self._widgets["axis.lock_fourth_quadrant"].isChecked()
        y_mode = self._get_combo_value(self._widgets["axis.y_mode"])

        x_min_widget: QDoubleSpinBox = self._widgets["axis.x_min"]
        x_max_widget: QDoubleSpinBox = self._widgets["axis.x_max"]
        y_min_widget: QDoubleSpinBox = self._widgets["axis.y_min"]
        y_max_widget: QDoubleSpinBox = self._widgets["axis.y_max"]

        if auto_range:
            x_min_widget.setEnabled(False)
            x_max_widget.setEnabled(False)
            y_min_widget.setEnabled(False)
            y_max_widget.setEnabled(False)
            return

        x_min_widget.setEnabled(True)
        x_max_widget.setEnabled(True)
        y_min_widget.setEnabled(True)
        y_max_widget.setEnabled(True)

        fourth_quadrant_effective = lock_fourth and y_mode in ("current", "current_density")
        if fourth_quadrant_effective:
            x_min_widget.setValue(0.0)
            y_max_widget.setValue(0.0)
            x_min_widget.setEnabled(False)
            y_max_widget.setEnabled(False)

    def _on_reset_defaults_clicked(self) -> None:
        self.set_settings(copy.deepcopy(self._defaults))

    def _on_apply_clicked(self) -> None:
        if not self._validate_before_accept():
            return

        settings = self.get_settings()
        self.settings_applied.emit(settings)
        QMessageBox.information(self, "已套用", "目前設定已套用。")

    def _on_save_clicked(self) -> None:
        if not self._validate_before_accept():
            return

        settings = self.get_settings()
        ok, message = self.save_settings_to_json(settings)
        if ok:
            QMessageBox.information(self, "已儲存", f"設定已儲存到：\n{self._settings_file}")
        else:
            QMessageBox.critical(self, "儲存失敗", message)

    def _on_ok_clicked(self) -> None:
        if not self._validate_before_accept():
            return

        settings = self.get_settings()
        self.settings_applied.emit(settings)

        ok, message = self.save_settings_to_json(settings)
        if not ok:
            QMessageBox.critical(self, "儲存失敗", message)
            return

        super().accept()

    def _validate_before_accept(self) -> bool:
        axis_settings = self.get_settings()["axis"]

        x_min = axis_settings["x_min"]
        x_max = axis_settings["x_max"]
        y_min = axis_settings["y_min"]
        y_max = axis_settings["y_max"]

        if x_min >= x_max:
            QMessageBox.warning(self, "範圍錯誤", "X 最小值必須小於 X 最大值。")
            self.tab_widget.setCurrentIndex(2)
            return False

        if y_min >= y_max:
            QMessageBox.warning(self, "範圍錯誤", "Y 最小值必須小於 Y 最大值。")
            self.tab_widget.setCurrentIndex(2)
            return False

        if (
            not axis_settings["auto_range"]
            and axis_settings["lock_fourth_quadrant"]
            and axis_settings["y_mode"] in ("current", "current_density")
        ):
            if x_min != 0.0:
                QMessageBox.warning(self, "第四象限限制", "啟用第四象限時，X 最小值必須為 0。")
                self.tab_widget.setCurrentIndex(2)
                return False
            if y_max != 0.0:
                QMessageBox.warning(self, "第四象限限制", "啟用第四象限時，Y 最大值必須為 0。")
                self.tab_widget.setCurrentIndex(2)
                return False

        return True

    def set_settings(self, settings: Dict[str, Any]) -> None:
        merged = copy.deepcopy(self._defaults)
        self._deep_update(merged, settings or {})

        self._widgets["general.title"].setText(merged["general"]["title"])
        self._widgets["general.background_color"].set_color(merged["general"]["background_color"])

        self._set_combo_value(self._widgets["font.title_size"], merged["font"]["title_size"])
        self._set_combo_value(self._widgets["font.axis_title_size"], merged["font"]["axis_title_size"])
        self._set_combo_value(self._widgets["font.tick_size"], merged["font"]["tick_size"])
        self._set_combo_value(self._widgets["font.legend_size"], merged["font"]["legend_size"])

        self._widgets["axis.auto_range"].setChecked(merged["axis"]["auto_range"])
        self._widgets["axis.x_min"].setValue(float(merged["axis"]["x_min"]))
        self._widgets["axis.x_max"].setValue(float(merged["axis"]["x_max"]))
        self._widgets["axis.y_min"].setValue(float(merged["axis"]["y_min"]))
        self._widgets["axis.y_max"].setValue(float(merged["axis"]["y_max"]))
        self._widgets["axis.lock_fourth_quadrant"].setChecked(merged["axis"]["lock_fourth_quadrant"])
        self._set_combo_value(self._widgets["axis.y_mode"], merged["axis"]["y_mode"])

        self._widgets["grid.show_x"].setChecked(merged["grid"]["show_x"])
        self._widgets["grid.show_y"].setChecked(merged["grid"]["show_y"])
        self._widgets["grid.color"].set_color(merged["grid"]["color"])
        self._set_combo_value(self._widgets["grid.alpha"], int(merged["grid"]["alpha"]))
        self._set_combo_value(self._widgets["grid.line_style"], merged["grid"]["line_style"])

        self._widgets["legend.show"].setChecked(merged["legend"]["show"])
        self._set_combo_value(self._widgets["legend.position"], merged["legend"]["position"])

        for curve_key in self.CURVE_KEYS:
            curve_cfg = merged["curves"].get(curve_key, {})
            self._widgets[f"curves.{curve_key}.visible"].setChecked(curve_cfg.get("visible", True))
            self._widgets[f"curves.{curve_key}.name"].setText(
                curve_cfg.get("name", self.CURVE_TITLES[curve_key])
            )
            self._widgets[f"curves.{curve_key}.color"].set_color(curve_cfg.get("color", "#000000"))
            self._set_combo_value(
                self._widgets[f"curves.{curve_key}.width"],
                int(curve_cfg.get("width", 2)),
            )
            self._set_combo_value(
                self._widgets[f"curves.{curve_key}.line_style"],
                curve_cfg.get("line_style", "solid"),
            )

        self._set_combo_value(self._widgets["export.format"], merged["export"]["format"])
        self._set_combo_value(self._widgets["export.dpi"], int(merged["export"]["dpi"]))

        self._update_axis_enable_state()

    def get_settings(self) -> Dict[str, Any]:
        settings = {
            "general": {
                "title": self._widgets["general.title"].text().strip(),
                "background_color": self._widgets["general.background_color"].color(),
            },
            "font": {
                "title_size": int(self._get_combo_value(self._widgets["font.title_size"])),
                "axis_title_size": int(self._get_combo_value(self._widgets["font.axis_title_size"])),
                "tick_size": int(self._get_combo_value(self._widgets["font.tick_size"])),
                "legend_size": int(self._get_combo_value(self._widgets["font.legend_size"])),
            },
            "axis": {
                "auto_range": self._widgets["axis.auto_range"].isChecked(),
                "x_min": self._widgets["axis.x_min"].value(),
                "x_max": self._widgets["axis.x_max"].value(),
                "y_min": self._widgets["axis.y_min"].value(),
                "y_max": self._widgets["axis.y_max"].value(),
                "lock_fourth_quadrant": self._widgets["axis.lock_fourth_quadrant"].isChecked(),
                "y_mode": self._get_combo_value(self._widgets["axis.y_mode"]),
            },
            "grid": {
                "show_x": self._widgets["grid.show_x"].isChecked(),
                "show_y": self._widgets["grid.show_y"].isChecked(),
                "color": self._widgets["grid.color"].color(),
                "alpha": int(self._get_combo_value(self._widgets["grid.alpha"])),
                "line_style": self._get_combo_value(self._widgets["grid.line_style"]),
            },
            "legend": {
                "show": self._widgets["legend.show"].isChecked(),
                "position": self._get_combo_value(self._widgets["legend.position"]),
            },
            "curves": {},
            "export": {
                "format": self._get_combo_value(self._widgets["export.format"]),
                "dpi": int(self._get_combo_value(self._widgets["export.dpi"])),
            },
        }

        for curve_key in self.CURVE_KEYS:
            settings["curves"][curve_key] = {
                "visible": self._widgets[f"curves.{curve_key}.visible"].isChecked(),
                "name": self._widgets[f"curves.{curve_key}.name"].text().strip(),
                "color": self._widgets[f"curves.{curve_key}.color"].color(),
                "width": int(self._get_combo_value(self._widgets[f"curves.{curve_key}.width"])),
                "line_style": self._get_combo_value(self._widgets[f"curves.{curve_key}.line_style"]),
            }

        if (
            not settings["axis"]["auto_range"]
            and settings["axis"]["lock_fourth_quadrant"]
            and settings["axis"]["y_mode"] in ("current", "current_density")
        ):
            settings["axis"]["x_min"] = 0.0
            settings["axis"]["y_max"] = 0.0

        return settings

    def load_settings_from_json(self) -> Dict[str, Any]:
        if not self._settings_file.exists():
            self.save_settings_to_json(self._defaults)
            return copy.deepcopy(self._defaults)

        try:
            with self._settings_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            merged = copy.deepcopy(self._defaults)
            if isinstance(data, dict):
                self._deep_update(merged, data)
                return merged

            return copy.deepcopy(self._defaults)

        except Exception:
            return copy.deepcopy(self._defaults)

    def save_settings_to_json(self, settings: Dict[str, Any]) -> tuple[bool, str]:
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            with self._settings_file.open("w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            return True, ""
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _deep_update(base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        for key, value in incoming.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                IVPlotSettingsDialog._deep_update(base[key], value)
            else:
                base[key] = value


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    dlg = IVPlotSettingsDialog()

    def _on_applied(cfg: dict):
        print("Applied settings:")
        print(json.dumps(cfg, indent=2, ensure_ascii=False))

    dlg.settings_applied.connect(_on_applied)

    dlg.exec()
    sys.exit(0)