"""gui/main_window.py

Dynamic logical channel update:
- Replace the fixed 32-card display with a dynamic list of configured logical
  channels.
- Add a 「新增 Channel」 button that opens the existing channel setting dialog
  on the next unused internal channel id.
- Keep the internal numeric `ch_id` for compatibility with existing loggers and
  signals, while displaying logical labels such as CH_C01 / CH_I01 / CH_V01.
- Start scans from enabled dynamic cards only.
- Group cards by environment and allow ending/removing a logical channel while
  preserving an archive record for traceability.
- The channel card checkbox explicitly starts/pauses cyclic measurement and
  requires confirmation before changing state.
- Legacy/draft channel entries without a complete relay path are hidden to avoid
  duplicate derived logical labels.
- Global scheduler buttons are labeled as 「啟動全部循環量測」 and
  「停止全部循環量測」, both requiring confirmation before changing the
  whole-system scheduler state.
- The left-side control panel status label is updated from scan lifecycle and
  current-channel signals.
"""

import copy

import config

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QGridLayout,
    QDialog,
    QMessageBox,
    QPushButton,
    QScrollArea,
)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QTimer

from gui.channel_setting_dialog import ChannelSettingDialog
from gui.system_config_dialog import SystemConfigDialog
from gui.iv_monitor_window import IVMonitorWindow
from gui.trend_chart_window import TrendChartWindow
from gui.widgets.channel_card import ChannelCard
from gui.widgets.control_panel import ControlPanel
from core.environment_manager import EnvironmentManager
from core.measurement_schema import forward_card_metrics
from core.measurement_outcome import validate_channel_for_measurement
from core.notification_manager import NotificationManager
from core.shutdown_manager import ShutdownManager
from gui.trend_snapshot_renderer import TrendSnapshotRenderer
from gui.settings_save_controller import JsonDebouncedSaveController
from core.channel_identity import (
    build_archive_record,
    generate_run_session_id,
    migrate_channel_settings_file,
    normalize_channel_record,
)


class MainWindow(QMainWindow):
    """ReliabilityX Pro main control interface with dynamic logical channels."""

    request_init_hardware = pyqtSignal()
    request_start_scan = pyqtSignal(list)
    request_stop_scan = pyqtSignal()
    request_reload_config = pyqtSignal()
    request_poll_chamber = pyqtSignal()

    MAX_LOGICAL_CHANNEL_ID = 999

    def __init__(self, measure_engine, log_window):
        super().__init__()

        self.engine = measure_engine
        self.log_window = log_window
        self.cards = []
        self.cards_by_ch_id = {}
        self.environment_manager = EnvironmentManager()

        self.trend_snapshot_renderer = TrendSnapshotRenderer(
            getattr(self.engine, "log_mgr", None)
        )
        self.notification_manager = NotificationManager(
            self.engine,
            getattr(self.engine, "log_mgr", None),
            trend_renderer=self.trend_snapshot_renderer,
            parent=self,
        )
        self.shutdown_manager = None
        self._allow_close = False
        self._pending_channel_settings = None
        self._channel_settings_save_token = None
        self._channel_settings_rollback = None
        self._pending_runtime_channel_changes = {}
        self._channel_save_batches = {}
        self._applied_toggle_states = {}

        migrate_channel_settings_file(config.CHANNEL_SETTINGS_FILE, save=True)

        self.setWindowTitle("ReliabilityX Pro - 太陽能電池可靠度巡檢系統 v1.8.0")
        self.setMinimumSize(1200, 800)

        self.iv_monitor = IVMonitorWindow()
        self.trend_chart = TrendChartWindow()

        self.iv_monitor_window = self.iv_monitor
        self.trend_chart_window = self.trend_chart

        self.thread = QThread(self)
        self.engine.moveToThread(self.thread)
        self.thread.start()

        self.shutdown_manager = ShutdownManager(
            engine=self.engine,
            worker_thread=self.thread,
            log_manager=getattr(self.engine, "log_mgr", None),
            request_stop_callback=self.request_stop_scan.emit,
            notification_stop_callback=self.notification_manager.stop,
            child_windows=[self.iv_monitor, self.trend_chart, self.log_window],
        )

        self.channel_settings_save_controller = JsonDebouncedSaveController(self, debounce_ms=500)
        self.channel_settings_save_controller.saveSucceeded.connect(self._on_channel_settings_save_succeeded)
        self.channel_settings_save_controller.saveFailed.connect(self._on_channel_settings_save_failed)

        self.chamber_poll_timer = QTimer(self)
        self.chamber_poll_timer.setInterval(5000)
        self.chamber_poll_timer.timeout.connect(self.request_poll_chamber.emit)

        self.init_ui()
        self.connect_signals()
        self.notification_manager.start()

        self.load_and_refresh_all_channels()
        self.request_init_hardware.emit()

    def _log_ui(self, message: str, level: str = "info"):
        """Write a UI-originated event to the log manager when available."""
        log_mgr = getattr(self.engine, "log_mgr", None)
        if not log_mgr:
            print(f"[UI][{level.upper()}] {message}")
            return
        if level == "warning":
            log_mgr.log_warning(message)
        elif level == "error":
            log_mgr.log_error(message)
        else:
            log_mgr.log_info(message)


    def _get_channel_settings_for_edit(self):
        """Return latest channel settings, including any pending debounced save."""
        pending = None
        if hasattr(self, "channel_settings_save_controller"):
            pending = self.channel_settings_save_controller.pending_payload(config.CHANNEL_SETTINGS_FILE)
        if pending is not None:
            return pending
        if isinstance(self._pending_channel_settings, dict):
            return copy.deepcopy(self._pending_channel_settings)
        return config.load_json_file(config.CHANNEL_SETTINGS_FILE)

    @pyqtSlot(str, object)
    def _on_channel_settings_save_succeeded(self, file_path, token):
        """Apply saved toggles through the engine's thread-safe request queue."""
        if str(file_path) != str(config.CHANNEL_SETTINGS_FILE):
            return
        batch = self._channel_save_batches.pop(token, {})
        for ch_id, (channel, enabled) in batch.items():
            if self._applied_toggle_states.get(ch_id) != enabled:
                self.engine.queue_channel_enabled(channel, enabled)
                self._applied_toggle_states[ch_id] = enabled
        self._channel_save_batches = {key: value for key, value in self._channel_save_batches.items() if key > token}
        if token == self._channel_settings_save_token:
            self._pending_runtime_channel_changes.clear()
            self._pending_channel_settings = None
            self._channel_settings_rollback = None
            self._log_ui("[UI][CONFIG] channel_settings.json debounced async save completed")

    @pyqtSlot(str, str, object)
    def _on_channel_settings_save_failed(self, file_path, error, token):
        """Roll back all coalesced toggles; failed saves never reach hardware."""
        if str(file_path) != str(config.CHANNEL_SETTINGS_FILE):
            return
        if token != self._channel_settings_save_token:
            return
        rollback = self._channel_settings_rollback or {}
        persisted = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        for ch_id, old_val in rollback.items():
            if ch_id in self.cards_by_ch_id:
                saved_value = persisted.get(str(ch_id), {}).get("is_enabled", old_val)
                self.cards_by_ch_id[ch_id].set_checked(bool(saved_value))
        self._pending_channel_settings = None
        self._pending_runtime_channel_changes.clear()
        self._channel_save_batches.clear()
        self._channel_settings_rollback = None
        self._log_ui(f"[UI][CONFIG] channel_settings.json debounced save failed: {error}", "error")
        QMessageBox.critical(self, "儲存失敗", f"無法更新 Channel 循環量測狀態；本次變更未套用到排程。\n\n{error}")

    def init_ui(self):
        """Build the main window layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.control_panel = ControlPanel()
        main_layout.addWidget(self.control_panel, 1)

        channel_group = QGroupBox("動態 Channel 狀態巡檢清單")
        channel_group_layout = QVBoxLayout(channel_group)

        self.btn_add_channel = QPushButton("＋ 新增 Channel")
        self.btn_add_channel.setMinimumHeight(36)
        channel_group_layout.addWidget(self.btn_add_channel)

        self.channel_scroll = QScrollArea()
        self.channel_scroll.setWidgetResizable(True)
        self.channel_container = QWidget()
        self.channel_list_layout = QVBoxLayout(self.channel_container)
        self.channel_list_layout.setSpacing(12)
        self.channel_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.channel_scroll.setWidget(self.channel_container)
        channel_group_layout.addWidget(self.channel_scroll)

        main_layout.addWidget(channel_group, 3)

    def connect_signals(self):
        """Connect engine, control panel, and dynamic-card signals."""
        self.request_init_hardware.connect(
            self.engine.initialize_hardware,
            Qt.ConnectionType.QueuedConnection,
        )
        self.request_start_scan.connect(
            self.engine.start_scan_cycle,
            Qt.ConnectionType.QueuedConnection,
        )
        self.request_stop_scan.connect(
            self.engine.queue_graceful_stop,
            Qt.ConnectionType.DirectConnection,
        )

        if hasattr(self.engine, "reload_config"):
            self.request_reload_config.connect(
                self.engine.reload_config,
                Qt.ConnectionType.QueuedConnection,
            )

        if hasattr(self.engine, "poll_chamber_once"):
            self.request_poll_chamber.connect(
                self.engine.poll_chamber_once,
                Qt.ConnectionType.QueuedConnection,
            )
            self.chamber_poll_timer.start()

        if hasattr(self.engine, "hardware_status_updated"):
            self.engine.hardware_status_updated.connect(
                self.control_panel.set_hardware_status
            )

        if hasattr(self.engine, "env_data_updated"):
            self.engine.env_data_updated.connect(
                self.control_panel.update_env_data
            )

        if hasattr(self.engine, "scan_started"):
            self.engine.scan_started.connect(self.control_panel.on_scan_started)
            self.engine.scan_started.connect(self.on_scan_started_show_windows)
            self.engine.scan_started.connect(self.notification_manager.on_scan_started)

        if hasattr(self.engine, "scan_finished"):
            self.engine.scan_finished.connect(self.on_scan_finished)
            self.engine.scan_finished.connect(self.notification_manager.on_scan_finished)

        if hasattr(self.engine, "channel_status_updated"):
            self.engine.channel_status_updated.connect(self.update_realtime_status)

        if hasattr(self.engine, "channel_scan_pre_start"):
            self.engine.channel_scan_pre_start.connect(self.on_channel_scan_pre_start)

        if hasattr(self.engine, "channel_measurement_finished"):
            self.engine.channel_measurement_finished.connect(
                self.on_measurement_finished
            )
            self.engine.channel_measurement_finished.connect(
                self.notification_manager.on_channel_measurement_finished
            )

        self._try_connect_engine_window_signals()

        self.control_panel.reinit_hw_requested.connect(
            self.on_hardware_init_clicked
        )
        self.control_panel.start_scan_requested.connect(self.on_start_clicked)
        self.control_panel.stop_scan_requested.connect(self.on_stop_clicked)
        self.control_panel.sys_config_requested.connect(self.on_settings_clicked)
        self.control_panel.show_iv_trend_requested.connect(
            self.on_show_iv_trend_clicked
        )
        self.control_panel.show_logs_requested.connect(self.on_show_logs_clicked)
        self.control_panel.exit_requested.connect(self.on_exit_requested)
        self.btn_add_channel.clicked.connect(self.on_add_channel_clicked)

    def _try_connect_engine_window_signals(self):
        """Connect optional engine signals to optional monitoring windows."""
        safe_connections = [
            ("scan_started", self._safe_slot(self.iv_monitor, "clear_buffer")),
            ("measurement_preparing", self._safe_slot(self.iv_monitor, "prepare_for_scan")),
            ("channel_scan_prepared", self._safe_slot(self.iv_monitor, "prepare_for_scan")),
            ("channel_scan_pre_start", self._safe_slot(self.iv_monitor, "prepare_for_channel")),
            ("iv_point_acquired", self._safe_slot(self.iv_monitor, "update_plot")),
            ("point_measured", self._safe_slot(self.iv_monitor, "update_plot")),
            ("channel_measurement_finished", self._safe_slot(self.iv_monitor, "show_final_params")),
            ("channel_measurement_finished", self._safe_slot(self.trend_chart, "add_new_data")),
        ]

        for signal_name, slot in safe_connections:
            if slot is None:
                continue
            signal_obj = getattr(self.engine, signal_name, None)
            if signal_obj is None:
                continue
            try:
                signal_obj.connect(slot)
            except Exception:
                pass

    def _safe_slot(self, obj, method_name):
        """Return a callable method when available."""
        method = getattr(obj, method_name, None)
        if callable(method):
            return method
        return None

    def _show_and_focus_window(self, window):
        """Show, raise, and activate a monitoring window if possible."""
        if window is None:
            return

        try:
            if window.isMinimized():
                window.showNormal()
            else:
                window.show()
        except Exception:
            try:
                window.show()
            except Exception:
                return

        try:
            window.raise_()
        except Exception:
            pass

        try:
            window.activateWindow()
        except Exception:
            pass

    def _set_global_scheduler_status(self, text: str, status_level: str = "idle"):
        """Update the left control panel's global scheduler status label."""
        setter = getattr(self.control_panel, "set_scheduler_status", None)
        if callable(setter):
            setter(text, status_level)

    def _confirm_start_all_cyclic_measurement(self, active_channels_data: list[dict]) -> bool:
        """Confirm before starting the whole cyclic-measurement scheduler."""
        preview_lines = []
        for ch_data in active_channels_data[:8]:
            label = ch_data.get("channel_label") or f"CH{int(ch_data.get('ch_id', 0)):02d}"
            device = ch_data.get("device_name") or "未命名"
            interval = ch_data.get("interval_min", "--")
            preview_lines.append(f"- {label} / {device} / {interval} min")
        if len(active_channels_data) > 8:
            preview_lines.append(f"- ... 另有 {len(active_channels_data) - 8} 個 Channel")

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("確認啟動全部循環量測")
        msg.setText("確認啟動全部循環量測？")
        msg.setInformativeText(
            "系統將開始執行所有已勾選「開始循環量測」的 Channel；"
            "未勾選或已暫停的 Channel 不會納入本次排程。\n\n"
            "量測開始後，系統會依照各 Channel 的 interval_min / next_due_time 排程執行，"
            "並在每次 Channel 量測前先關閉所有 Relay，再開啟該 Channel 對應 Relay。\n\n"
            f"本次將啟動 {len(active_channels_data)} 個 Channel：\n"
            + "\n".join(preview_lines)
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        return msg.exec() == QMessageBox.StandardButton.Yes

    def _estimate_channel_duration_sec(self, ch_data: dict) -> float:
        try:
            v_start = float(ch_data.get("v_start", 0.0))
            v_stop = float(ch_data.get("v_stop", 0.0))
            v_step = abs(float(ch_data.get("v_step", 0.02) or 0.02))
            delay_sec = max(0.0, float(ch_data.get("delay_time", 50) or 50) / 1000.0)
            point_count = int(abs(v_stop - v_start) / v_step) + 1 if v_step > 0 else 1
            return max(1.0, (point_count * 2 * (delay_sec + 0.12)) + 1.0)
        except Exception:
            return 10.0

    def _build_scheduler_overload_info(self, active_channels_data: list[dict]) -> dict:
        active = list(active_channels_data or [])
        if not active:
            return {"overloaded": False}
        total_required = sum(self._estimate_channel_duration_sec(ch) for ch in active)
        intervals = []
        for ch in active:
            try:
                value = float(ch.get("interval_min", 0) or 0) * 60.0
                if value > 0:
                    intervals.append(value)
            except Exception:
                continue
        if not intervals:
            return {"overloaded": False, "total_required_sec": total_required}
        min_interval = min(intervals)
        load_ratio = total_required / min_interval if min_interval > 0 else 0.0
        return {
            "overloaded": total_required > min_interval,
            "total_required_sec": total_required,
            "min_interval_sec": min_interval,
            "active_channel_count": len(active),
            "load_ratio": load_ratio,
        }

    def _confirm_scheduler_overload_if_needed(self, active_channels_data: list[dict]) -> tuple[bool, dict]:
        overload_info = self._build_scheduler_overload_info(active_channels_data)
        if not overload_info.get("overloaded"):
            return True, overload_info
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("排程超載警告")
        msg.setText("目前排程可能無法在最短量測間隔內完成。")
        scheduler_policy = config.get_scheduler_runtime_settings()
        policy_text = (
            "Flexible catch-up：延遲仍量測並完整記錄"
            if scheduler_policy.get("mode") == "flexible_catch_up"
            else f"Strict skip：delay > {scheduler_policy.get('max_allowed_delay_sec')} 秒時跳過該輪"
        )
        msg.setInformativeText(
            f"Active Channels: {overload_info.get('active_channel_count')}\n"
            f"預估單輪量測時間: {overload_info.get('total_required_sec', 0):.1f} 秒\n"
            f"最短 Channel 間隔: {overload_info.get('min_interval_sec', 0):.1f} 秒\n"
            f"負載比例: {overload_info.get('load_ratio', 0):.2f}x\n"
            f"目前排程策略: {policy_text}\n\n"
            "系統會記錄 scheduled/actual/delay/conflict metadata；"
            "若使用 Strict skip，超過容忍延遲的本輪 channel 會寫入 skipped_due_to_schedule_overrun。\n\n"
            "建議增加 interval、減少 active channels、放大 V step 或縮短 delay_time。是否仍要啟動？"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        ok = msg.exec() == QMessageBox.StandardButton.Yes
        if ok:
            self._log_ui(
                f"[UI][SCHED] 使用者確認超載排程仍啟動 | "
                f"load_ratio={overload_info.get('load_ratio', 0):.2f} | "
                f"total_required_sec={overload_info.get('total_required_sec', 0):.1f} | "
                f"min_interval_sec={overload_info.get('min_interval_sec', 0):.1f}",
                "warning",
            )
        else:
            self._log_ui("[UI][SCHED] 使用者因排程超載取消啟動", "warning")
        return ok, overload_info

    def _validate_rline_before_start(self, active_channels_data: list[dict]) -> bool:
        cal_data = config.load_json_file(config.CALIBRATION_SETTINGS_FILE)
        if not isinstance(cal_data, dict):
            cal_data = {}
        missing = []
        expired = []
        max_age = config.get_rline_calibration_max_age_days()
        for ch_data in active_channels_data:
            pos = ch_data.get("relay_pos")
            neg = ch_data.get("relay_neg")
            label = ch_data.get("channel_label") or f"CH{int(ch_data.get('ch_id', 0)):02d}"
            status = config.evaluate_rline_calibration(pos, neg, calibration_data=cal_data, max_age_days=max_age)
            if not status.get("exists") or status.get("value") is None:
                missing.append(f"- {label}: SMU+ {pos} / SMU− {neg}")
            elif status.get("expired"):
                age_days = status.get("age_days")
                if age_days is None:
                    age_text = "無可追溯時間戳"
                else:
                    age_text = f"{age_days:.0f} 天前"
                expired.append(f"- {label}: {age_text}，門檻 {max_age} 天")
        if missing:
            QMessageBox.warning(
                self,
                "R-line 線阻尚未量測",
                "以下 Channel 的 SMU+/SMU− 組合尚未完成 R-line 線路阻抗量測，不能啟動量測：\n\n"
                + "\n".join(missing[:20])
                + (f"\n...另有 {len(missing) - 20} 筆" if len(missing) > 20 else "")
                + "\n\n請先到 Channel 設定頁按下「量測線路阻抗」。",
            )
            return False
        if expired:
            QMessageBox.warning(
                self,
                "R-line 校正已超過提醒期限",
                "以下 Channel 的 R-line 校正已超過全域提醒天數或缺少可追溯時間戳，不能啟動量測：\n\n"
                + "\n".join(expired[:20])
                + (f"\n...另有 {len(expired) - 20} 筆" if len(expired) > 20 else "")
                + "\n\n請先到 Channel 設定頁按下「量測線路阻抗」，完成本次實際 relay pair 的重新校正。",
            )
            return False
        return True

    def _confirm_graceful_stop(self) -> bool:
        """Confirm before stopping the whole cyclic-measurement scheduler."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("確認停止全部循環量測")
        msg.setText("確認停止全部循環量測？")
        msg.setInformativeText(
            "系統將停止全域量測排程，不再啟動新的 Channel 量測。\n\n"
            "若目前有 Channel 正在量測，系統會於目前 Channel 正掃與逆掃完成後，"
            "在安全狀態下停止：SMU output OFF，並執行 Relay reset_all。\n\n"
            "此操作不會刪除 Channel 設定，也不會釋放 Relay。"
            "若要結束單一實驗，請使用該 Channel 卡片上的「結束實驗 / 移除」。"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            self._log_ui("[UI] 使用者取消停止全部循環量測", "warning")
            return False
        return True

    def _infer_status_level_from_message(self, message: str) -> str:
        """Infer card status style from a status message."""
        msg = str(message or "")
        msg_lower = msg.lower()

        if (
            "failed" in msg_lower
            or "error" in msg_lower
            or "錯誤" in msg
            or "失敗" in msg
            or "異常" in msg
        ):
            return "error"

        if (
            "warning" in msg_lower
            or "warn" in msg_lower
            or "警告" in msg
            or "注意" in msg
        ):
            return "warning"

        if (
            "complete" in msg_lower
            or "completed" in msg_lower
            or "finished" in msg_lower
            or "done" in msg_lower
            or "完成" in msg
            or "成功" in msg
        ):
            return "ok"

        return "info"

    def _has_complete_relay_path(self, settings: dict) -> bool:
        """Return whether a logical channel has a usable SMU+/SMU− path."""
        if not isinstance(settings, dict):
            return False
        try:
            int(settings.get("relay_pos"))
            int(settings.get("relay_neg"))
            return True
        except (TypeError, ValueError):
            return False

    def _is_channel_configured(self, settings: dict) -> bool:
        """Return whether one settings entry should appear in the main list.

        Legacy fixed-channel entries may contain `is_enabled`, empty user fields,
        or other defaults even when no logical channel has actually been created.
        The dynamic main list should only show channels that have a complete relay
        path. This prevents draft/legacy blanks such as `+R-- / -R--` from being
        rendered as duplicate CH_I01 / CH_C01 / CH_V01 cards.
        """
        return self._has_complete_relay_path(settings)

    def _configured_channel_items(self, all_settings: dict):
        """Return sorted configured channel items as `(ch_id, settings)` tuples."""
        items = []
        for key, value in (all_settings or {}).items():
            if not str(key).isdigit() or not self._is_channel_configured(value):
                continue
            items.append((int(key), value))
        return sorted(items, key=self._channel_sort_key)

    def _channel_sort_key(self, item):
        """Sort by environment group, logical label number, and internal id."""
        ch_id, settings = item
        group_order, group_title, group_id = self._environment_group_key(settings or {})
        label = self._display_label_for_channel(ch_id, settings or {}, {str(ch_id): settings or {}})
        number = ch_id
        for prefix in ("CH_V", "CH_I", "CH_C", "CH_X"):
            if label.startswith(prefix):
                suffix = label.replace(prefix, "", 1)
                try:
                    number = int(suffix)
                except ValueError:
                    number = ch_id
                break
        return (group_order, group_title, group_id, number, ch_id)

    def _environment_instance_for_prefix(self, prefix: str) -> str:
        """Return the first configured environment instance that matches a prefix."""
        type_groups = {
            "C": {"climate"},
            "I": {"indoor"},
            "V": {"glovebox", "vacuum", "vacuum_glovebox"},
        }
        wanted = type_groups.get(prefix, set())
        for instance_id in self.environment_manager.list_instances():
            instance = self.environment_manager.get_instance(instance_id)
            if instance and str(instance.env_type).strip().lower() in wanted:
                return instance_id
        return ""

    def _environment_prefix_from_instance(self, environment_instance: str) -> str:
        """Return CH label prefix from an environment instance id."""
        instance = self.environment_manager.get_instance(str(environment_instance or ""))
        env_type = str(getattr(instance, "env_type", "") or "").strip().lower()
        if env_type == "climate":
            return "C"
        if env_type == "indoor":
            return "I"
        if env_type in {"glovebox", "vacuum", "vacuum_glovebox"}:
            return "V"
        return "X"

    def _infer_environment_instance_from_settings(self, settings: dict) -> str:
        """Infer the environment instance from saved value, label prefix, or relay range.

        This keeps the main card, logical channel name, and detail dialog aligned
        for legacy settings that predate `environment_instance`.
        """
        settings = settings or {}
        saved = str(settings.get("environment_instance") or "").strip()
        if saved and self.environment_manager.get_instance(saved) is not None:
            return saved

        label = str(settings.get("channel_label") or "").strip()
        for prefix in ("C", "I", "V"):
            if label.startswith(f"CH_{prefix}"):
                by_label = self._environment_instance_for_prefix(prefix)
                if by_label:
                    return by_label

        try:
            relay_pos = int(settings.get("relay_pos"))
            relay_neg = int(settings.get("relay_neg"))
        except (TypeError, ValueError):
            relay_pos = relay_neg = None

        if relay_pos is not None and relay_neg is not None:
            for instance_id in self.environment_manager.list_instances():
                relay_range = self.environment_manager.get_relay_range(instance_id)
                pos_range = relay_range.get("smu_plus", (None, None))
                neg_range = relay_range.get("smu_minus", (None, None))
                if (
                    pos_range[0] is not None
                    and neg_range[0] is not None
                    and pos_range[0] <= relay_pos <= pos_range[1]
                    and neg_range[0] <= relay_neg <= neg_range[1]
                ):
                    return instance_id

        return saved

    def _environment_group_key(self, settings: dict) -> tuple[int, str, str]:
        """Return `(order, title, id)` for grouping cards by environment."""
        env_instance_id = self._infer_environment_instance_from_settings(settings or {})
        instance = self.environment_manager.get_instance(env_instance_id)
        prefix = self._environment_prefix_from_instance(env_instance_id)
        order_map = {"V": 0, "I": 1, "C": 2, "X": 99}
        order = order_map.get(prefix, 99)
        if instance is None:
            return (order, "未指定環境", env_instance_id or "UNASSIGNED")
        title = str(instance.title or env_instance_id)
        prefix_label = {"V": "CH_V 真空 / Glovebox", "I": "CH_I 室內環境", "C": "CH_C Climate Chamber"}.get(prefix, "CH_X 未分類")
        return (order, f"{prefix_label} — {title}", env_instance_id)

    def _device_label(self, settings: dict, fallback_ch_id: int) -> str:
        """Return a readable label for relay-sharing summaries."""
        label = str((settings or {}).get("channel_label") or "").strip()
        device = str((settings or {}).get("device_name") or "").strip()
        if label and device:
            return f"{label} / {device}"
        if device:
            return device
        if label:
            return label
        return f"CH{fallback_ch_id:02d}"

    def _prefix_from_channel_settings(self, settings: dict) -> str:
        """Infer logical prefix from the canonical environment instance."""
        env_instance = self._infer_environment_instance_from_settings(settings or {})
        prefix = self._environment_prefix_from_instance(env_instance)
        if prefix != "X":
            return prefix

        try:
            relay_pos = int((settings or {}).get("relay_pos"))
        except (TypeError, ValueError):
            return "X"
        if 0 <= relay_pos <= 7:
            return "C"
        if 8 <= relay_pos <= 15:
            return "I"
        if 16 <= relay_pos <= 23:
            return "V"
        return "X"

    def _label_number(self, label: str, prefix: str) -> int | None:
        """Extract the numeric suffix from a logical label if it matches prefix."""
        label = str(label or "").strip()
        token = f"CH_{prefix}"
        if not label.startswith(token):
            return None
        try:
            return int(label.replace(token, "", 1))
        except ValueError:
            return None

    def _display_label_for_channel(self, ch_id: int, settings: dict, all_settings: dict) -> str:
        """Return persisted or derived logical label aligned to environment.

        The derived labels reserve explicit labels first, then assign labels to
        unlabeled valid channels in internal-id order. This prevents duplicate
        names when legacy settings did not persist `channel_label`.
        """
        settings = settings or {}
        prefix = self._prefix_from_channel_settings(settings)
        explicit_number = self._label_number(settings.get("channel_label"), prefix)
        if explicit_number is not None:
            return f"CH_{prefix}{explicit_number:02d}"

        used_numbers = set()
        unlabeled_same_prefix_ids = []
        for key, item_settings in (all_settings or {}).items():
            if not str(key).isdigit() or not self._is_channel_configured(item_settings):
                continue
            item_prefix = self._prefix_from_channel_settings(item_settings)
            if item_prefix != prefix:
                continue
            item_number = self._label_number((item_settings or {}).get("channel_label"), prefix)
            if item_number is not None:
                used_numbers.add(item_number)
            else:
                unlabeled_same_prefix_ids.append(int(key))

        unlabeled_same_prefix_ids.sort()
        assigned_numbers = {}
        next_number = 1
        for item_id in unlabeled_same_prefix_ids:
            while next_number in used_numbers:
                next_number += 1
            assigned_numbers[item_id] = next_number
            used_numbers.add(next_number)
            next_number += 1

        sequence = assigned_numbers.get(ch_id)
        if sequence is None:
            while next_number in used_numbers:
                next_number += 1
            sequence = next_number
        return f"CH_{prefix}{sequence:02d}"

    def _relay_sharing_lines(self, ch_id: int, settings: dict, all_settings: dict):
        """Build relay-sharing detail lines for one channel tooltip."""
        lines = []
        relay_pos = settings.get("relay_pos")
        relay_neg = settings.get("relay_neg")
        try:
            relay_pos_int = int(relay_pos) if relay_pos is not None else None
        except (TypeError, ValueError):
            relay_pos_int = None
        try:
            relay_neg_int = int(relay_neg) if relay_neg is not None else None
        except (TypeError, ValueError):
            relay_neg_int = None

        for polarity, relay_pin, same_key in [
            ("正極", relay_pos_int, "relay_pos"),
            ("負極", relay_neg_int, "relay_neg"),
        ]:
            if relay_pin is None:
                continue
            shared = []
            for other_key, other in (all_settings or {}).items():
                if not str(other_key).isdigit() or int(other_key) == ch_id or not isinstance(other, dict):
                    continue
                try:
                    if other.get(same_key) is not None and int(other.get(same_key)) == relay_pin:
                        shared.append(self._device_label(other, int(other_key)))
                except (TypeError, ValueError):
                    continue
            if shared:
                lines.append(f"Relay {relay_pin} 與 {'、'.join(shared)} 共用{polarity}")
            else:
                lines.append(f"Relay {relay_pin} 為獨立 relay（{polarity}）")
        return lines

    def _decorate_channel_for_display(self, ch_id: int, settings: dict, all_settings: dict):
        """Add derived display strings without changing the persisted settings."""
        display = dict(settings or {})
        canonical_env = self._infer_environment_instance_from_settings(display)
        if canonical_env:
            display["environment_instance"] = canonical_env
        display["channel_label"] = self._display_label_for_channel(ch_id, display, all_settings)
        relay_pos = display.get("relay_pos")
        relay_neg = display.get("relay_neg")
        display["relay_share_summary"] = f"+R{relay_pos if relay_pos is not None else '--'} / -R{relay_neg if relay_neg is not None else '--'}"
        display["relay_detail_tooltip"] = "\n".join(
            self._relay_sharing_lines(ch_id, display, all_settings)
        )
        return display

    def _clear_card_grid(self):
        """Remove all dynamic channel groups and cards from the list."""
        while self.channel_list_layout.count():
            item = self.channel_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.cards.clear()
        self.cards_by_ch_id.clear()

    def load_and_refresh_all_channels(self):
        """Reload configured channels and rebuild cards grouped by environment."""
        all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        self._clear_card_grid()

        grouped_items = {}
        group_meta = {}
        for ch_id, ch_settings in self._configured_channel_items(all_settings):
            group_key = self._environment_group_key(ch_settings)
            grouped_items.setdefault(group_key, []).append((ch_id, ch_settings))
            group_meta[group_key] = group_key[1]

        for group_key in sorted(grouped_items.keys()):
            group_title = group_meta.get(group_key, group_key[1])
            group_box = QGroupBox(group_title)
            group_layout = QGridLayout(group_box)
            group_layout.setSpacing(10)

            for index, (ch_id, ch_settings) in enumerate(grouped_items[group_key]):
                card = ChannelCard(channel_id=ch_id)
                decorated = self._decorate_channel_for_display(ch_id, ch_settings, all_settings)
                card.update_data(decorated)
                card.config_requested.connect(self.on_channel_detail_clicked)
                card.end_requested.connect(self.on_end_channel_requested)
                card.chk_enabled.toggled.connect(
                    lambda state, ch=ch_id: self.on_channel_toggled(state, ch)
                )
                self.cards.append(card)
                self.cards_by_ch_id[ch_id] = card
                group_layout.addWidget(card, index // 3, index % 3)

            for col in range(3):
                group_layout.setColumnStretch(col, 1)

            self.channel_list_layout.addWidget(group_box)

        self.channel_list_layout.addStretch(1)

    def _next_free_internal_channel_id(self, all_settings: dict) -> int | None:
        """Return the next unused internal numeric channel id."""
        used = {
            int(key)
            for key in (all_settings or {}).keys()
            if str(key).isdigit()
        }
        for ch_id in range(1, self.MAX_LOGICAL_CHANNEL_ID + 1):
            if ch_id not in used:
                return ch_id
        return None

    @pyqtSlot()
    def on_add_channel_clicked(self):
        """Open a blank settings dialog for a new logical channel."""
        all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        new_ch_id = self._next_free_internal_channel_id(all_settings)
        if new_ch_id is None:
            QMessageBox.warning(
                self,
                "無法新增 Channel",
                "已達可管理的 logical channel 數量上限。",
            )
            return

        dialog = ChannelSettingDialog(
            new_ch_id,
            self.engine,
            getattr(self.engine, "log_mgr", None),
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_and_refresh_all_channels()

    @pyqtSlot(bool, int)
    def on_channel_toggled(self, is_checked, ch_id):
        """Save individual start/pause changes and apply them at a safe boundary."""
        try:
            all_settings = self._get_channel_settings_for_edit()
            ch_key = str(ch_id)
            if ch_key not in all_settings or not isinstance(all_settings.get(ch_key), dict):
                if ch_id in self.cards_by_ch_id:
                    self.cards_by_ch_id[ch_id].set_checked(False)
                return

            old_val = bool(all_settings[ch_key].get("is_enabled", False))
            new_val = bool(is_checked)
            if old_val == new_val:
                return

            channel = dict(all_settings[ch_key], ch_id=ch_id)
            if new_val:
                config_error = validate_channel_for_measurement(
                    channel, config.GLOBAL_SAFETY, int(config.RELAY_CONFIG.get("TOTAL_CHANNELS", 64)),
                )
                if config_error:
                    self.cards_by_ch_id[ch_id].set_checked(old_val)
                    QMessageBox.warning(self, "設定不完整", config_error)
                    return
                if bool(getattr(self.engine, "is_running", False)) and not self._validate_rline_before_start([channel]):
                    self.cards_by_ch_id[ch_id].set_checked(old_val)
                    return

            display_label = self._display_label_for_channel(ch_id, all_settings[ch_key], all_settings)
            action = "開始循環量測" if new_val else "暫停循環量測"
            running_note = ""
            if bool(getattr(self.engine, "is_running", False)):
                running_note = (
                    "\n\n儲存成功後於安全邊界生效；正在量測的通道會完成正逆掃及清理後暫停。"
                    "其他通道繼續量測。重新啟動此通道會排入下一個可用時段，不補測暫停期間。"
                )
            detail = (
                f"確定要將 {display_label} 設為「{action}」嗎？\n\n"
                "此操作只會改變此 Channel 是否納入循環量測排程；"
                "不會刪除設定、釋放 relay 或移除既有量測資料。"
                + running_note
            )
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle(f"確認{action}")
            msg.setText(f"請再次確認是否要{action}。")
            msg.setInformativeText(detail)
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            if msg.exec() != QMessageBox.StandardButton.Yes:
                if ch_id in self.cards_by_ch_id:
                    self.cards_by_ch_id[ch_id].set_checked(old_val)
                return

            all_settings[ch_key]["is_enabled"] = new_val
            channel = normalize_channel_record(
                dict(all_settings[ch_key], ch_id=ch_id), ch_id, assign_experiment_uid=True,
            )
            all_settings[ch_key] = channel
            self._pending_runtime_channel_changes[ch_id] = (channel, new_val)
            self._pending_channel_settings = copy.deepcopy(all_settings)
            if self._channel_settings_rollback is None:
                self._channel_settings_rollback = {}
            self._channel_settings_rollback.setdefault(ch_id, old_val)
            self._channel_settings_save_token = self.channel_settings_save_controller.request_save(
                config.CHANNEL_SETTINGS_FILE,
                all_settings,
            )
            self._channel_save_batches[self._channel_settings_save_token] = copy.deepcopy(self._pending_runtime_channel_changes)
            self._log_ui(
                f"[UI][CONFIG] queued debounced async save for {display_label} is_enabled={new_val}; "
                f"applies_at_safe_boundary={bool(getattr(self.engine, 'is_running', False))}"
            )

            if getattr(self.engine, "log_mgr", None):
                reason = f"使用者於主介面確認切換 {display_label} 循環量測狀態"
                self.engine.log_mgr.log_config_change(
                    f"CH{ch_id}:is_enabled",
                    old_val,
                    new_val,
                    reason,
                )
        except Exception as e:
            if ch_id in self.cards_by_ch_id:
                try:
                    all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
                    self.cards_by_ch_id[ch_id].set_checked(bool(all_settings.get(str(ch_id), {}).get("is_enabled", False)))
                except Exception:
                    pass
            print(f"儲存或刷新 channel {ch_id} 狀態失敗: {e}")

    @pyqtSlot(int)
    def on_channel_detail_clicked(self, ch_id):
        """Open settings for an existing logical channel."""
        dialog = ChannelSettingDialog(
            ch_id,
            self.engine,
            getattr(self.engine, "log_mgr", None),
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_and_refresh_all_channels()

    def _archive_channel_record(self, ch_id: int, settings: dict) -> None:
        """Append an ended logical channel to an archive JSON file.

        Args:
            ch_id: Internal numeric channel id.
            settings: Active channel settings before removal.

        The active channel is removed from `channel_settings.json`, but this
        archive preserves the final configuration for audit and troubleshooting.
        Scientific data files are never deleted by this UI action.
        """
        try:
            archive_path = config.BASE_CONFIG_DIR / "archived_channel_settings.json"
            archive_payload = config.load_json_file(archive_path)
            if not isinstance(archive_payload, dict):
                archive_payload = {}

            archive_payload.setdefault("archive_schema_version", 1)
            history = archive_payload.setdefault("ended_channels", [])
            if not isinstance(history, list):
                history = []
                archive_payload["ended_channels"] = history

            record = build_archive_record(ch_id, settings, final_status="ended_by_user")
            history.append(record)
            config.save_json_file(archive_path, archive_payload)
        except Exception as exc:
            self._log_ui(f"[UI] 無法寫入 channel 封存紀錄：{exc}", "warning")

    @pyqtSlot(int)
    def on_end_channel_requested(self, ch_id):
        """End an experiment channel and remove it from the active UI list."""
        if bool(getattr(self.engine, "is_running", False)):
            QMessageBox.warning(
                self,
                "量測進行中",
                "目前量測正在進行中。請先停止量測，待目前元件完成並安全停止後，再結束或移除 Channel。",
            )
            return

        all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        ch_key = str(ch_id)
        settings = all_settings.get(ch_key, {})
        if not isinstance(settings, dict) or not settings:
            QMessageBox.information(self, "Channel 不存在", "此 channel 已不存在或尚未完成設定。")
            self.load_and_refresh_all_channels()
            return

        display_label = self._display_label_for_channel(ch_id, settings, all_settings)
        device = str(settings.get("device_name") or "未命名元件")
        relay_pos = settings.get("relay_pos", "--")
        relay_neg = settings.get("relay_neg", "--")

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("結束實驗 / 移除 Channel")
        msg.setText(f"確定要結束 {display_label} / {device} 並從主畫面移除此 Channel 嗎？")
        msg.setInformativeText(
            f"此操作會釋放目前設定的 relay 路徑 +R{relay_pos} / -R{relay_neg}，"
            "讓後續新增 Channel 時可以再次使用或共用。\n\n"
            "既有量測 CSV、summary 與 log 不會被刪除；系統會把最後的 Channel 設定保存到 "
            "config/archived_channel_settings.json 以供回溯。"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        self._archive_channel_record(ch_id, settings)
        all_settings.pop(ch_key, None)
        if not config.save_json_file(config.CHANNEL_SETTINGS_FILE, all_settings):
            QMessageBox.critical(self, "移除失敗", "無法更新 channel_settings.json。")
            return

        # Active relay assignment source-of-truth is channel_settings.json.
        # hardware_map.json is retained as a default template / migration reference,
        # so ending an experiment must not mutate hardware_map automatically.
        self._log_ui(
            f"[UI] 使用者結束並移除 {display_label} / {device}，relay +R{relay_pos} / -R{relay_neg} 已從 active channel_settings 釋放；hardware_map template 未變更"
        )
        self.load_and_refresh_all_channels()

    @pyqtSlot()
    def on_hardware_init_clicked(self):
        self.request_init_hardware.emit()

    @pyqtSlot()
    def on_start_clicked(self):
        """Start a scan from checked dynamic channel cards."""
        if self._pending_channel_settings is not None:
            QMessageBox.information(self, "設定儲存中", "請等待通道設定儲存完成後再啟動。")
            return
        all_settings = self._get_channel_settings_for_edit()
        active_channels_data = []

        for card in self.cards:
            if card.is_checked():
                ch_settings = all_settings.get(str(card.channel_id), {})
                ch_settings = dict(ch_settings)
                ch_settings["ch_id"] = card.channel_id
                ch_settings["channel_label"] = self._display_label_for_channel(
                    card.channel_id,
                    ch_settings,
                    all_settings,
                )

                if not all(
                    [
                        ch_settings.get("user"),
                        ch_settings.get("project"),
                        ch_settings.get("device_name"),
                    ]
                ):
                    QMessageBox.warning(
                        self,
                        "設定不完整",
                        f"{ch_settings.get('channel_label', f'CH{card.channel_id:02d}')} 的使用者、專案或設備名稱未設定，無法開始量測。",
                    )
                    return

                config_error = validate_channel_for_measurement(
                    ch_settings, config.GLOBAL_SAFETY, int(config.RELAY_CONFIG.get("TOTAL_CHANNELS", 64)),
                )
                if config_error:
                    QMessageBox.warning(self, "設定錯誤", f"{ch_settings['channel_label']}: {config_error}")
                    return
                active_channels_data.append(ch_settings)

        if not active_channels_data:
            QMessageBox.information(
                self,
                "無可啟動 Channel",
                "目前沒有任何 Channel 被設定為「開始循環量測」。\n請先勾選至少一個 Channel 後再啟動全部循環量測。",
            )
            return

        if bool(getattr(self.engine, "is_running", False)):
            QMessageBox.information(self, "排程已在執行", "目前已在執行循環量測排程。")
            return

        if not self._validate_rline_before_start(active_channels_data):
            return

        proceed_overload, overload_info = self._confirm_scheduler_overload_if_needed(active_channels_data)
        if not proceed_overload:
            return
        for ch_data in active_channels_data:
            ch_data.update({
                "scheduler_overloaded": bool(overload_info.get("overloaded")),
                "scheduler_load_ratio": overload_info.get("load_ratio", ""),
                "scheduler_total_required_sec": overload_info.get("total_required_sec", ""),
                "scheduler_min_interval_sec": overload_info.get("min_interval_sec", ""),
                "scheduler_policy": config.get_scheduler_runtime_settings().get("mode", "flexible_catch_up"),
                "scheduler_max_allowed_delay_sec": config.get_scheduler_runtime_settings().get("max_allowed_delay_sec", 300),
            })

        if not self._confirm_start_all_cyclic_measurement(active_channels_data):
            self._log_ui("[UI] 使用者取消啟動全部循環量測", "warning")
            return

        run_session_id = generate_run_session_id()
        normalized_active_channels = []
        settings_changed_for_identity = False
        latest_settings = self._get_channel_settings_for_edit()
        for ch_data in active_channels_data:
            ch_id = ch_data.get("ch_id")
            normalized = normalize_channel_record(ch_data, ch_id, run_session_id=run_session_id, assign_experiment_uid=True)
            normalized_active_channels.append(normalized)
            key = str(ch_id)
            if key in latest_settings and isinstance(latest_settings.get(key), dict):
                persisted = dict(latest_settings[key])
                for identity_key in ("experiment_uid", "internal_ch_id", "channel_schema_version", "status"):
                    if normalized.get(identity_key) not in (None, "") and persisted.get(identity_key) != normalized.get(identity_key):
                        persisted[identity_key] = normalized.get(identity_key)
                        settings_changed_for_identity = True
                latest_settings[key] = persisted
        if settings_changed_for_identity:
            config.save_json_file(config.CHANNEL_SETTINGS_FILE, latest_settings)
            self._log_ui(f"[UI][IDENTITY] ensured experiment_uid for active channels; run_session_id={run_session_id}")
        active_channels_data = normalized_active_channels

        self._set_global_scheduler_status("準備啟動全部循環量測", "info")
        self._log_ui(
            f"[UI] 使用者確認啟動全部循環量測；本次啟用 logical channel 數: {len(active_channels_data)}"
        )

        self.notification_manager.set_pending_scan_request(active_channels_data)

        if hasattr(self.trend_chart, "set_active_scope"):
            try:
                self.trend_chart.set_active_scope(active_channels_data)
            except Exception:
                pass

        self.request_start_scan.emit(active_channels_data)

    @pyqtSlot()
    def on_stop_clicked(self):
        self._log_ui("[UI] 使用者按下停止全部循環量測")

        is_running = bool(getattr(self.engine, "is_running", False))
        if not is_running:
            self._log_ui("[UI] 使用者按下停止全部循環量測，但目前沒有進行中的量測", "warning")
            self._set_global_scheduler_status("停止中", "idle")
            QMessageBox.information(self, "提示", "目前沒有進行中的循環量測排程。")
            return

        if not self._confirm_graceful_stop():
            return

        self._set_global_scheduler_status("安全停止中 — 當前 Channel 完成後停止", "warning")
        self._log_ui(
            "[UI] 使用者確認停止全部循環量測；系統將於目前 Channel 正逆掃完成後停止"
        )
        self.request_stop_scan.emit()

    @pyqtSlot()
    def on_settings_clicked(self):
        dialog = SystemConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_and_refresh_all_channels()

            if hasattr(self.engine, "reload_config"):
                self.request_reload_config.emit()

            self.notification_manager.reload_settings()
            QMessageBox.information(self, "設定更新", "系統設定已更新並套用。")

    @pyqtSlot()
    def on_show_logs_clicked(self):
        self.log_window.show()
        try:
            self.log_window.raise_()
        except Exception:
            pass
        try:
            self.log_window.activateWindow()
        except Exception:
            pass

    @pyqtSlot()
    def on_show_iv_trend_clicked(self):
        self._show_and_focus_window(self.iv_monitor)
        self._show_and_focus_window(self.trend_chart)

    @pyqtSlot()
    def on_scan_started_show_windows(self):
        self._show_and_focus_window(self.iv_monitor)
        self._show_and_focus_window(self.trend_chart)

    @pyqtSlot(int)
    def on_channel_scan_pre_start(self, ch_id):
        """Show the current measuring channel in the global scheduler status."""
        try:
            all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
            settings = all_settings.get(str(ch_id), {})
            label = self._display_label_for_channel(int(ch_id), settings, all_settings)
            device = str((settings or {}).get("device_name") or "未命名")
            self._set_global_scheduler_status(f"量測中 — {label} / {device}", "info")
        except Exception:
            self._set_global_scheduler_status(f"量測中 — CH{int(ch_id):02d}", "info")

    @pyqtSlot(dict)
    def update_realtime_status(self, data):
        """Render worker status without overwriting successful card metrics."""
        ch_id = data.get("ch_id")
        if ch_id == -1:
            self._set_global_scheduler_status(data.get("message", ""), "info")
            return
        if ch_id is None or ch_id <= 0:
            return

        card = self.cards_by_ch_id.get(int(ch_id))
        if card is not None:
            message = data.get("message", "")
            if message == "已完成":
                return
            status_level = self._infer_status_level_from_message(message)
            card.update_status(message, status_level=status_level)

    @pyqtSlot(dict)
    def on_measurement_finished(self, results):
        """Display coherent canonical forward metrics, including validity/source."""
        ch_id = results.get("ch_id")
        if ch_id is None:
            return

        card = self.cards_by_ch_id.get(int(ch_id))
        if card is not None:
            voc, eff, source = forward_card_metrics(results)
            if source == "Invalid":
                card.update_status("Voc: — | Eff: —（無有效正掃數據）", status_level="warning")
            else:
                source_label = {"Corr": "正掃／校正", "Raw": "正掃／原始", "Legacy": "舊版正掃"}[source]
                status_text = f"Voc: {voc:.3f}V | Eff: {eff:.2f}%（{source_label}）"
                card.update_status(status_text, status_level="ok" if source == "Corr" else "warning")

        if bool(getattr(self.engine, "is_running", False)):
            self._set_global_scheduler_status("量測排程執行中，等待下一個 Channel", "ok")

    @pyqtSlot(dict)
    def on_scan_finished(self, finish_info):
        if hasattr(self.control_panel, "on_scan_finished"):
            try:
                self.control_panel.on_scan_finished()
            except Exception:
                pass

        finish_reason = str((finish_info or {}).get("finish_reason", "")).strip()
        if finish_reason == "stopped_after_current_channel":
            self._set_global_scheduler_status("停止中（已停止全部循環量測）", "idle")
        elif finish_reason in {"failed", "hardware_not_ready"}:
            self._set_global_scheduler_status("錯誤停止 — 請查看 Log", "error")
        elif finish_reason == "no_active_channels":
            self._set_global_scheduler_status("停止中（沒有可執行 Channel）", "warning")
        elif finish_reason == "completed":
            self._set_global_scheduler_status("停止中（排程已完成）", "idle")
        else:
            self._set_global_scheduler_status("停止中", "idle")

        trend_clear_scope = self._safe_slot(self.trend_chart, "clear_active_scope")
        if trend_clear_scope is not None:
            try:
                trend_clear_scope()
            except Exception:
                pass

        if finish_reason == "stopped_after_current_channel":
            self._log_ui("[UI] 掃描已依使用者要求於當前元件完成後停止")
        elif finish_reason == "completed":
            self._log_ui("[UI] 掃描已正常完成")
        elif finish_reason:
            self._log_ui(f"[UI] 掃描已結束（原因：{finish_reason}）", "warning")
        else:
            self._log_ui("[UI] 掃描已結束")

    @pyqtSlot()
    def on_exit_requested(self):
        """Handle the explicit safe-close button on the control panel."""
        if self.shutdown_manager is None:
            self.close()
            return

        mode = self.shutdown_manager.ask_shutdown_mode(self)
        if mode is None:
            self._log_ui("[UI] 使用者取消安全關閉程式", "warning")
            return

        if self.shutdown_manager.shutdown(mode=mode, parent=self):
            self._allow_close = True
            self.close()

    def closeEvent(self, event):
        """Prevent raw window close from bypassing the shutdown manager."""
        if not self._allow_close:
            event.ignore()
            self.on_exit_requested()
            return

        super().closeEvent(event)
