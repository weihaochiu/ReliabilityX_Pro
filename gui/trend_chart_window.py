"""
TrendChartWindow: controller for the long-term trend monitor.

本版本重點：
- 新增「使用者 / 專案 / 電池代號」三層範圍選擇
- grouped legend 改為左側樹狀群組顯示，不重複 user/project
- tooltip 只有在滑鼠明確靠近資料點時才顯示
- 環境曲線改為共 X 軸的下方子圖；未勾選時主圖吃滿高度
- 左側控制區改為整欄 QScrollArea，避免高度不足時硬壓縮內容
- v5 起與 Telegram 通知共用 core/trend_scope_utils.py 的 series/group 規則
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from bisect import bisect_right
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import config

from core.measurement_schema import IV_PARAMETER_KEYS, metric_key_from_label
from core.numeric_utils import parse_float_or_none
from core.trend_scope_utils import (
    annotate_scope_entry,
    make_display_label,
    make_group_label,
    make_series_key,
)
from .widgets.trend_device_list import TrendDeviceListWidget
from .widgets.trend_display_widget import TrendDisplayWidget
from .widgets.trend_plot_settings_dialog import TrendPlotSettingsDialog
from .widgets.trend_plot_widget import TrendPlotWidget
from .widgets.trend_selector_widget import TrendSelectorWidget

logger = logging.getLogger(__name__)


class TrendChartWindow(QWidget):
    """Trend monitor controller window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ReliabilityX Pro - 長期穩定性與壽命分析中心")
        self.setMinimumSize(1260, 780)

        trend_runtime = config.get_trend_runtime_settings()
        self.max_history_points = trend_runtime["max_in_memory_points"]
        self.render_throttle_ms = trend_runtime["render_throttle_ms"]
        self.all_data_history: List[Dict] = []
        self._series_history: Dict[str, List[Dict]] = {}
        self._dropped_history_count = 0
        self.active_scope_entries: Dict[str, Dict] = {}
        self._plot_settings_dialog = None

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(self.render_throttle_ms)
        self._update_timer.timeout.connect(self.update_chart)

        self._init_ui()
        self._connect_signals()

    def closeEvent(self, event: QCloseEvent):
        """Keep the window hidden instead of destroying it."""
        self.hide()
        event.ignore()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(370)
        controls_scroll.setMaximumWidth(430)
        controls_scroll.setStyleSheet("QScrollArea { border: none; }")

        controls_content = QWidget()
        controls_content.setMinimumWidth(352)

        controls_layout = QVBoxLayout(controls_content)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.setSpacing(12)

        self.selector_widget = TrendSelectorWidget()
        self.display_widget = TrendDisplayWidget()
        self.device_list_widget = TrendDeviceListWidget()

        self.btn_plot_settings = QPushButton("圖表設定...")
        self.btn_save_plot = QPushButton("儲存圖表...")
        for btn in (self.btn_plot_settings, self.btn_save_plot):
            btn.setMinimumHeight(42)

        controls_layout.addWidget(self.selector_widget)
        controls_layout.addWidget(self.display_widget)
        controls_layout.addWidget(self.device_list_widget)
        controls_layout.addWidget(self.btn_plot_settings)
        controls_layout.addWidget(self.btn_save_plot)
        controls_layout.addStretch(1)

        controls_scroll.setWidget(controls_content)
        splitter.addWidget(controls_scroll)

        self.plot_widget = TrendPlotWidget()
        splitter.addWidget(self.plot_widget)
        splitter.setSizes([390, 950])

    def _connect_signals(self):
        self.selector_widget.selectionChanged.connect(self.schedule_chart_update)
        self.display_widget.displayOptionsChanged.connect(self.schedule_chart_update)
        self.device_list_widget.visibilityChanged.connect(self.schedule_chart_update)
        self.btn_plot_settings.clicked.connect(self._on_plot_settings_clicked)
        self.btn_save_plot.clicked.connect(self._on_save_plot_clicked)

        vb = self.plot_widget.get_main_viewbox()
        if vb is not None:
            vb.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _summary_rows_to_records(self, summary_path: Path) -> List[Dict]:
        """Load one Summary_report.csv into trend records.

        This parser intentionally understands the canonical SummaryLogger layout.
        It also tolerates missing identity columns for legacy files by falling
        back to metadata comment rows.
        """
        records: List[Dict] = []
        try:
            rows = list(csv.reader(summary_path.open("r", encoding="utf-8-sig", newline="")))
        except Exception as exc:
            logger.warning("Unable to read summary history %s: %s", summary_path, exc)
            return records

        meta: Dict[str, str] = {}
        header_idx = None
        for idx, row in enumerate(rows):
            if not row:
                continue
            key = str(row[0] or "").strip().lstrip("#").strip().rstrip(":")
            if key and len(row) > 1 and str(row[0]).startswith("#"):
                meta[key] = str(row[1] or "").strip()
            if row and str(row[0]).strip() == "Start_Time":
                header_idx = idx
                break
        if header_idx is None:
            return records

        header = rows[header_idx]
        header_map = {str(name).strip(): idx for idx, name in enumerate(header) if str(name).strip()}
        user = meta.get("User", meta.get("User_Name", ""))
        project = meta.get("Project", meta.get("Project_Name", ""))
        device = meta.get("Device", meta.get("Device_Name", ""))
        ch_meta = meta.get("Channel", "")
        experiment_uid_meta = meta.get("Experiment_UID", "")
        run_session_meta = meta.get("Run_Session_ID", "")
        channel_label_meta = meta.get("Channel_Label", "")

        def cell(row, idx, default=""):
            try:
                return row[idx]
            except Exception:
                return default

        # Canonical metric offsets from SummaryLogger row layout.
        base = 4
        param_count = len(IV_PARAMETER_KEYS)
        blocks = {
            "F_Raw": base,
            "R_Raw": base + param_count,
            "F_Corr": base + (param_count * 2) + 2,
            "R_Corr": base + (param_count * 3) + 2,
        }
        hi_raw_idx = base + (param_count * 2)
        hi_corr_idx = base + (param_count * 4) + 2

        for row in rows[header_idx + 1:]:
            if not row or not str(cell(row, 0)).strip() or str(cell(row, 0)).startswith("#"):
                continue
            timestamp = self._coerce_timestamp(cell(row, 0))
            rec: Dict = {
                "timestamp": timestamp,
                "user": user,
                "project": project,
                "device_name": device,
                "ch_id": ch_meta,
                "channel_label": cell(row, header_map.get("Channel_Label", -1), channel_label_meta) or channel_label_meta,
                "experiment_uid": cell(row, header_map.get("Experiment_UID", -1), experiment_uid_meta) or experiment_uid_meta,
                "run_session_id": cell(row, header_map.get("Run_Session_ID", -1), run_session_meta) or run_session_meta,
                "history_source": "summary_csv",
                "summary_path": str(summary_path),
                "temp": parse_float_or_none(cell(row, 1)),
                "hum": parse_float_or_none(cell(row, 2)),
            }
            # Prefer explicit internal id when present, otherwise parse metadata channel.
            internal_ch = cell(row, header_map.get("Internal_CH_ID", -1), "")
            if internal_ch:
                rec["ch_id"] = internal_ch
            for suffix, start in blocks.items():
                for offset, param in enumerate(IV_PARAMETER_KEYS):
                    rec[f"{param}_{suffix}"] = parse_float_or_none(cell(row, start + offset))
            rec["HI_Raw"] = parse_float_or_none(cell(row, hi_raw_idx))
            rec["HI_Corr"] = parse_float_or_none(cell(row, hi_corr_idx))
            rec["series_key"] = self._make_series_key(rec)
            rec["display_label"] = self._make_display_label(rec)
            rec["group_label"] = self._make_group_label(rec)
            records.append(rec)
        return records

    def _load_historical_summary_for_scope(self, entries: List[Dict]) -> int:
        """Load historical Summary_report.csv records for active-scope series."""
        if not entries:
            return 0
        allowed = {entry.get("series_key") for entry in entries if entry.get("series_key")}
        if not allowed:
            return 0
        loaded = 0
        existing_keys = {
            (item.get("series_key"), item.get("timestamp"), item.get("run_session_id"), item.get("summary_path"))
            for item in self.all_data_history
        }
        try:
            data_root = config.get_safe_data_dir()
        except Exception:
            data_root = Path("data")
        try:
            summary_files = list(Path(data_root).rglob("Summary_report.csv"))
        except Exception as exc:
            logger.warning("Unable to scan summary history under %s: %s", data_root, exc)
            return 0
        for summary_path in summary_files:
            for rec in self._summary_rows_to_records(summary_path):
                if rec.get("series_key") not in allowed:
                    continue
                dedupe = (rec.get("series_key"), rec.get("timestamp"), rec.get("run_session_id"), rec.get("summary_path"))
                if dedupe in existing_keys:
                    continue
                existing_keys.add(dedupe)
                self.all_data_history.append(rec)
                self._insert_series_record(rec)
                loaded += 1
        if loaded:
            self._trim_history_if_needed()
            logger.info("Loaded %s historical trend points from Summary_report.csv for active scope", loaded)
        return loaded

    @pyqtSlot(list)
    def set_active_scope(self, active_channels_data: List[Dict]):
        """Update visible scope for the trend window."""
        entries = []
        for raw in active_channels_data or []:
            entry = annotate_scope_entry(raw)
            entries.append(entry)

        self.active_scope_entries = {entry["series_key"]: entry for entry in entries}
        self._load_historical_summary_for_scope(entries)
        self.device_list_widget.set_scope_entries(entries)
        self.schedule_chart_update()

    @pyqtSlot()
    def clear_active_scope(self):
        """Clear active scope after a scan finishes."""
        self.active_scope_entries.clear()
        self.device_list_widget.clear_scope()
        self.schedule_chart_update()

    @pyqtSlot()
    def _on_plot_settings_clicked(self):
        try:
            current_settings = self.plot_widget.get_current_plot_settings()
        except Exception as exc:
            logger.warning("無法從 plot_widget 取得目前設定，改用預設流程開啟 dialog: %s", exc)
            current_settings = None

        dlg = TrendPlotSettingsDialog(settings=current_settings, parent=self)
        dlg.settings_applied.connect(self.plot_widget.apply_plot_settings)
        self._plot_settings_dialog = dlg
        dlg.exec()
        self._plot_settings_dialog = None

    @pyqtSlot()
    def _on_save_plot_clicked(self):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"Trend_Chart_{timestamp}.png"
            file_filter = (
                "PNG 圖片 (*.png);;"
                "JPEG 圖片 (*.jpg);;"
                "TIFF 圖片 (*.tif);;"
                "BMP 圖片 (*.bmp);;"
                "所有檔案 (*)"
            )
            file_name, _ = QFileDialog.getSaveFileName(self, "儲存圖表", default_filename, file_filter)
            if not file_name:
                return
            if self.plot_widget.export_plot(file_name):
                QMessageBox.information(self, "成功", f"圖表已成功儲存至:\n{file_name}")
            else:
                QMessageBox.critical(self, "錯誤", "儲存圖表失敗。")
        except Exception as exc:
            logger.exception("儲存趨勢圖失敗")
            QMessageBox.critical(self, "錯誤", f"儲存圖表時發生錯誤:\n{exc}")

    def _insert_series_record(self, entry: Dict):
        series_key = entry.get("series_key")
        if not series_key:
            return
        bucket = self._series_history.setdefault(series_key, [])
        timestamp = entry.get("timestamp") or datetime.now()
        if not bucket or (bucket[-1].get("timestamp") or datetime.min) <= timestamp:
            bucket.append(entry)
            return
        timestamps = [item.get("timestamp") or datetime.min for item in bucket]
        bucket.insert(bisect_right(timestamps, timestamp), entry)

    def _rebuild_series_cache(self):
        self._series_history = {}
        for entry in self.all_data_history:
            self._insert_series_record(entry)

    def _trim_history_if_needed(self):
        if self.max_history_points <= 0:
            return
        excess = len(self.all_data_history) - self.max_history_points
        if excess <= 0:
            return
        del self.all_data_history[:excess]
        self._dropped_history_count += excess
        self._rebuild_series_cache()
        logger.info(
            "Trend cache bounded: dropped %s old GUI points; kept %s recent points",
            excess,
            len(self.all_data_history),
        )

    @pyqtSlot()
    def schedule_chart_update(self):
        """Debounce chart redraws so bursts of channel results do not freeze UI."""
        if not self._update_timer.isActive():
            self._update_timer.start()

    @pyqtSlot(dict)
    def add_new_data(self, res_dict):
        """Append one finished measurement point to bounded GUI history."""
        entry = dict(res_dict or {})
        entry["timestamp"] = self._coerce_timestamp(entry.get("timestamp"))
        entry.setdefault("temp", None)
        entry.setdefault("hum", None)
        entry["series_key"] = self._make_series_key(entry)
        entry["display_label"] = self._make_display_label(entry)
        entry["group_label"] = self._make_group_label(entry)
        self.all_data_history.append(entry)
        self._insert_series_record(entry)
        self._trim_history_if_needed()
        self.schedule_chart_update()

    @pyqtSlot()
    def update_chart(self):
        """Refresh visible trend curves and grouped legend."""
        selection = self.selector_widget.get_current_selection()
        options = self.display_widget.get_current_options()
        visible_series_keys = self.device_list_widget.get_visible_series_keys()
        visible_key_set = set(visible_series_keys)

        self.plot_widget.toggle_env_axis(options.get("show_env", False))

        metric_label = selection["metric"]
        y_label = f"Normalized {metric_label}" if options.get("normalize") else metric_label
        self.plot_widget.set_labels(
            title=metric_label,
            x_label=self._get_x_label(options.get("x_axis_mode", "運行時間 (Hours)"), visible_series_keys),
            y_label=y_label,
            y2_label="Environment (Temp / Hum)",
        )

        all_known_keys = set(self.active_scope_entries.keys()) | set(self._series_history.keys())
        legend_entries: List[Tuple[str, str]] = []
        grouped_legend: Dict[str, List[Dict]] = {}
        all_visible_records: List[Dict] = []

        x_axis_mode = options.get("x_axis_mode", "運行時間 (Hours)")
        time_divisor, _ = self._get_time_divisor(visible_series_keys, x_axis_mode)
        global_visible_start = self._get_global_visible_start(visible_series_keys)

        for series_key in sorted(all_known_keys):
            scope_entry = self.active_scope_entries.get(series_key)
            if series_key not in visible_key_set:
                label = self._make_display_label(scope_entry or {"series_key": series_key})
                self.plot_widget.update_device_plot(series_key, [], [], label, False, point_payloads=[])
                continue

            series_records = list(self._series_history.get(series_key, []))
            if not series_records:
                label = self._make_display_label(scope_entry or {"series_key": series_key})
                self.plot_widget.update_device_plot(series_key, [], [], label, False, point_payloads=[])
                continue

            y_vals = self._get_metric_values(series_records, selection)
            x_vals = self._get_x_axis_values(series_records, x_axis_mode, time_divisor, global_visible_start)

            if options.get("normalize") and y_vals:
                baseline = y_vals[0]
                if baseline not in (None, 0):
                    y_vals = [(float(y) / float(baseline)) * 100.0 if y is not None else None for y in y_vals]

            if options.get("smoothing"):
                y_vals = self._apply_moving_average(y_vals, window=3)

            plot_triplets = [
                (x, y, payload)
                for x, y, payload in zip(x_vals, y_vals, series_records)
                if y is not None
            ]
            if plot_triplets:
                x_plot, y_plot, payload_plot = zip(*plot_triplets)
                x_plot = list(x_plot)
                y_plot = list(y_plot)
                payload_plot = list(payload_plot)
            else:
                x_plot, y_plot, payload_plot = [], [], []

            label = self._make_display_label(scope_entry or series_records[0])
            self.plot_widget.update_device_plot(series_key, x_plot, y_plot, label, True, point_payloads=payload_plot)
            color = self.plot_widget.get_series_color(series_key)
            legend_entries.append((series_key, label))
            all_visible_records.extend(series_records)

            group_label = self._make_group_label(scope_entry or series_records[0])
            grouped_legend.setdefault(group_label, []).append({
                "display_label": label,
                "color": color,
            })

        self.device_list_widget.set_grouped_legend(grouped_legend)
        self.plot_widget.refresh_builtin_legend(legend_entries, include_env=bool(options.get("show_env")))

        if options.get("show_env"):
            self._update_environment_subplot(all_visible_records, x_axis_mode, time_divisor, global_visible_start)
        else:
            self.plot_widget.update_env_curves([], [], [], placeholder_text="")

    def _update_environment_subplot(
        self,
        visible_records: List[Dict],
        x_axis_mode: str,
        time_divisor: float,
        visible_start: Optional[datetime],
    ):
        if not visible_records:
            self.plot_widget.update_env_curves([], [], [], placeholder_text="環境資料尚未導入")
            return

        start_ts = min(d["timestamp"] for d in visible_records if d.get("timestamp"))
        end_ts = max(d["timestamp"] for d in visible_records if d.get("timestamp"))

        env_records = [
            d for d in self.all_data_history
            if d.get("timestamp") and start_ts <= d["timestamp"] <= end_ts
            and (d.get("temp") is not None or d.get("hum") is not None)
        ]
        env_records.sort(key=lambda item: item["timestamp"])

        if not env_records:
            self.plot_widget.update_env_curves([], [], [], placeholder_text="環境資料尚未導入")
            return

        x_env = self._get_x_axis_values(env_records, x_axis_mode, time_divisor, visible_start)
        y_temp = [d.get("temp") for d in env_records]
        y_hum = [d.get("hum") for d in env_records]
        self.plot_widget.update_env_curves(x_env, y_temp, y_hum, placeholder_text="")

    def _get_x_label(self, x_axis_mode: str, visible_series_keys: List[str]) -> str:
        if "Hours" not in x_axis_mode:
            return "Measurement Sequence"

        _, label = self._get_time_divisor(visible_series_keys, x_axis_mode)
        return label

    def _get_time_divisor(self, visible_series_keys: List[str], x_axis_mode: str):
        if "Hours" not in x_axis_mode:
            return 1.0, "Measurement Sequence"

        key_set = set(visible_series_keys)
        timestamps = [
            d.get("timestamp")
            for key in key_set
            for d in self._series_history.get(key, [])
            if d.get("timestamp")
        ]
        if len(timestamps) < 2:
            return 3600.0, "Time (Hours)"

        duration_seconds = (max(timestamps) - min(timestamps)).total_seconds()
        if duration_seconds < 120:
            return 1.0, "Time (Seconds)"
        if duration_seconds < 7200:
            return 60.0, "Time (Minutes)"
        return 3600.0, "Time (Hours)"

    def _get_global_visible_start(self, visible_series_keys: List[str]) -> Optional[datetime]:
        key_set = set(visible_series_keys)
        timestamps = [
            d.get("timestamp")
            for key in key_set
            for d in self._series_history.get(key, [])
            if d.get("timestamp")
        ]
        return min(timestamps) if timestamps else None

    def _get_metric_values(self, data_list: List[Dict], selection: Dict) -> List[Optional[float]]:
        metric_key = metric_key_from_label(selection.get("metric"))
        path = "Corr" if "Corr" in str(selection.get("path")) else "Raw"

        if metric_key == "HI":
            return [self._safe_float(d.get(f"HI_{path}")) for d in data_list]

        direction = "R" if "Reverse" in str(selection.get("direction")) else "F"
        lookup_key = f"{metric_key}_{direction}_{path}"
        return [self._safe_float(d.get(lookup_key)) for d in data_list]

    def _get_x_axis_values(
        self,
        data_list: List[Dict],
        x_mode: str,
        divisor: float = 1.0,
        global_start: Optional[datetime] = None,
    ) -> List[float]:
        if not data_list:
            return []
        if "Hours" in x_mode:
            start_time = global_start or min(
                (d.get("timestamp") for d in data_list if d.get("timestamp")),
                default=datetime.now(),
            )
            return [
                ((d.get("timestamp") or start_time) - start_time).total_seconds() / float(divisor or 1.0)
                for d in data_list
            ]
        return list(range(1, len(data_list) + 1))

    def _apply_moving_average(self, values: List[Optional[float]], window: int = 3) -> List[Optional[float]]:
        if window <= 1 or len(values) < 2:
            return values
        output: List[Optional[float]] = []
        for idx in range(len(values)):
            segment = [v for v in values[max(0, idx - window + 1): idx + 1] if v is not None]
            output.append(sum(segment) / len(segment) if segment else None)
        return output

    def _create_tooltip_text(self, data_point: Dict) -> str:
        selection = self.selector_widget.get_current_selection()
        direction = "R" if "Reverse" in str(selection.get("direction")) else "F"
        path = "Corr" if "Corr" in str(selection.get("path")) else "Raw"

        pce = self._format_number(data_point.get(f"PCE_{direction}_{path}"), 2, suffix=" %")
        voc = self._format_number(data_point.get(f"Voc_{direction}_{path}"), 3, suffix=" V")
        jsc = self._format_number(data_point.get(f"Jsc_{direction}_{path}"), 2, suffix=" mA/cm²")
        ff = self._format_number(data_point.get(f"FF_{direction}_{path}"), 1, suffix=" %")
        temp = self._format_number(data_point.get("temp"), 1, suffix=" °C")
        hum = self._format_number(data_point.get("hum"), 1, suffix=" %RH")

        return (
            f"User: {data_point.get('user', 'N/A')}\n"
            f"Project: {data_point.get('project', 'N/A')}\n"
            f"Device: {data_point.get('device_name', 'N/A')}\n"
            f"Channel: CH{int(data_point.get('ch_id', 0) or 0):02d}\n\n"
            f"PCE: {pce}\n"
            f"Voc: {voc}\n"
            f"Jsc: {jsc}\n"
            f"FF: {ff}\n\n"
            f"Temp: {temp}\n"
            f"Hum: {hum}"
        )

    def _on_mouse_moved(self, pos):
        visible_series_keys = self.device_list_widget.get_visible_series_keys()
        target = self.plot_widget.find_hover_target(pos, visible_series_keys, radius_px=12.0)
        if not target:
            self.plot_widget.hide_tooltip()
            return

        payload, x_val, y_val = target
        tooltip_text = self._create_tooltip_text(payload)
        self.plot_widget.update_tooltip(tooltip_text, x_val, y_val)

    def _make_series_key(self, data: Dict) -> str:
        return make_series_key(data)

    def _make_display_label(self, data: Dict) -> str:
        return make_display_label(data)

    def _make_group_label(self, data: Dict) -> str:
        return make_group_label(data, "user_project")

    def _coerce_timestamp(self, value) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(value)
            except Exception:
                pass
        return datetime.now()

    def _safe_float(self, value) -> Optional[float]:
        return parse_float_or_none(value, field_name="trend_value", context="TrendChartWindow")

    def _format_number(self, value, digits: int, suffix: str = "") -> str:
        number = parse_float_or_none(value)
        if number is None:
            return f"—{suffix}"
        return f"{number:.{digits}f}{suffix}"
