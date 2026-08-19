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


class TrendPlotSettingsDialog(QDialog):
    """
    Trend Monitor 圖表設定對話框

    功能：
    - 開啟時自動從 config/trend_plot_settings.json 讀取
    - JSON 不存在時自動建立預設檔
    - 套用：發送 settings_applied 信號，不關閉
    - 儲存：寫入 JSON，不關閉
    - 確定：套用 + 儲存 + 關閉
    - 取消：直接關閉，不套用、不儲存
    - 還原預設：回復內建預設值

    本修正版重點：
    - X / 左Y / 右Y 軸文字改為「預設文字」概念
    - 留空時表示由主視窗依顯示模式 / 指標自動連動
    - 避免 "X" / "Value" / "Environment" 這類固定字串誤導並覆蓋動態標題
    """

    settings_applied = pyqtSignal(dict)

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

    EXPORT_FORMAT_OPTIONS = {
        "PNG": "png",
        "JPG": "jpg",
        "TIFF": "tif",
        "BMP": "bmp",
    }

    FONT_SIZE_OPTIONS = [6, 8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 26, 28, 32, 36, 40, 48, 56, 64, 72]
    ALPHA_OPTIONS = list(range(0, 101, 10))
    LINE_WIDTH_OPTIONS = list(range(1, 13))
    SYMBOL_SIZE_OPTIONS = [0, 2, 4, 6, 8, 10, 12, 14, 16]
    EXPORT_DPI_OPTIONS = [72, 96, 120, 150, 200, 300, 600]

    def __init__(
        self,
        settings: Dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Trend Monitor 圖表設定")
        self.resize(980, 820)

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
                # 留空 = 由主視窗依顯示模式 / 指標動態決定
                "x_label": "",
                "left_y_label": "",
                "right_y_label": "",
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
        current_file = Path(__file__).resolve()
        project_root = current_file.parents[2]
        config_dir = project_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "trend_plot_settings.json"

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
        self._widgets["general.show_tooltip"] = QCheckBox("顯示 Tooltip")
        self._widgets["general.tooltip_background_color"] = ColorButton("#FFFFFF")
        self._widgets["general.tooltip_text_color"] = ColorButton("#000000")

        form.addRow("圖表標題", self._widgets["general.title"])
        form.addRow("背景顏色", self._widgets["general.background_color"])
        form.addRow(self._widgets["general.show_tooltip"])
        form.addRow("Tooltip 背景顏色", self._widgets["general.tooltip_background_color"])
        form.addRow("Tooltip 文字顏色", self._widgets["general.tooltip_text_color"])

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _build_font_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("字型大小")
        form = QFormLayout(group)

        self._widgets["font.title_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.x_axis_title_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.left_y_axis_title_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.right_y_axis_title_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.tick_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.legend_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")
        self._widgets["font.tooltip_size"] = self._make_value_combo(self.FONT_SIZE_OPTIONS, " pt")

        form.addRow("標題字型大小", self._widgets["font.title_size"])
        form.addRow("X 軸標題字型大小", self._widgets["font.x_axis_title_size"])
        form.addRow("左 Y 軸標題字型大小", self._widgets["font.left_y_axis_title_size"])
        form.addRow("右 Y 軸標題字型大小", self._widgets["font.right_y_axis_title_size"])
        form.addRow("刻度字型大小", self._widgets["font.tick_size"])
        form.addRow("圖例字型大小", self._widgets["font.legend_size"])
        form.addRow("Tooltip 字型大小", self._widgets["font.tooltip_size"])

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _build_axis_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("座標軸設定")
        form = QFormLayout(group)

        self._widgets["axis.x_label"] = QLineEdit()
        self._widgets["axis.left_y_label"] = QLineEdit()
        self._widgets["axis.right_y_label"] = QLineEdit()

        self._widgets["axis.x_label"].setPlaceholderText("留空＝依顯示模式自動顯示，例如 Time (Hours) / Measurement Sequence")
        self._widgets["axis.left_y_label"].setPlaceholderText("留空＝依維度與指標自動顯示，例如 PCE (%) / Voc (V)")
        self._widgets["axis.right_y_label"].setPlaceholderText("留空＝依環境軸狀態自動顯示，例如 Environment / Temp / Hum")

        self._widgets["axis.auto_range"] = QCheckBox("啟用自動縮放")
        self._widgets["axis.show_right_axis"] = QCheckBox("顯示右側環境軸")

        self._widgets["axis.x_min"] = self._make_double_spinbox(-999999, 999999, 3)
        self._widgets["axis.x_max"] = self._make_double_spinbox(-999999, 999999, 3)
        self._widgets["axis.left_y_min"] = self._make_double_spinbox(-999999, 999999, 3)
        self._widgets["axis.left_y_max"] = self._make_double_spinbox(-999999, 999999, 3)
        self._widgets["axis.right_y_min"] = self._make_double_spinbox(-999999, 999999, 3)
        self._widgets["axis.right_y_max"] = self._make_double_spinbox(-999999, 999999, 3)

        form.addRow("X 軸預設文字（留空＝自動連動）", self._widgets["axis.x_label"])
        form.addRow("左 Y 軸預設文字（留空＝自動連動）", self._widgets["axis.left_y_label"])
        form.addRow("右 Y 軸預設文字（留空＝自動連動）", self._widgets["axis.right_y_label"])
        form.addRow(self._widgets["axis.auto_range"])
        form.addRow(self._widgets["axis.show_right_axis"])
        form.addRow("X 最小值", self._widgets["axis.x_min"])
        form.addRow("X 最大值", self._widgets["axis.x_max"])
        form.addRow("左 Y 最小值", self._widgets["axis.left_y_min"])
        form.addRow("左 Y 最大值", self._widgets["axis.left_y_max"])
        form.addRow("右 Y 最小值", self._widgets["axis.right_y_min"])
        form.addRow("右 Y 最大值", self._widgets["axis.right_y_max"])

        note = QLabel(
            "說明：\n"
            "1. X 軸文字通常由顯示模式自動連動，例如「運行時間」或「量測序號」。\n"
            "2. 左 Y 軸文字通常由維度與指標自動連動，例如 PCE (%)、Voc (V)、Jsc (mA/cm²)。\n"
            "3. 這三個欄位屬於『預設文字』；留空時，主視窗的動態文字會優先顯示。\n"
            "4. 啟用自動縮放時，X / Y 範圍欄位會停用。\n"
            "5. 關閉右側環境軸時，右 Y 軸範圍只會保留設定值，不一定立即顯示。"
        )
        note.setWordWrap(True)
        note.setFrameShape(QFrame.Shape.StyledPanel)
        note.setStyleSheet("padding: 8px; background: #F6F6F6; color: #333;")

        layout.addWidget(group)
        layout.addWidget(note)
        layout.addStretch()

        self._widgets["axis.auto_range"].toggled.connect(self._update_axis_enable_state)
        self._widgets["axis.show_right_axis"].toggled.connect(self._update_axis_enable_state)

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
        self._widgets["legend.include_env_curves"] = QCheckBox("圖例包含環境曲線")
        self._widgets["legend.use_full_device_name"] = QCheckBox("使用完整設備名稱")

        form.addRow(self._widgets["legend.show"])
        form.addRow("圖例位置", self._widgets["legend.position"])
        form.addRow(self._widgets["legend.include_env_curves"])
        form.addRow(self._widgets["legend.use_full_device_name"])

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

        group_device = QGroupBox("設備趨勢曲線")
        form_device = QFormLayout(group_device)

        self._widgets["curves.device.default_line_width"] = self._make_value_combo(self.LINE_WIDTH_OPTIONS, " px")
        self._widgets["curves.device.default_line_style"] = QComboBox()
        self._populate_combo(self._widgets["curves.device.default_line_style"], self.LINE_STYLE_OPTIONS)
        self._widgets["curves.device.show_symbols"] = QCheckBox("顯示資料點")
        self._widgets["curves.device.symbol_size"] = self._make_value_combo(self.SYMBOL_SIZE_OPTIONS, " px")
        self._widgets["curves.device.auto_color"] = QCheckBox("啟用自動配色")
        self._widgets["curves.device.allow_per_curve_override"] = QCheckBox("允許單條曲線覆蓋預設樣式")

        form_device.addRow("預設線寬", self._widgets["curves.device.default_line_width"])
        form_device.addRow("預設線型", self._widgets["curves.device.default_line_style"])
        form_device.addRow(self._widgets["curves.device.show_symbols"])
        form_device.addRow("點大小", self._widgets["curves.device.symbol_size"])
        form_device.addRow(self._widgets["curves.device.auto_color"])
        form_device.addRow(self._widgets["curves.device.allow_per_curve_override"])

        layout.addWidget(group_device)

        group_temp = QGroupBox("環境曲線 - Temp")
        form_temp = QFormLayout(group_temp)

        self._widgets["curves.env_temp.visible"] = QCheckBox("顯示 Temp 曲線")
        self._widgets["curves.env_temp.name"] = QLineEdit()
        self._widgets["curves.env_temp.color"] = ColorButton("#FFA07A")
        self._widgets["curves.env_temp.width"] = self._make_value_combo(self.LINE_WIDTH_OPTIONS, " px")
        self._widgets["curves.env_temp.line_style"] = QComboBox()
        self._populate_combo(self._widgets["curves.env_temp.line_style"], self.LINE_STYLE_OPTIONS)

        form_temp.addRow(self._widgets["curves.env_temp.visible"])
        form_temp.addRow("名稱", self._widgets["curves.env_temp.name"])
        form_temp.addRow("顏色", self._widgets["curves.env_temp.color"])
        form_temp.addRow("線寬", self._widgets["curves.env_temp.width"])
        form_temp.addRow("線型", self._widgets["curves.env_temp.line_style"])

        layout.addWidget(group_temp)

        group_hum = QGroupBox("環境曲線 - Hum")
        form_hum = QFormLayout(group_hum)

        self._widgets["curves.env_hum.visible"] = QCheckBox("顯示 Hum 曲線")
        self._widgets["curves.env_hum.name"] = QLineEdit()
        self._widgets["curves.env_hum.color"] = ColorButton("#ADD8E6")
        self._widgets["curves.env_hum.width"] = self._make_value_combo(self.LINE_WIDTH_OPTIONS, " px")
        self._widgets["curves.env_hum.line_style"] = QComboBox()
        self._populate_combo(self._widgets["curves.env_hum.line_style"], self.LINE_STYLE_OPTIONS)

        form_hum.addRow(self._widgets["curves.env_hum.visible"])
        form_hum.addRow("名稱", self._widgets["curves.env_hum.name"])
        form_hum.addRow("顏色", self._widgets["curves.env_hum.color"])
        form_hum.addRow("線寬", self._widgets["curves.env_hum.width"])
        form_hum.addRow("線型", self._widgets["curves.env_hum.line_style"])

        layout.addWidget(group_hum)
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
        self._widgets["export.use_current_view_range"] = QCheckBox("使用目前畫面範圍")
        self._widgets["export.filename_pattern"] = QLineEdit()

        form.addRow("格式", self._widgets["export.format"])
        form.addRow("解析度 (DPI)", self._widgets["export.dpi"])
        form.addRow(self._widgets["export.use_current_view_range"])
        form.addRow("預設檔名樣式", self._widgets["export.filename_pattern"])

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

        axis_keys = [
            "axis.x_min",
            "axis.x_max",
            "axis.left_y_min",
            "axis.left_y_max",
            "axis.right_y_min",
            "axis.right_y_max",
        ]

        for key in axis_keys:
            self._widgets[key].setEnabled(not auto_range)

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
        axis = self.get_settings()["axis"]

        if axis["x_min"] >= axis["x_max"]:
            QMessageBox.warning(self, "範圍錯誤", "X 最小值必須小於 X 最大值。")
            self.tab_widget.setCurrentIndex(2)
            return False

        if axis["left_y_min"] >= axis["left_y_max"]:
            QMessageBox.warning(self, "範圍錯誤", "左 Y 最小值必須小於左 Y 最大值。")
            self.tab_widget.setCurrentIndex(2)
            return False

        if axis["right_y_min"] >= axis["right_y_max"]:
            QMessageBox.warning(self, "範圍錯誤", "右 Y 最小值必須小於右 Y 最大值。")
            self.tab_widget.setCurrentIndex(2)
            return False

        return True

    def set_settings(self, settings: Dict[str, Any]) -> None:
        merged = copy.deepcopy(self._defaults)
        self._deep_update(merged, settings or {})

        self._widgets["general.title"].setText(merged["general"]["title"])
        self._widgets["general.background_color"].set_color(merged["general"]["background_color"])
        self._widgets["general.show_tooltip"].setChecked(merged["general"]["show_tooltip"])
        self._widgets["general.tooltip_background_color"].set_color(
            merged["general"]["tooltip_background_color"]
        )
        self._widgets["general.tooltip_text_color"].set_color(
            merged["general"]["tooltip_text_color"]
        )

        self._set_combo_value(self._widgets["font.title_size"], merged["font"]["title_size"])
        self._set_combo_value(self._widgets["font.x_axis_title_size"], merged["font"]["x_axis_title_size"])
        self._set_combo_value(
            self._widgets["font.left_y_axis_title_size"], merged["font"]["left_y_axis_title_size"]
        )
        self._set_combo_value(
            self._widgets["font.right_y_axis_title_size"], merged["font"]["right_y_axis_title_size"]
        )
        self._set_combo_value(self._widgets["font.tick_size"], merged["font"]["tick_size"])
        self._set_combo_value(self._widgets["font.legend_size"], merged["font"]["legend_size"])
        self._set_combo_value(self._widgets["font.tooltip_size"], merged["font"]["tooltip_size"])

        self._widgets["axis.x_label"].setText(merged["axis"]["x_label"])
        self._widgets["axis.left_y_label"].setText(merged["axis"]["left_y_label"])
        self._widgets["axis.right_y_label"].setText(merged["axis"]["right_y_label"])
        self._widgets["axis.auto_range"].setChecked(merged["axis"]["auto_range"])
        self._widgets["axis.show_right_axis"].setChecked(merged["axis"]["show_right_axis"])
        self._widgets["axis.x_min"].setValue(float(merged["axis"]["x_min"]))
        self._widgets["axis.x_max"].setValue(float(merged["axis"]["x_max"]))
        self._widgets["axis.left_y_min"].setValue(float(merged["axis"]["left_y_min"]))
        self._widgets["axis.left_y_max"].setValue(float(merged["axis"]["left_y_max"]))
        self._widgets["axis.right_y_min"].setValue(float(merged["axis"]["right_y_min"]))
        self._widgets["axis.right_y_max"].setValue(float(merged["axis"]["right_y_max"]))

        self._widgets["grid.show_x"].setChecked(merged["grid"]["show_x"])
        self._widgets["grid.show_y"].setChecked(merged["grid"]["show_y"])
        self._widgets["grid.color"].set_color(merged["grid"]["color"])
        self._set_combo_value(self._widgets["grid.alpha"], int(merged["grid"]["alpha"]))
        self._set_combo_value(self._widgets["grid.line_style"], merged["grid"]["line_style"])

        self._widgets["legend.show"].setChecked(merged["legend"]["show"])
        self._set_combo_value(self._widgets["legend.position"], merged["legend"]["position"])
        self._widgets["legend.include_env_curves"].setChecked(merged["legend"]["include_env_curves"])
        self._widgets["legend.use_full_device_name"].setChecked(merged["legend"]["use_full_device_name"])

        self._set_combo_value(
            self._widgets["curves.device.default_line_width"],
            int(merged["curves"]["device"]["default_line_width"]),
        )
        self._set_combo_value(
            self._widgets["curves.device.default_line_style"],
            merged["curves"]["device"]["default_line_style"],
        )
        self._widgets["curves.device.show_symbols"].setChecked(merged["curves"]["device"]["show_symbols"])
        self._set_combo_value(
            self._widgets["curves.device.symbol_size"],
            int(merged["curves"]["device"]["symbol_size"]),
        )
        self._widgets["curves.device.auto_color"].setChecked(merged["curves"]["device"]["auto_color"])
        self._widgets["curves.device.allow_per_curve_override"].setChecked(
            merged["curves"]["device"]["allow_per_curve_override"]
        )

        self._widgets["curves.env_temp.visible"].setChecked(merged["curves"]["env_temp"]["visible"])
        self._widgets["curves.env_temp.name"].setText(merged["curves"]["env_temp"]["name"])
        self._widgets["curves.env_temp.color"].set_color(merged["curves"]["env_temp"]["color"])
        self._set_combo_value(
            self._widgets["curves.env_temp.width"],
            int(merged["curves"]["env_temp"]["width"]),
        )
        self._set_combo_value(
            self._widgets["curves.env_temp.line_style"],
            merged["curves"]["env_temp"]["line_style"],
        )

        self._widgets["curves.env_hum.visible"].setChecked(merged["curves"]["env_hum"]["visible"])
        self._widgets["curves.env_hum.name"].setText(merged["curves"]["env_hum"]["name"])
        self._widgets["curves.env_hum.color"].set_color(merged["curves"]["env_hum"]["color"])
        self._set_combo_value(
            self._widgets["curves.env_hum.width"],
            int(merged["curves"]["env_hum"]["width"]),
        )
        self._set_combo_value(
            self._widgets["curves.env_hum.line_style"],
            merged["curves"]["env_hum"]["line_style"],
        )

        self._set_combo_value(self._widgets["export.format"], merged["export"]["format"])
        self._set_combo_value(self._widgets["export.dpi"], int(merged["export"]["dpi"]))
        self._widgets["export.use_current_view_range"].setChecked(
            merged["export"]["use_current_view_range"]
        )
        self._widgets["export.filename_pattern"].setText(merged["export"]["filename_pattern"])

        self._update_axis_enable_state()

    def get_settings(self) -> Dict[str, Any]:
        settings = {
            "general": {
                "title": self._widgets["general.title"].text().strip(),
                "background_color": self._widgets["general.background_color"].color(),
                "show_tooltip": self._widgets["general.show_tooltip"].isChecked(),
                "tooltip_background_color": self._widgets["general.tooltip_background_color"].color(),
                "tooltip_text_color": self._widgets["general.tooltip_text_color"].color(),
            },
            "font": {
                "title_size": int(self._get_combo_value(self._widgets["font.title_size"])),
                "x_axis_title_size": int(self._get_combo_value(self._widgets["font.x_axis_title_size"])),
                "left_y_axis_title_size": int(
                    self._get_combo_value(self._widgets["font.left_y_axis_title_size"])
                ),
                "right_y_axis_title_size": int(
                    self._get_combo_value(self._widgets["font.right_y_axis_title_size"])
                ),
                "tick_size": int(self._get_combo_value(self._widgets["font.tick_size"])),
                "legend_size": int(self._get_combo_value(self._widgets["font.legend_size"])),
                "tooltip_size": int(self._get_combo_value(self._widgets["font.tooltip_size"])),
            },
            "axis": {
                "x_label": self._widgets["axis.x_label"].text().strip(),
                "left_y_label": self._widgets["axis.left_y_label"].text().strip(),
                "right_y_label": self._widgets["axis.right_y_label"].text().strip(),
                "auto_range": self._widgets["axis.auto_range"].isChecked(),
                "x_min": self._widgets["axis.x_min"].value(),
                "x_max": self._widgets["axis.x_max"].value(),
                "left_y_min": self._widgets["axis.left_y_min"].value(),
                "left_y_max": self._widgets["axis.left_y_max"].value(),
                "right_y_min": self._widgets["axis.right_y_min"].value(),
                "right_y_max": self._widgets["axis.right_y_max"].value(),
                "show_right_axis": self._widgets["axis.show_right_axis"].isChecked(),
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
                "include_env_curves": self._widgets["legend.include_env_curves"].isChecked(),
                "use_full_device_name": self._widgets["legend.use_full_device_name"].isChecked(),
            },
            "curves": {
                "device": {
                    "default_line_width": int(
                        self._get_combo_value(self._widgets["curves.device.default_line_width"])
                    ),
                    "default_line_style": self._get_combo_value(
                        self._widgets["curves.device.default_line_style"]
                    ),
                    "show_symbols": self._widgets["curves.device.show_symbols"].isChecked(),
                    "symbol_size": int(self._get_combo_value(self._widgets["curves.device.symbol_size"])),
                    "auto_color": self._widgets["curves.device.auto_color"].isChecked(),
                    "allow_per_curve_override": self._widgets[
                        "curves.device.allow_per_curve_override"
                    ].isChecked(),
                },
                "env_temp": {
                    "visible": self._widgets["curves.env_temp.visible"].isChecked(),
                    "name": self._widgets["curves.env_temp.name"].text().strip(),
                    "color": self._widgets["curves.env_temp.color"].color(),
                    "width": int(self._get_combo_value(self._widgets["curves.env_temp.width"])),
                    "line_style": self._get_combo_value(self._widgets["curves.env_temp.line_style"]),
                },
                "env_hum": {
                    "visible": self._widgets["curves.env_hum.visible"].isChecked(),
                    "name": self._widgets["curves.env_hum.name"].text().strip(),
                    "color": self._widgets["curves.env_hum.color"].color(),
                    "width": int(self._get_combo_value(self._widgets["curves.env_hum.width"])),
                    "line_style": self._get_combo_value(self._widgets["curves.env_hum.line_style"]),
                },
            },
            "export": {
                "format": self._get_combo_value(self._widgets["export.format"]),
                "dpi": int(self._get_combo_value(self._widgets["export.dpi"])),
                "use_current_view_range": self._widgets["export.use_current_view_range"].isChecked(),
                "filename_pattern": self._widgets["export.filename_pattern"].text().strip(),
            },
        }
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
                TrendPlotSettingsDialog._deep_update(base[key], value)
            else:
                base[key] = value


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    dlg = TrendPlotSettingsDialog()

    def _on_applied(cfg: dict):
        print(json.dumps(cfg, indent=2, ensure_ascii=False))

    dlg.settings_applied.connect(_on_applied)

    dlg.exec()
    sys.exit(0)