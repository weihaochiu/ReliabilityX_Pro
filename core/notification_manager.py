from __future__ import annotations

import datetime
import io
import json
import logging
import re
import mimetypes
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.trend_spec import (
    get_trend_metric_options,
    metric_filename_slug,
    normalize_direction_label,
    normalize_metric_labels,
    normalize_path_label,
    normalize_x_axis_label,
)

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import config
from core.trend_scope_utils import filter_records_to_active_scope, group_entries


def send_telegram_message(bot_token: str, chat_id: str, text: str, timeout: int = 10) -> tuple[bool, str]:
    bot_token = str(bot_token or "").strip()
    chat_id = str(chat_id or "").strip()
    text = str(text or "").strip()

    if not bot_token:
        return False, "Bot Token 不可為空。"
    if not chat_id:
        return False, "Chat ID 不可為空。"
    if not text:
        return False, "訊息內容不可為空。"

    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:4096],
    }).encode("utf-8")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    request = urllib.request.Request(url, data=payload, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        if data.get("ok"):
            return True, "訊息發送成功。"
        return False, data.get("description", "Telegram API 回傳失敗。")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            return False, data.get("description", f"HTTP {exc.code}")
        except Exception:
            return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


def _build_multipart(fields: Dict[str, str], files: List[Tuple[str, str, bytes, str]]) -> Tuple[bytes, str]:
    boundary = f"----ReliabilityX{uuid.uuid4().hex}"
    buffer = io.BytesIO()

    for name, value in fields.items():
        buffer.write(f"--{boundary}\r\n".encode("utf-8"))
        buffer.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        buffer.write(str(value).encode("utf-8"))
        buffer.write(b"\r\n")

    for field_name, filename, content, content_type in files:
        buffer.write(f"--{boundary}\r\n".encode("utf-8"))
        buffer.write(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        buffer.write(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        buffer.write(content)
        buffer.write(b"\r\n")

    buffer.write(f"--{boundary}--\r\n".encode("utf-8"))
    return buffer.getvalue(), boundary


def send_telegram_image(
    bot_token: str,
    chat_id: str,
    file_path: str | Path,
    *,
    caption: str = "",
    as_document: bool = False,
    timeout: int = 30,
) -> tuple[bool, str]:
    bot_token = str(bot_token or "").strip()
    chat_id = str(chat_id or "").strip()
    file_path = Path(file_path)

    if not bot_token:
        return False, "Bot Token 不可為空。"
    if not chat_id:
        return False, "Chat ID 不可為空。"
    if not file_path.exists():
        return False, f"圖檔不存在：{file_path}"

    method_name = "sendDocument" if as_document else "sendPhoto"
    file_field = "document" if as_document else "photo"
    url = f"https://api.telegram.org/bot{bot_token}/{method_name}"

    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    with file_path.open("rb") as fh:
        file_bytes = fh.read()

    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = str(caption)[:1024]
    payload, boundary = _build_multipart(
        fields,
        [(file_field, file_path.name, file_bytes, mime_type)],
    )

    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    request.add_header("Content-Length", str(len(payload)))

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        if data.get("ok"):
            return True, "圖片發送成功。"
        return False, data.get("description", "Telegram API 回傳失敗。")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            return False, data.get("description", f"HTTP {exc.code}")
        except Exception:
            return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


class _TelegramErrorLogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__(level=logging.ERROR)
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(record)
        except Exception:
            pass


class NotificationManager(QObject):
    """管理 Telegram 通知：開始量測、停止/完成、重大錯誤、定時摘要與趨勢圖。"""

    automatic_message_finished = pyqtSignal(bool, str)

    def __init__(self, engine, log_mgr=None, trend_renderer=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.log_mgr = log_mgr or getattr(engine, "log_mgr", None)
        self.trend_renderer = trend_renderer

        self.settings: Dict[str, Any] = {}
        self.telegram_cfg: Dict[str, Any] = {}
        self.general_cfg: Dict[str, Any] = {}
        self.latest_channel_results: Dict[int, Dict[str, Any]] = {}
        self.trend_history: List[Dict[str, Any]] = []
        self.pending_scan_channels: List[Dict[str, Any]] = []
        self._last_error_sent_at: Dict[str, float] = {}
        self._sent_schedule_keys: set[str] = set()
        self._schedule_date: Optional[str] = None
        self._log_handler: Optional[_TelegramErrorLogHandler] = None

        self._timer = QTimer(self)
        self._timer.setInterval(20 * 1000)
        self._timer.timeout.connect(self._on_schedule_timer)

        self.reload_settings()
        self._install_log_handler()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self._on_schedule_timer()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._remove_log_handler()

    def set_trend_renderer(self, trend_renderer) -> None:
        self.trend_renderer = trend_renderer

    def reload_settings(self) -> None:
        self.settings = config.load_notification_settings()
        self.telegram_cfg = config.resolve_telegram_secret_fields(self.settings.get("TELEGRAM", {}))
        self.general_cfg = dict(self.settings.get("GENERAL", {}))

    def set_pending_scan_request(self, active_channels_data: Iterable[Dict[str, Any]]) -> None:
        self.pending_scan_channels = [dict(item) for item in (active_channels_data or [])]

    @pyqtSlot()
    def on_scan_started(self) -> None:
        self.reload_settings()
        if not self._telegram_enabled() or not self.telegram_cfg.get("notify_on_measurement_start", True):
            return

        channels = self.pending_scan_channels or []
        lines = [f"時間: {self._now_text()}"]
        if channels:
            lines.append(f"啟用通道數: {len(channels)}")
            for item in channels[:32]:
                ch_id = item.get("ch_id", "?")
                user = item.get("user", "-")
                project = item.get("project", "-")
                device = item.get("device_name", "-")
                try:
                    ch_text = f"CH{int(ch_id):02d}"
                except Exception:
                    ch_text = f"CH{ch_id}"
                lines.append(f"{ch_text} | {user} / {project} / {device}")
        else:
            lines.append("啟用通道資訊: 未取得")

        self._queue_telegram_send("ReliabilityX 開始量測", "\n".join(lines), success_log="Telegram 開始量測通知發送成功。", fail_title="開始量測通知")

    @pyqtSlot(dict)
    def on_scan_finished(self, finish_info: Dict[str, Any]) -> None:
        self.reload_settings()
        self.pending_scan_channels = []

        if not self._telegram_enabled():
            return

        finish_info = dict(finish_info or {})
        finish_reason = str(finish_info.get("finish_reason", "")).strip()
        last_finished_channel_id = finish_info.get("last_finished_channel_id")
        finish_time = finish_info.get("finish_time") or self._now_text()

        notify_on_stop = bool(
            self.telegram_cfg.get(
                "notify_on_measurement_stop",
                self.telegram_cfg.get("notify_on_measurement_start", True),
            )
        )
        notify_on_complete = bool(
            self.telegram_cfg.get(
                "notify_on_measurement_complete",
                self.telegram_cfg.get("notify_on_measurement_start", True),
            )
        )

        if finish_reason == "stopped_after_current_channel" and notify_on_stop:
            lines = [
                f"時間: {self._fmt_time_value(finish_time)}",
                "模式: 完成目前元件正逆掃後停止",
                f"最後完成通道: {self._format_channel(last_finished_channel_id)}",
                "結果: 未進入下一顆元件",
            ]
            self._queue_telegram_send(
                "ReliabilityX 停止量測",
                "\n".join(lines),
                success_log="Telegram 停止量測通知發送成功。",
                fail_title="停止量測通知",
            )
            return

        if finish_reason == "completed" and notify_on_complete:
            lines = [
                f"時間: {self._fmt_time_value(finish_time)}",
                "結果: 本輪量測已正常完成",
                f"最後完成通道: {self._format_channel(last_finished_channel_id)}",
            ]
            self._queue_telegram_send(
                "ReliabilityX 量測完成",
                "\n".join(lines),
                success_log="Telegram 量測完成通知發送成功。",
                fail_title="量測完成通知",
            )

    @pyqtSlot(dict)
    def on_channel_measurement_finished(self, results: Dict[str, Any]) -> None:
        if not isinstance(results, dict):
            return
        result_copy = dict(results)
        if "timestamp" not in result_copy:
            result_copy["timestamp"] = self._now()
        try:
            ch_id = int(result_copy.get("ch_id"))
            self.latest_channel_results[ch_id] = result_copy
        except Exception:
            pass
        self.trend_history.append(result_copy)

    def _install_log_handler(self) -> None:
        logger = getattr(self.log_mgr, "logger", None)
        if logger is None or self._log_handler is not None:
            return
        self._log_handler = _TelegramErrorLogHandler(self._handle_log_record)
        logger.addHandler(self._log_handler)

    def _remove_log_handler(self) -> None:
        logger = getattr(self.log_mgr, "logger", None)
        if logger is None or self._log_handler is None:
            return
        try:
            logger.removeHandler(self._log_handler)
        except Exception:
            pass
        self._log_handler = None

    def _telegram_enabled(self) -> bool:
        return bool(
            self.telegram_cfg.get("enabled")
            and str(self.telegram_cfg.get("bot_token", "")).strip()
            and str(self.telegram_cfg.get("chat_id", "")).strip()
        )

    def _trend_image_enabled(self) -> bool:
        return bool(
            self.telegram_cfg.get("trend_images_enabled", False)
            and normalize_metric_labels(self.telegram_cfg.get("trend_metrics", []))
        )

    def _timezone_name(self) -> str:
        return str(self.general_cfg.get("timezone", "Asia/Taipei") or "Asia/Taipei")

    def _now(self) -> datetime.datetime:
        tz_name = self._timezone_name()
        if ZoneInfo is not None:
            try:
                return datetime.datetime.now(ZoneInfo(tz_name))
            except Exception:
                pass
        return datetime.datetime.now()

    def _now_text(self) -> str:
        return self._now().strftime("%Y-%m-%d %H:%M:%S")

    def _fmt_time_value(self, value: Any) -> str:
        if isinstance(value, datetime.datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value or self._now_text())

    def _format_channel(self, ch_id: Any) -> str:
        try:
            return f"CH{int(ch_id):02d}"
        except Exception:
            return "-"

    def _handle_log_record(self, record: logging.LogRecord) -> None:
        self.reload_settings()
        if not self._telegram_enabled() or not self.telegram_cfg.get("notify_on_critical_error", True):
            return
        if getattr(record, "levelno", logging.INFO) < logging.ERROR:
            return

        message = record.getMessage()
        if not message or "[NOTIFY]" in message:
            return

        cooldown_seconds = int(self.telegram_cfg.get("cooldown_seconds", 300) or 300)
        dedup_key = f"{record.levelname}:{message.strip()[:200]}"
        now_ts = time.time()
        last_sent = self._last_error_sent_at.get(dedup_key, 0.0)
        if cooldown_seconds > 0 and (now_ts - last_sent) < cooldown_seconds:
            return

        self._last_error_sent_at[dedup_key] = now_ts
        body = f"時間: {self._now_text()}\n等級: {record.levelname}\n{message.strip()}"
        self._queue_telegram_send("ReliabilityX 重大錯誤", body)

    def _on_schedule_timer(self) -> None:
        self.reload_settings()
        if not self._telegram_enabled() or not self.telegram_cfg.get("notify_on_daily_summary", True):
            return

        now = self._now()
        date_key = now.strftime("%Y%m%d")
        if self._schedule_date != date_key:
            self._schedule_date = date_key
            self._sent_schedule_keys = set()

        if now.minute != 0:
            return

        hours = self._normalized_report_hours()
        if now.hour not in hours:
            return

        dispatch_key = f"{date_key}-{now.hour:02d}"
        if dispatch_key in self._sent_schedule_keys:
            return

        self._sent_schedule_keys.add(dispatch_key)

        if self._trend_image_enabled() and self.trend_renderer is not None:
            ok = self._dispatch_trend_reports()
            if ok:
                return

        self._queue_telegram_send("ReliabilityX IV 定時摘要", self._build_daily_summary_text())

    def _normalized_report_hours(self) -> List[int]:
        hours: List[int] = []
        for value in self.telegram_cfg.get("daily_report_hours", []):
            try:
                hour = int(value)
            except Exception:
                continue
            if 0 <= hour <= 23 and hour not in hours:
                hours.append(hour)
        hours.sort()
        return hours

    def _dispatch_trend_reports(self) -> bool:
        """Dispatch trend reports, preferring active-scope PDF when enabled."""
        if bool(self.telegram_cfg.get("trend_pdf_enabled", False)):
            ok = self._dispatch_trend_pdf_reports()
            if ok:
                return True
        return self._dispatch_trend_images()

    def _dispatch_trend_pdf_reports(self) -> bool:
        metrics = normalize_metric_labels(self.telegram_cfg.get("trend_metrics", []))
        if not metrics or not self.trend_history or self.trend_renderer is None:
            return False
        group_mode = self.telegram_cfg.get("trend_group_mode", "overall")
        direction = normalize_direction_label(self.telegram_cfg.get("trend_direction"))
        path = normalize_path_label(self.telegram_cfg.get("trend_path"))
        x_axis_mode = normalize_x_axis_label(self.telegram_cfg.get("trend_x_axis_mode"))
        normalize = bool(self.telegram_cfg.get("trend_normalize", False))
        smoothing = bool(self.telegram_cfg.get("trend_smoothing", False))
        show_env = bool(self.telegram_cfg.get("trend_pdf_include_env_when_available", True))
        image_width = int(self.telegram_cfg.get("trend_image_width", 2400) or 2400)
        image_height = int(self.telegram_cfg.get("trend_image_height", 1400) or 1400)

        scope_entries = list(self.pending_scan_channels or [])
        history = self.trend_history
        if scope_entries:
            history = filter_records_to_active_scope(history, scope_entries)
        if not history:
            if self.log_mgr:
                self.log_mgr.log_warning("[NOTIFY] active-scope PDF report skipped because no trend history matched current active channels.")
            return False

        groups = group_entries(scope_entries or history, group_mode)
        if not groups:
            groups = [{"group_key": "overall", "group_label": "整體", "entries": scope_entries or history}]

        success_count = 0
        temp_dir = Path(tempfile.gettempdir()) / "reliabilityx_notification"
        temp_dir.mkdir(parents=True, exist_ok=True)
        for group in groups:
            entries = group.get("entries", [])
            group_history = filter_records_to_active_scope(history, entries) if entries else history
            if not group_history:
                continue
            group_label = group.get("group_label") or "整體"
            safe_slug = re.sub(r"[^\w.-]+", "_", str(group.get("group_key") or group_label))[:60] or "overall"
            output_path = temp_dir / self.trend_renderer.build_pdf_filename(safe_slug)
            ok, msg = self.trend_renderer.render_pdf_report(
                group_history,
                output_path,
                metrics=metrics,
                direction=direction,
                path=path,
                x_axis_mode=x_axis_mode,
                normalize=normalize,
                smoothing=smoothing,
                group_label=group_label,
                scope_entries=entries,
                status_text="量測中（定時摘要）",
                image_width=image_width,
                image_height=image_height,
                include_env_when_available=show_env,
            )
            if not ok:
                if self.log_mgr:
                    self.log_mgr.log_warning(f"[NOTIFY] PDF 趨勢報告產生失敗 ({group_label}): {msg}")
                continue
            caption = f"ReliabilityX 趨勢 PDF 報告\n群組: {group_label}\n時間: {self._now_text()}"
            self._queue_telegram_image_send(output_path, caption=caption, as_document=True, delete_after_send=True)
            success_count += 1
        return success_count > 0

    def _dispatch_trend_images(self) -> bool:
        metrics = normalize_metric_labels(self.telegram_cfg.get("trend_metrics", []))
        if not metrics:
            return False
        if not self.trend_history:
            if self.log_mgr:
                self.log_mgr.log_warning("[NOTIFY] 尚無趨勢歷史資料，改發送文字摘要。")
            return False

        direction = normalize_direction_label(self.telegram_cfg.get("trend_direction"))
        path = normalize_path_label(self.telegram_cfg.get("trend_path"))
        x_axis_mode = normalize_x_axis_label(self.telegram_cfg.get("trend_x_axis_mode"))
        normalize = bool(self.telegram_cfg.get("trend_normalize", False))
        show_env = bool(self.telegram_cfg.get("trend_show_env", False))
        smoothing = bool(self.telegram_cfg.get("trend_smoothing", False))
        as_document = bool(self.telegram_cfg.get("trend_send_as_document", False))
        image_width = int(self.telegram_cfg.get("trend_image_width", 1600) or 1600)
        image_height = int(self.telegram_cfg.get("trend_image_height", 900) or 900)

        success_count = 0
        for metric in metrics:
            temp_dir = Path(tempfile.gettempdir()) / "reliabilityx_notification"
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_path = temp_dir / self._build_trend_filename(metric)
            ok, msg = self.trend_renderer.render_snapshot(
                self.trend_history,
                output_path,
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
                if self.log_mgr:
                    self.log_mgr.log_warning(f"[NOTIFY] 趨勢圖產生失敗 ({metric}): {msg}")
                continue

            caption = self._build_trend_caption(metric, direction, path, x_axis_mode, normalize, show_env)
            self._queue_telegram_image_send(output_path, caption=caption, as_document=as_document, delete_after_send=True)
            success_count += 1

        return success_count > 0

    def _build_trend_filename(self, metric: str) -> str:
        ts = self._now().strftime("%Y%m%d_%H%M%S")
        return f"trend_{metric_filename_slug(metric)}_{ts}.png"

    def _build_trend_caption(
        self,
        metric: str,
        direction: str,
        path: str,
        x_axis_mode: str,
        normalize: bool,
        show_env: bool,
    ) -> str:
        parts = [
            "ReliabilityX 趨勢圖",
            f"指標: {metric}",
            f"方向: {direction if metric != 'Hysteresis_Index' else '不適用'}",
            f"路徑: {path}",
            f"X軸: {x_axis_mode}",
            f"標準化: {'是' if normalize else '否'}",
            f"環境數據: {'是' if show_env else '否'}",
            f"時間: {self._now_text()}",
        ]
        return "\n".join(parts)

    def _build_daily_summary_text(self) -> str:
        lines = [f"時間: {self._now_text()}"]
        if not self.latest_channel_results:
            lines.append("目前尚無已完成量測的 IV 結果。")
            return "\n".join(lines)

        for ch_id in sorted(self.latest_channel_results.keys()):
            result = self.latest_channel_results[ch_id]
            device = result.get("device_name", "-")
            voc = self._pick_metric(result, "Voc")
            jsc = self._pick_metric(result, "Jsc")
            ff = self._pick_metric(result, "FF")
            pce = self._pick_metric(result, "PCE")
            lines.append(
                f"CH{ch_id:02d} | {device} | "
                f"Voc={self._fmt_number(voc)} | "
                f"Jsc={self._fmt_number(jsc)} | "
                f"FF={self._fmt_number(ff)} | "
                f"PCE={self._fmt_number(pce)}"
            )
        return "\n".join(lines)

    def _pick_metric(self, result: Dict[str, Any], metric_name: str):
        alias_map = {
            "Voc": ["Voc_f", "Voc_F_Corr", "Voc_F_Raw", "Voc"],
            "Jsc": ["Jsc_f", "Jsc_F_Corr", "Jsc_F_Raw", "Jsc"],
            "FF": ["FF_f", "FF_F_Corr", "FF_F_Raw", "FF"],
            "PCE": ["Eff_f", "PCE_f", "PCE_F_Corr", "PCE_F_Raw", "PCE"],
        }
        aliases = alias_map.get(metric_name, [metric_name])
        for alias in aliases:
            value = result.get(alias)
            if value not in (None, ""):
                return value

        nested_candidates = ["Forward_Corr", "F_Corr", "Forward_Raw", "F_Raw"]
        for container_name in nested_candidates:
            sub = result.get(container_name)
            if isinstance(sub, dict):
                for alias in [metric_name, metric_name.lower(), metric_name.upper()]:
                    value = sub.get(alias)
                    if value not in (None, ""):
                        return value
        return ""

    def _fmt_number(self, value: Any) -> str:
        if value in (None, ""):
            return "-"
        try:
            number = float(value)
        except Exception:
            return str(value)
        text = f"{number:.4f}".rstrip("0").rstrip(".")
        return text or "0"

    def _queue_telegram_send(
        self,
        title: str,
        body: str,
        *,
        success_log: str | None = None,
        fail_title: str | None = None,
    ) -> None:
        if not self._telegram_enabled():
            return

        bot_token = str(self.telegram_cfg.get("bot_token", "") or "").strip()
        chat_id = str(self.telegram_cfg.get("chat_id", "") or "").strip()
        max_len = max(100, int(self.telegram_cfg.get("max_message_length", 3500) or 3500))
        text = f"{title}\n{body}".strip()
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."

        thread = threading.Thread(
            target=self._send_text_worker,
            args=(bot_token, chat_id, text, success_log, fail_title or title),
            daemon=True,
        )
        thread.start()

    def _queue_telegram_image_send(
        self,
        file_path: str | Path,
        *,
        caption: str,
        as_document: bool,
        delete_after_send: bool,
    ) -> None:
        if not self._telegram_enabled():
            return
        bot_token = str(self.telegram_cfg.get("bot_token", "") or "").strip()
        chat_id = str(self.telegram_cfg.get("chat_id", "") or "").strip()
        thread = threading.Thread(
            target=self._send_image_worker,
            args=(bot_token, chat_id, str(file_path), caption, as_document, delete_after_send),
            daemon=True,
        )
        thread.start()

    def _send_text_worker(
        self,
        bot_token: str,
        chat_id: str,
        text: str,
        success_log: str | None,
        fail_title: str,
    ) -> None:
        ok, message = send_telegram_message(bot_token, chat_id, text)
        self.automatic_message_finished.emit(ok, message)
        if self.log_mgr:
            if ok:
                self.log_mgr.log_info(f"[NOTIFY] {success_log or 'Telegram 訊息發送成功。'}")
            else:
                self.log_mgr.log_warning(f"[NOTIFY] Telegram {fail_title}發送失敗: {message}")

    def _send_image_worker(
        self,
        bot_token: str,
        chat_id: str,
        file_path: str,
        caption: str,
        as_document: bool,
        delete_after_send: bool,
    ) -> None:
        try:
            ok, message = send_telegram_image(
                bot_token,
                chat_id,
                file_path,
                caption=caption,
                as_document=as_document,
            )
            self.automatic_message_finished.emit(ok, message)
            if self.log_mgr:
                if ok:
                    self.log_mgr.log_info(f"[NOTIFY] Telegram 趨勢圖發送成功: {Path(file_path).name}")
                else:
                    self.log_mgr.log_warning(f"[NOTIFY] Telegram 趨勢圖發送失敗: {message}")
        finally:
            if delete_after_send:
                try:
                    os.remove(file_path)
                except Exception:
                    pass
