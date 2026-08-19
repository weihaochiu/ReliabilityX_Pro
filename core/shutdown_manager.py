"""Safe application shutdown orchestration for ReliabilityX Pro.

`MainWindow` should not directly perform every shutdown step.  This manager
centralizes the two operator-facing exit modes:

1. Safe process shutdown: freeze/stop the scheduler, let the current channel
   reach a safe boundary, save runtime state through the engine, force SMU OFF,
   reset relays, stop notifications, close child windows, stop the worker thread,
   and allow the Qt application to exit.
2. Emergency shutdown and exit: immediately request an abort, force SMU OFF,
   reset relays, close hardware connections, write a CRITICAL log, and exit.

The manager intentionally contains no GUI layout code except the confirmation
message box helper.  The main window remains responsible for presenting the
button and for calling this manager.
"""

from __future__ import annotations

import time
import datetime as _dt
from typing import Callable, Iterable, Optional

try:
    import config
except Exception:  # pragma: no cover - defensive for isolated unit tests
    config = None

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget


class ShutdownManager:
    """Coordinate safe and emergency application shutdown."""

    SAFE_MODE = "safe"
    EMERGENCY_MODE = "emergency"

    def __init__(
        self,
        *,
        engine,
        worker_thread: Optional[QThread] = None,
        log_manager=None,
        request_stop_callback: Optional[Callable[[], None]] = None,
        notification_stop_callback: Optional[Callable[[], None]] = None,
        child_windows: Optional[Iterable[QWidget]] = None,
    ):
        self.engine = engine
        self.worker_thread = worker_thread
        self.log_manager = log_manager or getattr(engine, "log_mgr", None)
        self.request_stop_callback = request_stop_callback
        self.notification_stop_callback = notification_stop_callback
        self.child_windows = list(child_windows or [])
        self.shutdown_in_progress = False
        self.last_mode = None

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _log(self, message: str, level: str = "info") -> None:
        prefix = "[SHUTDOWN] "
        text = prefix + str(message)
        mgr = self.log_manager
        if mgr is None:
            print(text)
            return
        try:
            if level == "critical" and hasattr(mgr, "log_critical"):
                mgr.log_critical(text)
            elif level in {"critical", "error"}:
                mgr.log_error(text)
            elif level == "warning":
                mgr.log_warning(text)
            else:
                mgr.log_info(text)
        except Exception:
            print(text)

    def _wait_for_engine_idle(self, timeout_sec: float) -> bool:
        """Wait for the measurement engine to leave the running state."""
        app = QApplication.instance()
        deadline = time.monotonic() + max(0.0, float(timeout_sec or 0.0))
        while bool(getattr(self.engine, "is_running", False)):
            if time.monotonic() >= deadline:
                return False
            if app is not None:
                app.processEvents()
            time.sleep(0.05)
        return True

    def _stop_notifications(self) -> None:
        if self.notification_stop_callback is None:
            return
        try:
            self.notification_stop_callback()
            self._log("Notification manager stopped.")
        except Exception as exc:
            self._log(f"Notification manager stop failed: {exc}", "warning")

    def _safe_hardware_state(self, *, close_connections: bool) -> None:
        """Force output-off / relay-reset through engine helper methods."""
        try:
            if hasattr(self.engine, "force_safe_hardware_state"):
                self.engine.force_safe_hardware_state(close_connections=close_connections)
            elif hasattr(self.engine, "shutdown_hardware"):
                self.engine.shutdown_hardware()
            self._log("Hardware safe-state command completed.")
        except Exception as exc:
            self._log(f"Hardware safe-state command failed: {exc}", "error")

    def _emergency_engine_shutdown(self) -> None:
        try:
            if hasattr(self.engine, "emergency_shutdown"):
                self.engine.emergency_shutdown()
            else:
                self._safe_hardware_state(close_connections=True)
            self._log("Emergency engine shutdown completed.", "critical")
        except Exception as exc:
            self._log(f"Emergency engine shutdown failed: {exc}", "critical")

    def _close_child_windows(self) -> None:
        for window in self.child_windows:
            if window is None:
                continue
            try:
                window.close()
            except Exception as exc:
                self._log(f"Child window close failed: {exc}", "warning")

    def _stop_worker_thread(self, timeout_ms: int = 5000) -> None:
        thread = self.worker_thread
        if thread is None:
            return
        try:
            thread.quit()
            if not thread.wait(timeout_ms):
                self._log("Worker thread did not stop before timeout.", "warning")
            else:
                self._log("Worker thread stopped.")
        except Exception as exc:
            self._log(f"Worker thread stop failed: {exc}", "warning")

    def _flush_logs(self) -> None:
        mgr = self.log_manager
        if mgr is None:
            return
        try:
            if hasattr(mgr, "flush"):
                mgr.flush()
            for handler in getattr(getattr(mgr, "logger", None), "handlers", []) or []:
                try:
                    handler.flush()
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Confirmation dialog
    # ------------------------------------------------------------------
    def ask_shutdown_mode(self, parent: QWidget | None = None) -> Optional[str]:
        """Ask the operator which shutdown path should be executed."""
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("ReliabilityX Pro 關閉確認")
        msg.setText("請選擇關閉方式")
        msg.setInformativeText(
            "目前系統可能仍連接 SMU / Relay / Chamber。\n\n"
            "✅ 安全流程關閉：停止 scheduler，不再派發新量測；等待目前量測到安全邊界；"
            "關閉 SMU output、reset all relay、儲存 runtime schedule state、flush CSV/log，然後離開程式。\n\n"
            "⚠️ 緊急停止並關閉：立即要求中止量測，強制 SMU output OFF、reset all relay，"
            "儘可能寫入 log；目前量測點可能不完整。"
        )
        safe_btn = msg.addButton("✅ 安全流程關閉", QMessageBox.ButtonRole.AcceptRole)
        emergency_btn = msg.addButton("⚠️ 緊急停止並關閉", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(safe_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == safe_btn:
            return self.SAFE_MODE
        if clicked == emergency_btn:
            return self.EMERGENCY_MODE
        if clicked == cancel_btn:
            return None
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def shutdown(self, *, mode: str, parent: QWidget | None = None) -> bool:
        """Run the requested shutdown sequence.

        Returns True when `MainWindow` may proceed with closing itself.
        """
        if self.shutdown_in_progress:
            self._log("Shutdown request ignored because another shutdown is already in progress.", "warning")
            return False

        mode = (mode or "").strip().lower()
        if mode not in {self.SAFE_MODE, self.EMERGENCY_MODE}:
            self._log(f"Unknown shutdown mode: {mode}", "warning")
            return False

        self.shutdown_in_progress = True
        self.last_mode = mode

        if mode == self.EMERGENCY_MODE:
            self._log("EMERGENCY_SHUTDOWN_AND_EXIT requested by operator.", "critical")
            self._stop_notifications()
            self._emergency_engine_shutdown()
            self._close_child_windows()
            self._stop_worker_thread(timeout_ms=3000)
            self._flush_logs()
            return True

        self._log("SAFE_PROCESS_SHUTDOWN requested by operator.")
        self._stop_notifications()

        if bool(getattr(self.engine, "is_running", False)):
            self._log("Requesting graceful scheduler stop before application exit.")
            try:
                # The measurement loop may be occupying the worker thread, so a queued
                # stop slot can be delayed until too late.  Set the cooperative stop
                # flags directly first; then also emit the normal UI stop callback for
                # consistency with the rest of the application.
                setattr(self.engine, "stop_requested", True)
                setattr(self.engine, "stop_request_reason", "safe_shutdown_after_current_channel")
                setattr(self.engine, "stop_request_at", _dt.datetime.now())
                if self.request_stop_callback is not None:
                    self.request_stop_callback()
                elif hasattr(self.engine, "stop_scan_cycle"):
                    self.engine.stop_scan_cycle()
            except Exception as exc:
                self._log(f"Graceful stop request failed: {exc}", "error")

            timeout_sec = getattr(config, "SAFE_SHUTDOWN_WAIT_SEC", 600) if config is not None else 600
            if not self._wait_for_engine_idle(timeout_sec):
                self._log(
                    "Safe shutdown timed out before the current measurement reached a safe boundary. "
                    "Application close is cancelled; use emergency shutdown if hardware safety requires immediate abort.",
                    "error",
                )
                self.shutdown_in_progress = False
                if parent is not None:
                    QMessageBox.critical(
                        parent,
                        "安全流程關閉逾時",
                        "目前量測尚未到達安全停止邊界，因此未關閉程式。\n\n"
                        "若硬體安全需要立即中止，請再次按下安全關閉程式並選擇「緊急停止並關閉」。",
                    )
                return False

        self._safe_hardware_state(close_connections=True)
        self._close_child_windows()
        self._stop_worker_thread(timeout_ms=5000)
        self._flush_logs()
        self._log("SAFE_PROCESS_SHUTDOWN completed.")
        self._flush_logs()
        return True
