from __future__ import annotations

import logging
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PyQt6.QtWidgets import QApplication
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from core.numeric_utils import parse_float_or_none
from core.trend_scope_utils import annotate_scope_entry, make_display_label, make_series_key
from core.trend_spec import (
    get_metric_value,
    metric_filename_slug,
    normalize_direction_label,
    normalize_path_label,
    normalize_x_axis_label,
)
from .widgets.trend_plot_widget import TrendPlotWidget

logger = logging.getLogger(__name__)


class TrendSnapshotRenderer:
    """Render high-resolution trend PNGs and multi-page PDF reports for Telegram."""

    def __init__(self, log_mgr=None):
        self.log_mgr = log_mgr

    def render_snapshot(
        self,
        history: Iterable[Dict[str, Any]],
        output_path: str | Path,
        *,
        metric: str,
        direction: Optional[str],
        path: str,
        x_axis_mode: str,
        normalize: bool = False,
        show_env: bool = False,
        smoothing: bool = False,
        image_width: int = 2400,
        image_height: int = 1400,
    ) -> Tuple[bool, str]:
        """Render one high-resolution PNG using the same main-plot + env-subplot layout as Trend Chart."""
        history_list = [annotate_scope_entry(item) for item in (history or []) if isinstance(item, dict)]
        if not history_list:
            return False, "尚無趨勢歷史資料可供輸出。"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        widget = None
        try:
            metric = str(metric or "PCE (%)")
            direction = normalize_direction_label(direction)
            path = normalize_path_label(path)
            x_axis_mode = normalize_x_axis_label(x_axis_mode)

            widget = TrendPlotWidget()
            widget.resize(max(1200, int(image_width)), max(800, int(image_height)))

            x_label, time_divisor = self._resolve_x_axis(history_list, x_axis_mode)
            has_env = bool(show_env and self._has_environment_data(history_list))
            y_label = f"Normalized {metric}" if normalize else metric
            widget.set_labels(
                title=metric,
                x_label=x_label,
                y_label=y_label,
                y2_label="Temp (°C) / Hum (%RH)" if has_env else None,
            )
            widget.toggle_env_axis(has_env)

            legend_entries: List[Tuple[str, str]] = []
            series_keys = self._collect_series_keys(history_list)
            for series_key in series_keys:
                dev_data = sorted(
                    [d for d in history_list if self._series_key_from_result(d) == series_key],
                    key=lambda x: self._coerce_timestamp(x.get("timestamp")) or datetime.now(),
                )
                if not dev_data:
                    continue

                y_vals = self._get_metric_values(dev_data, metric, direction, path)
                x_vals = self._get_x_axis_values(history_list, dev_data, x_axis_mode, time_divisor)

                if smoothing:
                    y_vals = self._moving_average(y_vals, window=5)

                if normalize and y_vals:
                    baseline = next((y for y in y_vals if y not in (None, 0)), None)
                    if baseline not in (None, 0):
                        y_vals = [(float(y) / float(baseline)) * 100.0 if y is not None else None for y in y_vals]

                triplets = [(x, y, payload) for x, y, payload in zip(x_vals, y_vals, dev_data) if y is not None]
                if not triplets:
                    continue
                x_plot, y_plot, payload_plot = zip(*triplets)

                legend_name = self._display_label_from_result(dev_data[0])
                widget.update_device_plot(
                    series_key,
                    list(x_plot),
                    list(y_plot),
                    legend_name,
                    True,
                    point_payloads=list(payload_plot),
                )
                legend_entries.append((series_key, legend_name))

            if has_env:
                env_data = sorted(history_list, key=lambda x: self._coerce_timestamp(x.get("timestamp")) or datetime.now())
                x_env = self._get_x_axis_values(history_list, env_data, x_axis_mode, time_divisor)
                y_temp = [self._coerce_float(d.get("temp"), 0.0) for d in env_data]
                y_hum = [self._coerce_float(d.get("hum"), 0.0) for d in env_data]
                widget.update_env_curves(x_env, y_temp, y_hum, placeholder_text="")
            else:
                widget.update_env_curves([], [], [], placeholder_text="")

            try:
                widget.refresh_builtin_legend(legend_entries, include_env=has_env)
            except Exception:
                pass

            app = QApplication.instance()
            if app is not None:
                widget.show()
                app.processEvents()
            pixmap = widget.grab()
            if pixmap.isNull():
                return False, "無法擷取趨勢圖畫面。"
            if not pixmap.save(str(output_path), "PNG"):
                return False, "PNG 儲存失敗。"
            return True, str(output_path)

        except Exception as exc:
            logger.exception("背景趨勢圖輸出失敗")
            return False, str(exc)
        finally:
            if widget is not None:
                try:
                    widget.hide()
                except Exception:
                    pass
                try:
                    widget.deleteLater()
                except Exception:
                    pass

    def render_pdf_report(
        self,
        history: Iterable[Dict[str, Any]],
        output_path: str | Path,
        *,
        metrics: Iterable[str],
        direction: Optional[str],
        path: str,
        x_axis_mode: str,
        normalize: bool = False,
        smoothing: bool = False,
        group_label: Optional[str] = None,
        scope_entries: Optional[Iterable[Dict[str, Any]]] = None,
        status_text: str = "量測中（定時摘要）",
        generated_at: Optional[datetime] = None,
        image_width: int = 2400,
        image_height: int = 1400,
        include_env_when_available: bool = True,
    ) -> Tuple[bool, str]:
        """Render one multi-page PDF report; one metric per page, env subplot appended when available."""
        history_list = [annotate_scope_entry(item) for item in (history or []) if isinstance(item, dict)]
        metrics_list = [str(m) for m in (metrics or []) if str(m).strip()]
        scope_list = [annotate_scope_entry(item) for item in (scope_entries or []) if isinstance(item, dict)]
        if not history_list:
            return False, "尚無趨勢歷史資料可供輸出 PDF。"
        if not metrics_list:
            return False, "未選擇任何趨勢圖指標。"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ts = generated_at or datetime.now()
        show_env = bool(include_env_when_available and self._has_environment_data(history_list))

        temp_pngs: List[Path] = []
        try:
            for metric in metrics_list:
                png_path = output_path.parent / f"{output_path.stem}_{metric_filename_slug(metric)}.png"
                ok, msg = self.render_snapshot(
                    history_list,
                    png_path,
                    metric=metric,
                    direction=direction,
                    path=path,
                    x_axis_mode=x_axis_mode,
                    normalize=normalize,
                    show_env=show_env,
                    smoothing=smoothing,
                    image_width=image_width,
                    image_height=image_height,
                )
                if not ok:
                    return False, msg
                temp_pngs.append(png_path)

            page_size = landscape(A4)
            pdf = canvas.Canvas(str(output_path), pagesize=page_size)
            page_width, page_height = page_size
            margin = 30
            title_y = page_height - 28
            meta_top = page_height - 52
            footer_y = 18

            device_labels = [self._display_label_from_result(item) for item in scope_list] or [self._display_label_from_result(item) for item in history_list]
            device_text = ", ".join(device_labels) if device_labels else "-"
            device_lines = textwrap.wrap(device_text, width=92)
            group_text = group_label or "整體"
            direction_text = normalize_direction_label(direction)
            path_text = normalize_path_label(path)
            x_axis_text = normalize_x_axis_label(x_axis_mode)
            env_text = "有資料時每頁自動附加環境子圖" if show_env else "目前無環境資料，未顯示環境子圖"

            for idx, (metric, png_path) in enumerate(zip(metrics_list, temp_pngs), start=1):
                pdf.setTitle(f"ReliabilityX Trend Report - {group_text}")
                pdf.setFont("Helvetica-Bold", 16)
                pdf.drawString(margin, title_y, "ReliabilityX 趨勢 PDF 報告")
                pdf.setFont("Helvetica", 9)
                meta_lines = [
                    f"群組: {group_text}",
                    f"頁面指標: {metric}",
                    f"報告時間: {ts.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"狀態: {status_text}",
                    f"掃描方向 / 數據路徑: {direction_text} / {path_text}",
                    f"X 軸模式 / 標準化 / 平滑: {x_axis_text} / {'是' if normalize else '否'} / {'是' if smoothing else '否'}",
                    f"環境子圖: {env_text}",
                    f"電池數量: {len(device_labels)}",
                ]
                current_y = meta_top
                for line in meta_lines:
                    pdf.drawString(margin, current_y, line)
                    current_y -= 11
                for line in device_lines[:3]:
                    pdf.drawString(margin, current_y, f"電池: {line}" if line == device_lines[0] else f"      {line}")
                    current_y -= 11
                if len(device_lines) > 3:
                    pdf.drawString(margin, current_y, f"      ... 共 {len(device_labels)} 顆")
                    current_y -= 11

                image_reader = ImageReader(str(png_path))
                img_w, img_h = image_reader.getSize()
                available_w = page_width - (margin * 2)
                available_h = current_y - footer_y - 12
                scale = min(available_w / img_w, available_h / img_h)
                draw_w = img_w * scale
                draw_h = img_h * scale
                draw_x = margin + (available_w - draw_w) / 2
                draw_y = footer_y + 10
                pdf.drawImage(image_reader, draw_x, draw_y, draw_w, draw_h, preserveAspectRatio=True, mask='auto')

                pdf.setFont("Helvetica", 8)
                pdf.drawString(margin, footer_y, "資料來源：active scope；本頁採單一指標主圖 + 下方環境子圖格式。")
                pdf.drawRightString(page_width - margin, footer_y, f"Page {idx} / {len(metrics_list)}")
                pdf.showPage()

            pdf.save()
            return True, str(output_path)
        except Exception as exc:
            logger.exception("PDF 趨勢報告輸出失敗")
            return False, str(exc)
        finally:
            for path_obj in temp_pngs:
                try:
                    path_obj.unlink(missing_ok=True)
                except Exception:
                    pass

    def build_filename(self, metric: str, timestamp: Optional[datetime] = None) -> str:
        ts = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
        return f"trend_{metric_filename_slug(metric)}_{ts}.png"

    def build_pdf_filename(self, group_slug: str, timestamp: Optional[datetime] = None) -> str:
        ts = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
        return f"trend_report_{group_slug}_{ts}.pdf"

    def _has_environment_data(self, history_list: List[Dict[str, Any]]) -> bool:
        for item in history_list:
            if item.get("temp") not in (None, "") or item.get("hum") not in (None, ""):
                return True
        return False

    def _collect_series_keys(self, history_list: List[Dict[str, Any]]) -> List[str]:
        ordered: List[str] = []
        for item in history_list:
            series_key = self._series_key_from_result(item)
            if series_key not in ordered:
                ordered.append(series_key)
        return ordered

    def _series_key_from_result(self, result: Dict[str, Any]) -> str:
        return str(result.get("series_key") or make_series_key(result))

    def _display_label_from_result(self, result: Dict[str, Any]) -> str:
        return str(result.get("display_label") or make_display_label(result))

    def _coerce_timestamp(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            text = value.strip()
            for parser in (
                datetime.fromisoformat,
                lambda x: datetime.strptime(x, "%Y/%m/%d %H:%M:%S"),
                lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S"),
                lambda x: datetime.strptime(x, "%Y/%m/%d %H:%M"),
                lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M"),
            ):
                try:
                    return parser(text)
                except Exception:
                    continue
        return None

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _resolve_x_axis(self, history_list: List[Dict[str, Any]], x_axis_mode: str) -> Tuple[str, int]:
        x_label = "Measurement Sequence"
        time_divisor = 1
        if "Hours" in x_axis_mode:
            if len(history_list) > 1:
                sorted_history = sorted(history_list, key=lambda x: self._coerce_timestamp(x.get("timestamp")) or datetime.now())
                start_ts = self._coerce_timestamp(sorted_history[0].get("timestamp"))
                end_ts = self._coerce_timestamp(sorted_history[-1].get("timestamp"))
                if start_ts and end_ts:
                    duration_seconds = (end_ts - start_ts).total_seconds()
                    if duration_seconds < 120:
                        x_label = "Time (Seconds)"
                        time_divisor = 1
                    elif duration_seconds < 7200:
                        x_label = "Time (Minutes)"
                        time_divisor = 60
                    else:
                        x_label = "Time (Hours)"
                        time_divisor = 3600
                else:
                    x_label = "Time (Hours)"
                    time_divisor = 3600
            else:
                x_label = "Time (Hours)"
                time_divisor = 3600
        return x_label, time_divisor

    def _get_metric_values(self, dev_data: List[Dict[str, Any]], metric: str, direction: Optional[str], path: str) -> List[Optional[float]]:
        values: List[Optional[float]] = []
        for item in dev_data:
            values.append(parse_float_or_none(get_metric_value(item, metric, direction, path, None)))
        return values

    def _get_x_axis_values(self, all_history: List[Dict[str, Any]], data_list: List[Dict[str, Any]], x_mode: str, divisor: int = 1) -> List[float]:
        if not data_list:
            return []
        if "Hours" in x_mode:
            sorted_history = sorted(all_history, key=lambda x: self._coerce_timestamp(x.get("timestamp")) or datetime.now())
            start_time = self._coerce_timestamp(sorted_history[0].get("timestamp"))
            if start_time is None:
                return list(range(1, len(data_list) + 1))
            xs: List[float] = []
            for item in data_list:
                ts = self._coerce_timestamp(item.get("timestamp")) or start_time
                xs.append((ts - start_time).total_seconds() / max(1, divisor))
            return xs
        return [float(i) for i in range(1, len(data_list) + 1)]

    def _moving_average(self, values: List[float], window: int = 5) -> List[float]:
        if window <= 1 or len(values) <= 2:
            return list(values)
        smoothed: List[float] = []
        for idx in range(len(values)):
            start = max(0, idx - window + 1)
            chunk = values[start: idx + 1]
            if not chunk:
                smoothed.append(values[idx])
                continue
            smoothed.append(sum(chunk) / len(chunk))
        return smoothed
