import datetime
import io
import logging
import re
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    _HAS_QT_MESSAGE_HANDLER = True
except Exception:
    QtMsgType = None
    qInstallMessageHandler = None
    _HAS_QT_MESSAGE_HANDLER = False

import config


_SESSION_LOG_RE = re.compile(
    r"^log_(?P<date>\d{8})(?:_(?P<session>\d{2,}))?(?:_part(?P<part>\d{2,}))?\.txt$",
    re.IGNORECASE,
)


class _StderrToLogger(io.TextIOBase):
    """
    將寫到 sys.stderr 的內容同步寫入 logger。
    可選擇是否保留原本 stderr 輸出到黑色 console 視窗。

    關鍵保護：
    1. 防止 logging -> stderr -> logger 的遞迴。
    2. 在 shutdown / pipe 已失效時自動停用。
    3. 失敗時優先靜默，不再二次點燃 logging 鏈。
    """

    def __init__(self, logger, original_stream=None, level=logging.ERROR, keep_console=True):
        super().__init__()
        self.logger = logger
        self.original_stream = original_stream
        self.level = level
        self.keep_console = keep_console
        self._buffer = ""
        self._disabled = False
        self._in_write = False
        self._lock = threading.RLock()

    def disable(self):
        with self._lock:
            self._disabled = True
            self._buffer = ""

    def _write_console(self, text: str):
        if not self.keep_console or self.original_stream is None or not text:
            return
        try:
            self.original_stream.write(text)
        except (OSError, ValueError):
            self.keep_console = False
        except Exception:
            self.keep_console = False

    def _flush_console(self):
        if not self.keep_console or self.original_stream is None:
            return
        try:
            self.original_stream.flush()
        except (OSError, ValueError):
            self.keep_console = False
        except Exception:
            self.keep_console = False

    def _emit_line_to_logger(self, line: str):
        if self._disabled or not line:
            return

        try:
            self.logger.log(self.level, "[STDERR] %s", line)
        except (OSError, ValueError):
            # 常見於 WinError 233、stream 已關閉、pipe 失效
            self._disabled = True
        except Exception:
            self._disabled = True

    def write(self, msg):
        if msg is None:
            return 0

        text = str(msg)
        if not text:
            return 0

        with self._lock:
            # 永遠先盡力保留 console 輸出
            self._write_console(text)

            if self._disabled:
                return len(text)

            # 若 logger 在 handleError 期間又回寫 stderr，直接吞掉，避免遞迴爆炸
            if self._in_write:
                return len(text)

            try:
                self._in_write = True
                self._buffer += text

                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    line = line.rstrip()
                    if line:
                        self._emit_line_to_logger(line)

                return len(text)
            finally:
                self._in_write = False

    def flush(self):
        with self._lock:
            self._flush_console()

            if self._disabled:
                self._buffer = ""
                return

            if self._in_write:
                return

            pending = self._buffer.rstrip()
            self._buffer = ""

            if not pending:
                return

            try:
                self._in_write = True
                self._emit_line_to_logger(pending)
            finally:
                self._in_write = False

    def isatty(self):
        try:
            if self.original_stream is not None:
                return self.original_stream.isatty()
        except Exception:
            pass
        return False

    @property
    def encoding(self):
        try:
            if self.original_stream is not None:
                return self.original_stream.encoding
        except Exception:
            pass
        return "utf-8"


class LogManager(QObject):
    """
    ReliabilityX Pro 系統日誌管理器
    負責處理系統事件、參數變更稽核與硬體健康監控，
    並透過 Signal 將日誌發送到 GUI。

    這版修正重點：
    1. 保留 File + Stream handler。
    2. 攔截未捕捉例外（主執行緒 / thread）。
    3. 將 stderr 內容同步寫入 log 檔，但加入防遞迴保護。
    4. 嘗試攔截 Qt warning / critical 訊息。
    5. shutdown 時先解除 stderr redirect，再做 flush / close。
    6. 每次啟動分配獨立 session log 檔名：
       - log_YYYYMMDD.txt
       - log_YYYYMMDD_02.txt
       - log_YYYYMMDD_03.txt
    7. 同一個 session 若檔案過大，自動切 part：
       - log_YYYYMMDD_part02.txt
       - log_YYYYMMDD_part03.txt
       - log_YYYYMMDD_02_part02.txt
    """

    log_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()

        self.settings = config.load_user_settings()
        self.log_dir = self._resolve_log_dir()

        # 可選：若 settings 沒有對應欄位，就採用預設值
        self.log_max_mb = self._safe_int(self.settings.get("log_max_mb"), 10, min_value=1)
        self.log_max_bytes = self.log_max_mb * 1024 * 1024
        self.log_backup_count = self._safe_int(self.settings.get("log_backup_count"), 200, min_value=1)

        # 每次啟動都分配一個新的 session log 檔名
        self.log_path = self._allocate_session_log_path(self.log_dir)
        self.log_filename = self.log_path.name

        self.logger = logging.getLogger("ReliabilityX_Pro")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        # 若同一個 process 內曾建立過舊 LogManager，先清乾淨 handler，避免檔案鎖或重複輸出
        for handler in list(self.logger.handlers):
            try:
                handler.flush()
            except Exception:
                pass
            try:
                handler.close()
            except Exception:
                pass
            try:
                self.logger.removeHandler(handler)
            except Exception:
                pass

        self._original_stdout = getattr(sys, "__stdout__", None) or sys.stdout
        self._original_stderr = getattr(sys, "__stderr__", None) or sys.stderr
        self._original_excepthook = sys.excepthook
        self._original_threading_excepthook = getattr(threading, "excepthook", None)

        self._stderr_redirector = None
        self._qt_message_handler_installed = False
        self._previous_qt_message_handler = None
        self._is_shutting_down = False
        self._is_shutdown_complete = False

        self._setup_logger()
        self._install_runtime_hooks()

        # 啟動時記一筆 session 基本資訊
        self.log_info(
            f"[LOG_SESSION] 啟動新日誌工作階段 | file={self.log_filename} | "
            f"max_size={self.log_max_mb}MB | backup_count={self.log_backup_count}"
        )

    def _safe_int(self, value, default, min_value=None):
        try:
            result = int(value)
        except (TypeError, ValueError):
            result = default

        if min_value is not None and result < min_value:
            result = min_value
        return result

    def _resolve_log_dir(self) -> Path:
        """解析並建立可用的日誌資料夾"""
        original_path = self.settings.get("log_dir")
        resolved_dir = config.resolve_user_dir(
            "log_dir",
            config.BASE_LOG_DIR,
            settings=self.settings,
            auto_persist=True,
        )

        if str(original_path or "") != str(resolved_dir):
            self._fallback_stderr_write(f"[PATH] 日誌目錄已自動修正為: {resolved_dir}")

        return resolved_dir

    def _build_formatter(self):
        return logging.Formatter(
            "%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def _fallback_stderr_write(self, text: str):
        if not text:
            return
        try:
            if self._original_stderr is not None:
                self._original_stderr.write(f"{text}\n")
                self._original_stderr.flush()
        except Exception:
            pass

    def _render_fallback_message(self, msg, args):
        try:
            if args:
                return str(msg) % args
            return str(msg)
        except Exception:
            try:
                joined_args = ", ".join(str(a) for a in args)
                return f"{msg} | args=[{joined_args}]"
            except Exception:
                return str(msg)

    def _allocate_session_log_path(self, log_dir: Path) -> Path:
        """
        為本次啟動分配唯一 log 檔名：
          第一次: log_YYYYMMDD.txt
          第二次: log_YYYYMMDD_02.txt
          第三次: log_YYYYMMDD_03.txt

        會連同同一天既有的 part 檔一起判斷，避免重複使用舊 session 編號。
        """
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        max_session_no = 0

        try:
            for path in log_dir.glob(f"log_{date_str}*.txt"):
                match = _SESSION_LOG_RE.match(path.name)
                if not match:
                    continue
                if match.group("date") != date_str:
                    continue

                session_str = match.group("session")
                session_no = int(session_str) if session_str else 1
                if session_no > max_session_no:
                    max_session_no = session_no
        except Exception:
            # 若掃描資料夾失敗，仍保底回到第一個命名
            pass

        next_session_no = max_session_no + 1
        if next_session_no <= 1:
            return log_dir / f"log_{date_str}.txt"
        return log_dir / f"log_{date_str}_{next_session_no:02d}.txt"

    def _rotated_log_namer(self, default_name: str) -> str:
        """
        將 RotatingFileHandler 預設檔名：
          log_20260327.txt.1
        改成：
          log_20260327_part02.txt

        若原本是：
          log_20260327_02.txt.1
        改成：
          log_20260327_02_part02.txt
        """
        path = Path(default_name)
        match = re.match(
            r"^(?P<stem>log_\d{8}(?:_\d{2,})?)\.txt\.(?P<roll>\d+)$",
            path.name,
            re.IGNORECASE,
        )
        if not match:
            return str(path)

        stem = match.group("stem")
        roll_index = int(match.group("roll"))
        part_no = roll_index + 1  # .1 -> part02, .2 -> part03
        return str(path.with_name(f"{stem}_part{part_no:02d}.txt"))

    def _create_file_handler(self, log_path: Path, formatter: logging.Formatter):
        """
        建立 session 專屬檔案 handler：
        - mode='w'：本次啟動從空白檔開始
        - maxBytes：檔案過大時切 part
        - backupCount：最多保留多少個 part
        """
        file_handler = RotatingFileHandler(
            filename=str(log_path),
            mode="w",
            maxBytes=self.log_max_bytes,
            backupCount=self.log_backup_count,
            encoding="utf-8-sig",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.namer = self._rotated_log_namer
        return file_handler

    def _setup_logger(self):
        """實作雙重處理器 (File & Stream)"""
        formatter = self._build_formatter()

        try:
            config.ensure_directory(self.log_dir, fallback=config.BASE_LOG_DIR)

            file_handler = self._create_file_handler(self.log_path, formatter)

            # 綁到原始 stdout，避免與 stderr redirect 形成回圈
            stream_handler = logging.StreamHandler(self._original_stdout)
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(formatter)

            self.logger.addHandler(file_handler)
            self.logger.addHandler(stream_handler)

        except OSError as exc:
            self._fallback_stderr_write(f"[CRITICAL] 無法初始化 Logger Handler: {exc}")

            try:
                self.log_dir = config.ensure_directory(config.BASE_LOG_DIR)
                self.log_path = self._allocate_session_log_path(self.log_dir)
                self.log_filename = self.log_path.name

                file_handler = self._create_file_handler(self.log_path, formatter)

                stream_handler = logging.StreamHandler(self._original_stdout)
                stream_handler.setLevel(logging.INFO)
                stream_handler.setFormatter(formatter)

                self.logger.addHandler(file_handler)
                self.logger.addHandler(stream_handler)
                self._fallback_stderr_write(f"[PATH] Logger 已回退至預設日誌目錄: {self.log_dir}")

            except OSError as fallback_exc:
                self._fallback_stderr_write(f"[FATAL] 連預設日誌目錄也無法建立: {fallback_exc}")

    def _install_runtime_hooks(self):
        """安裝全域錯誤攔截與 stderr 導流"""
        # 避免 logging handler emit 失敗時，再把內部 traceback 打回 stderr 造成連鎖爆炸
        logging.raiseExceptions = False

        sys.excepthook = self._handle_uncaught_exception

        if hasattr(threading, "excepthook"):
            threading.excepthook = self._handle_thread_exception

        self._stderr_redirector = _StderrToLogger(
            logger=self.logger,
            original_stream=self._original_stderr,
            level=logging.ERROR,
            keep_console=True,
        )
        sys.stderr = self._stderr_redirector

        if _HAS_QT_MESSAGE_HANDLER and callable(qInstallMessageHandler):
            try:
                self._previous_qt_message_handler = qInstallMessageHandler(self._qt_message_handler)
                self._qt_message_handler_installed = True
            except Exception as exc:
                self._safe_logger_call("warning", "[QT] 安裝 Qt message handler 失敗: %s", exc)

    def _safe_emit(self, level: str, msg: str):
        """
        關閉流程或 QObject/Signal 已不可用時，不再拋例外。
        """
        if self._is_shutting_down or self._is_shutdown_complete:
            return

        try:
            self.log_signal.emit(level, msg)
        except RuntimeError:
            pass
        except Exception:
            pass

    def _safe_logger_call(self, method_name: str, msg, *args, **kwargs):
        """
        安全呼叫 logger。
        若 handler / stream 已失效，直接 fallback 到原始 stderr，不再觸發第二輪 logging。
        """
        try:
            log_method = getattr(self.logger, method_name, None)
            if callable(log_method):
                log_method(msg, *args, **kwargs)
        except (OSError, ValueError) as exc:
            if self._stderr_redirector is not None:
                try:
                    self._stderr_redirector.disable()
                except Exception:
                    pass
            rendered = self._render_fallback_message(msg, args)
            self._fallback_stderr_write(
                f"[LOGGER_FALLBACK][{method_name.upper()}] {rendered} | {exc}"
            )
        except Exception as exc:
            if self._stderr_redirector is not None:
                try:
                    self._stderr_redirector.disable()
                except Exception:
                    pass
            rendered = self._render_fallback_message(msg, args)
            self._fallback_stderr_write(
                f"[LOGGER_FALLBACK][{method_name.upper()}] {rendered} | {exc}"
            )

    def _handle_uncaught_exception(self, exc_type, exc_value, exc_traceback):
        """
        攔截主執行緒未捕捉例外。
        """
        if exc_type is KeyboardInterrupt:
            if callable(self._original_excepthook):
                self._original_excepthook(exc_type, exc_value, exc_traceback)
            return

        formatted = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )

        self._safe_logger_call("critical", "[UNCAUGHT_EXCEPTION]\n%s", formatted)
        self._safe_emit("CRITICAL", f"[UNCAUGHT_EXCEPTION]\n{formatted}")
        self._flush_if_needed(force=True)

    def _handle_thread_exception(self, args):
        """
        攔截背景執行緒未捕捉例外。
        args: threading.ExceptHookArgs
        """
        thread_name = getattr(getattr(args, "thread", None), "name", "UnknownThread")
        exc_type = getattr(args, "exc_type", Exception)
        exc_value = getattr(args, "exc_value", None)
        exc_traceback = getattr(args, "exc_traceback", None)

        formatted = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )

        self._safe_logger_call("critical", "[THREAD_EXCEPTION][%s]\n%s", thread_name, formatted)
        self._safe_emit("CRITICAL", f"[THREAD_EXCEPTION][{thread_name}]\n{formatted}")
        self._flush_if_needed(force=True)

        # 若你希望保留 Python 預設 thread excepthook 行為，可自行打開：
        # if callable(self._original_threading_excepthook):
        #     self._original_threading_excepthook(args)

    def _qt_message_handler(self, mode, context, message):
        """
        攔截 Qt 訊息，保留到目前 session log。
        """
        if self._is_shutting_down or self._is_shutdown_complete:
            return

        try:
            category = getattr(context, "category", "") if context else ""
            file_name = getattr(context, "file", "") if context else ""
            line_no = getattr(context, "line", 0) if context else 0

            prefix = "[QT]"
            if category:
                prefix += f"[{category}]"
            if file_name:
                prefix += f"[{Path(file_name).name}:{line_no}]"

            text = f"{prefix} {message}"

            if mode == QtMsgType.QtDebugMsg:
                self._safe_logger_call("info", text)
                self._safe_emit("INFO", text)
            elif mode == QtMsgType.QtInfoMsg:
                self._safe_logger_call("info", text)
                self._safe_emit("INFO", text)
            elif mode == QtMsgType.QtWarningMsg:
                self._safe_logger_call("warning", text)
                self._safe_emit("WARNING", text)
            elif mode == QtMsgType.QtCriticalMsg:
                self._safe_logger_call("error", text)
                self._safe_emit("ERROR", text)
                self._flush_if_needed(force=True)
            elif mode == QtMsgType.QtFatalMsg:
                self._safe_logger_call("critical", text)
                self._safe_emit("CRITICAL", text)
                self._flush_if_needed(force=True)
            else:
                self._safe_logger_call("info", text)
                self._safe_emit("INFO", text)
        except Exception:
            # Qt handler 內不應再拋例外，避免造成更多訊息風暴
            pass

    def log_config_change(self, param_name, old_value, new_value, reason):
        """[稽核軌跡] 紀錄參數變更"""
        msg = (
            f"[CONFIG] {param_name} 變更 | "
            f"原始值: {old_value} -> 新值: {new_value} | "
            f"原因: {reason}"
        )
        self._safe_logger_call("info", msg)
        self._safe_emit("INFO", msg)
        self._flush_if_needed()

    def log_info(self, msg):
        """紀錄正常巡檢流程"""
        self._safe_logger_call("info", msg)
        self._safe_emit("INFO", msg)
        self._flush_if_needed()

    def log_warning(self, msg):
        """紀錄非致命硬體延遲或設定變更"""
        self._safe_logger_call("warning", msg)
        self._safe_emit("WARNING", msg)
        self._flush_if_needed()

    def log_error(self, msg, error_code=None, exc_info=False):
        """紀錄導致量測跳過的錯誤"""
        full_msg = f"{msg} (Error Code: {error_code})" if error_code else msg
        self._safe_logger_call("error", full_msg, exc_info=exc_info)
        self._safe_emit("ERROR", full_msg)
        self._flush_if_needed(force=True)

    def log_critical(self, msg, exc_info=False):
        """紀錄導致系統終止的致命事件"""
        self._safe_logger_call("critical", msg, exc_info=exc_info)
        self._safe_emit("CRITICAL", msg)
        self._flush_if_needed(force=True)

    def log_hardware_status(self, device_name, status_dict):
        """硬體健康度診斷"""
        status_str = ", ".join([f"{k}: {v}" for k, v in status_dict.items()])
        msg = f"[HEALTH] {device_name} 狀態: {status_str}"
        self._safe_logger_call("info", msg)
        self._safe_emit("INFO", msg)
        self._flush_if_needed()

    def _flush_if_needed(self, force=False):
        """確保日誌即時寫入磁碟"""
        if self.logger is None or not self.logger.handlers:
            return

        for handler in list(self.logger.handlers):
            try:
                handler.flush()
            except (OSError, ValueError):
                # 關閉期間或 stream 已失效時靜默處理
                if force:
                    self._fallback_stderr_write("[WARNING] Logger flush 失敗。")
            except Exception:
                if force:
                    self._fallback_stderr_write("[WARNING] Logger flush 發生非預期例外。")

        # 只有非 shutdown 狀態才允許去 flush redirector，避免關閉時再次觸發 logger
        if force and self._stderr_redirector is not None and not self._is_shutting_down:
            try:
                self._stderr_redirector.flush()
            except Exception:
                pass

    def shutdown(self):
        """
        程式結束前呼叫，恢復 hooks / streams。
        這裡最重要的是：
        1. 先標記 shutting down
        2. 先停用 stderr redirect
        3. 先恢復 sys.stderr
        4. 最後才 flush / close handlers
        """
        if self._is_shutdown_complete:
            return

        self._is_shutting_down = True

        try:
            if self._stderr_redirector is not None:
                self._stderr_redirector.disable()
        except Exception:
            pass

        try:
            if sys.stderr is self._stderr_redirector:
                sys.stderr = self._original_stderr
        except Exception:
            pass

        try:
            if callable(self._original_excepthook):
                sys.excepthook = self._original_excepthook
        except Exception:
            pass

        try:
            if hasattr(threading, "excepthook") and callable(self._original_threading_excepthook):
                threading.excepthook = self._original_threading_excepthook
        except Exception:
            pass

        try:
            if _HAS_QT_MESSAGE_HANDLER and self._qt_message_handler_installed and callable(qInstallMessageHandler):
                qInstallMessageHandler(self._previous_qt_message_handler)
                self._qt_message_handler_installed = False
        except Exception:
            pass

        # 注意：這裡故意不 force=True，避免再碰 stderr redirector
        try:
            self._flush_if_needed(force=False)
        except Exception:
            pass

        for handler in list(self.logger.handlers):
            try:
                handler.flush()
            except Exception:
                pass

            try:
                handler.close()
            except Exception:
                pass

            try:
                self.logger.removeHandler(handler)
            except Exception:
                pass

        self._is_shutdown_complete = True

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass