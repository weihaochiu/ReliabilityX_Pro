"""Qualified measurements with staged operator reports and verified cleanup (OI-054/057)."""

import time
import copy
from queue import SimpleQueue, Empty
import datetime
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

import config
from core.IV_parameter_analysis_utils import (
    calculate_iv_parameters, calculate_line_resistance, correct_iv_point, classify_solar_polarity,
    build_voltage_sweep,
)
from core.iv_curve_logger import IVCurveLogger
from core.summary_logger import SummaryLogger
from core.measurement_scheduler import MeasurementScheduler
from core.measurement_outcome import ChannelOutcome, validate_channel_for_measurement
from core.diagnostic_messages import build_diagnostic_report, STAGES
from driver.smu_driver import HardwareCommunicationError, HardwareReadError
from core.channel_identity import migrate_channel_settings_file, generate_run_session_id, normalize_channel_record


class MeasurementInterrupted(Exception):
    """Custom exception for immediate abort only."""
    pass


class MeasureEngine(QObject):
    """ReliabilityX Pro measurement engine."""

    hardware_status_updated = pyqtSignal(bool, bool, bool)
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal(dict)
    channel_status_updated = pyqtSignal(dict)
    channel_measurement_finished = pyqtSignal(dict)
    point_measured = pyqtSignal(dict)
    env_data_updated = pyqtSignal(object, object)
    channel_scan_pre_start = pyqtSignal(int)
    channel_scan_prepared = pyqtSignal(dict)
    line_resistance_result = pyqtSignal(dict)
    diagnostic_progress = pyqtSignal(dict)
    spot_check_result = pyqtSignal(dict)

    def __init__(self, smu_driver=None, relay_driver=None, chamber_driver=None, log_manager=None, **kwargs):
        super().__init__()
        self.smu = smu_driver
        self.relay = relay_driver
        self.chamber_driver = chamber_driver
        self.log_mgr = log_manager
        self.iv_curve_logger = IVCurveLogger()
        self.summary_logger = SummaryLogger()

        self.is_running = False
        self.stop_requested = False
        self.stop_request_reason = None
        self.stop_request_at = None
        self.last_finish_reason = None
        self.last_finished_channel_id = None
        self.completed_channel_count = 0
        self.total_channel_count = 0
        self.failed_channel_count = 0
        self.last_channel_failure = None
        self._channel_commands = SimpleQueue()
        self._run_session_id = ""

        self.ch_settings = {}
        self.cal_settings = {}
        self._active_channel_context = None
        self._relay_reconnect_during_measurement = False

        self._sanitize_runtime_paths()

    # ---------------------------------------------------------
    # Logging helpers
    # ---------------------------------------------------------
    def _log_info(self, message):
        if self.log_mgr:
            self.log_mgr.log_info(message)
        else:
            print(f"[INFO] {message}")

    def _log_warning(self, message):
        if self.log_mgr:
            self.log_mgr.log_warning(message)
        else:
            print(f"[WARNING] {message}")

    def _log_error(self, message, exc_info=False):
        if self.log_mgr:
            try:
                self.log_mgr.log_error(message, exc_info=exc_info)
            except TypeError:
                self.log_mgr.log_error(message)
        else:
            print(f"[ERROR] {message}")

    def _log_scan(self, message, level="info"):
        text = f"[SCAN] {message}"
        if level == "warning":
            self._log_warning(text)
        elif level == "error":
            self._log_error(text)
        else:
            self._log_info(text)

    # ---------------------------------------------------------
    # Startup path sanitation
    # ---------------------------------------------------------
    def _sanitize_runtime_paths(self):
        try:
            sanitized = config.sanitize_user_paths()
            self._log_info(
                f"[PATH] 已檢查儲存路徑 | "
                f"data_dir={sanitized.get('data_dir')} | "
                f"log_dir={sanitized.get('log_dir')}"
            )
        except Exception as exc:
            self._log_warning(f"[PATH] 路徑清洗失敗，將使用預設路徑: {exc}")

    # ---------------------------------------------------------
    # Generic helpers
    # ---------------------------------------------------------
    def _interruptible_sleep(self, duration_s):
        end_time = time.time() + duration_s
        while time.time() < end_time:
            if not self.is_running:
                raise MeasurementInterrupted("Measurement stopped immediately.")
            time.sleep(0.05)

    def _read_vi_before_reset(self):
        if not self.smu:
            return None
        return self.smu.read_vi()

    def _relay_reset_all(self, settle_sec=0.1):
        if not self.relay or not self._probe_relay_connected():
            raise IOError("Relay 未連線，無法執行 reset_all。")
        if not self.relay.reset_all():
            raise IOError("Relay reset_all() 失敗。")
        if settle_sec > 0:
            self._interruptible_sleep(settle_sec)

    def _prepare_channel_path(self, ch_id, relay_pos, relay_neg, settle_sec=0.3):
        """Establish exactly one pair after verified output OFF.

        Args:
            ch_id: Logical channel for diagnostics.
            relay_pos: Physical positive relay ID.
            relay_neg: Physical negative relay ID.
            settle_sec: Interruptible settling delay.

        Raises:
            IOError: Switching or full controller-state verification failed.
        """
        self.smu.set_output_verified(False)
        self._relay_reset_all(settle_sec=0.1)

        res1 = self.relay.switch_on(relay_pos)
        res2 = self.relay.switch_on(relay_neg)
        if not (res1 and res2):
            raise IOError(
                f"Relay 切換失敗，無法建立 CH{ch_id:02d} 的獨立量測路徑 "
                f"(pins {relay_pos}, {relay_neg})"
            )

        if not self.relay.verify_state({relay_pos, relay_neg}):
            raise IOError(f"CH{ch_id:02d} Relay readall 與選定 pair {relay_pos}/{relay_neg} 不符")

        if settle_sec > 0:
            self._interruptible_sleep(settle_sec)

    def _cleanup_channel_path(self, settle_sec=0.05):
        self._relay_reset_all(settle_sec=settle_sec)

    def _reset_scan_state(self):
        """Reset per-run completion diagnostics and discard stale UI requests."""
        self.stop_requested = False
        self.stop_request_reason = None
        self.stop_request_at = None
        self.last_finish_reason = None
        self.last_finished_channel_id = None
        self.completed_channel_count = 0
        self.total_channel_count = 0
        self.failed_channel_count = 0
        self.last_channel_failure = None
        while not self._channel_commands.empty():
            self._channel_commands.get_nowait()

    def _build_finish_info(self):
        """Build the scan result including classified channel failures."""
        return {
            "finish_reason": self.last_finish_reason or "",
            "finish_time": datetime.datetime.now(),
            "last_finished_channel_id": self.last_finished_channel_id,
            "stop_requested": self.stop_requested,
            "stop_request_reason": self.stop_request_reason,
            "completed_channel_count": self.completed_channel_count,
            "failed_channel_count": self.failed_channel_count,
            "last_channel_failure": self.last_channel_failure,
            "remaining_channel_count": max(0, self.total_channel_count - self.completed_channel_count),
        }

    def queue_channel_enabled(self, channel, enabled):
        """Enqueue a GUI request without hardware IO or worker-state mutation.

        Args:
            channel: Saved channel settings, copied before crossing threads.
            enabled: Requested participation in the current scheduler.

        Returns:
            Whether a running scan accepted the request for boundary handling.
        """
        if not self.is_running:
            return False
        self._channel_commands.put((copy.deepcopy(channel), bool(enabled)))
        return True

    def _apply_channel_commands(self, scheduler):
        """Consume saved GUI toggles only between complete channel attempts."""
        changed = False
        while True:
            try:
                channel, enabled = self._channel_commands.get_nowait()
            except Empty:
                break
            if channel is None:
                self.stop_scan_cycle()
                continue
            channel = normalize_channel_record(
                channel, channel["ch_id"], run_session_id=self._run_session_id,
                assign_experiment_uid=True,
            )
            scheduler.set_channel_enabled(channel, enabled, datetime.datetime.now())
            self.channel_status_updated.emit({
                "ch_id": channel["ch_id"],
                "message": "已加入排程，等待量測" if enabled else "已暫停循環量測",
            })
            self._log_scan(f"{self._channel_label(channel)} boundary toggle applied | enabled={enabled}")
            changed = True
        if changed:
            self.total_channel_count = len(scheduler.items)
            self._save_schedule_state(scheduler, status="running")

    def queue_graceful_stop(self):
        """Enqueue stop from any thread; perform it at a channel boundary."""
        if self.is_running:
            self._channel_commands.put((None, False))

    # ---------------------------------------------------------
    # Hardware status / health check helpers
    # ---------------------------------------------------------
    def _probe_smu_connected(self):
        if not self.smu:
            return False
        if not getattr(self.smu, "is_connected", False):
            return False
        try:
            if hasattr(self.smu, "get_idn"):
                idn = self.smu.get_idn()
                return isinstance(idn, str) and bool(idn.strip())
            return True
        except Exception as e:
            self._log_warning(f"SMU 狀態驗證失敗，視為未連線: {e}")
            try:
                self.smu.close()
            except Exception:
                pass
            return False

    def _probe_relay_connected(self):
        if not self.relay:
            return False
        if not getattr(self.relay, "is_connected", False):
            return False
        ser = getattr(self.relay, "ser", None)
        if ser is None:
            return False
        try:
            return bool(ser.is_open)
        except Exception:
            return False

    def _probe_chamber_connected(self):
        """Return True only when chamber telemetry is readable.

        Serial open alone is not enough for scientific readiness because USB-RS485
        can be open while the controller address, FCS, A/B wiring, or remote
        communication setting is wrong.
        """
        if not self.chamber_driver:
            return False
        try:
            is_open = self.chamber_driver.is_connected() if callable(getattr(self.chamber_driver, "is_connected", None)) else False
            if not is_open:
                return False
            status = self.chamber_driver.read_status()
            if status:
                self.env_data_updated.emit(status.get("temp_pv"), status.get("hum_pv"))
                return True
            self.env_data_updated.emit(None, None)
            return False
        except Exception as exc:
            self._log_warning(f"Chamber telemetry probe failed: {exc}")
            self.env_data_updated.emit(None, None)
            return False

    def _connect_smu_if_needed(self):
        if not self.smu:
            self._log_warning("SMU driver 不存在。")
            return False

        if self._probe_smu_connected():
            self._log_info("SMU 已連線，略過重連。")
            return True

        self._log_info("SMU 未連線，開始重新連線...")
        try:
            ok = bool(self.smu.connect())
        except Exception as e:
            self._log_error(f"SMU 重連失敗: {e}")
            ok = False

        if ok:
            self._log_info("SMU 連線: 成功")
        else:
            self._log_error("SMU 連線: 失敗")
        return ok

    def _connect_relay_if_needed(self, *, allow_reset_all=True):
        """Reconnect relay with active-measurement safety guard.

        During an active IV scan we must not blindly call reset_all after a
        reconnect because that can physically cut the current measurement path.
        The conservative policy is to abort/stop the current channel and require
        a safe boundary rather than trying to restore an uncertain relay state.
        """
        if not self.relay:
            self._log_warning("Relay driver 不存在。")
            return False

        if self._probe_relay_connected():
            self._log_info("Relay 已連線，略過重連。")
            return True

        active_measurement = bool(self.is_running or self._active_channel_context)
        self._log_info("Relay 未連線，開始重新連線...")
        try:
            ok = bool(self.relay.auto_scan())
            if ok and allow_reset_all and not active_measurement:
                try:
                    self.relay.reset_all()
                except Exception as e:
                    self._log_warning(f"Relay 已連線，但 reset_all 失敗: {e}")
            elif ok and active_measurement:
                self._relay_reconnect_during_measurement = True
                self.stop_requested = True
                self.stop_request_reason = "relay_reconnected_during_active_measurement"
                self.stop_request_at = datetime.datetime.now()
                self._log_error(
                    "Relay 在 active measurement 期間重新連線；已禁止自動 reset_all，"
                    "目前 channel 將標記為失敗並於安全邊界停止，以避免量測路徑被硬切斷。"
                )
                return False
        except Exception as e:
            self._log_error(f"Relay 重連失敗: {e}")
            ok = False

        if ok:
            self._log_info("Relay 連線: 成功")
        else:
            self._log_warning("Relay 連線: 失敗")
        return ok

    def _connect_chamber_if_needed(self):
        """Open chamber serial port from config and require telemetry readiness."""
        if not self.chamber_driver:
            return False

        if self._probe_chamber_connected():
            self._log_info("Chamber telemetry 已連線，略過重連。")
            return True

        connect_func = getattr(self.chamber_driver, "connect", None)
        if not callable(connect_func):
            return False

        chamber_conf = {}
        try:
            chamber_conf = config.load_config_settings().get("CHAMBER_CONFIG", {}) or {}
        except Exception as exc:
            self._log_warning(f"Chamber 設定讀取失敗: {exc}")
        port = str(chamber_conf.get("PORT", "") or "").strip()
        baudrate = int(chamber_conf.get("BAUDRATE", 9600) or 9600)
        station_id = int(chamber_conf.get("ID", 1) or 1)
        if not port:
            self._log_warning("Chamber 未設定 COM port；略過自動重連。")
            self.env_data_updated.emit(None, None)
            return False

        self._log_info(f"Chamber 未就緒，開始重連: port={port} | baud={baudrate} | id={station_id} | serial=8E1")
        try:
            self.chamber_driver.station_id = str(station_id).zfill(2)
            serial_ok = bool(connect_func(port, baudrate=baudrate))
            if not serial_ok:
                self._log_warning("Chamber serial port 開啟失敗。")
                self.env_data_updated.emit(None, None)
                return False
            telemetry_ok, status, diagnostic = self.chamber_driver.test_telemetry(probe_all=True)
            if telemetry_ok and status:
                self._log_info(
                    f"Chamber telemetry OK: {status.get('temp_pv'):.1f} °C / {status.get('hum_pv'):.1f} % | "
                    f"FCS={getattr(self.chamber_driver, 'fcs_mode', '-')}"
                )
                self.env_data_updated.emit(status.get("temp_pv"), status.get("hum_pv"))
                return True
            self._log_warning("Chamber serial port 已開啟，但 telemetry 讀取失敗。")
            self._log_warning(diagnostic)
            self.env_data_updated.emit(None, None)
            return False
        except Exception as e:
            self._log_error(f"Chamber 重連/telemetry 測試失敗: {e}")
            self.env_data_updated.emit(None, None)
            return False

    def _emit_current_hardware_status(self):
        smu_ok = self._probe_smu_connected()
        relay_ok = self._probe_relay_connected()
        chamber_ok = self._probe_chamber_connected()
        self.hardware_status_updated.emit(smu_ok, relay_ok, chamber_ok)
        return smu_ok, relay_ok, chamber_ok

    @pyqtSlot()
    def poll_chamber_once(self):
        """Poll one chamber telemetry sample for the main-window environment panel."""
        if not self.chamber_driver:
            self.env_data_updated.emit(None, None)
            self.hardware_status_updated.emit(self._probe_smu_connected(), self._probe_relay_connected(), False)
            return
        try:
            is_open = self.chamber_driver.is_connected() if callable(getattr(self.chamber_driver, "is_connected", None)) else False
            if not is_open:
                self.env_data_updated.emit(None, None)
                self.hardware_status_updated.emit(self._probe_smu_connected(), self._probe_relay_connected(), False)
                return
            status = self.chamber_driver.read_status()
            if status:
                self.env_data_updated.emit(status.get("temp_pv"), status.get("hum_pv"))
                self.hardware_status_updated.emit(self._probe_smu_connected(), self._probe_relay_connected(), True)
            else:
                self.env_data_updated.emit(None, None)
                self.hardware_status_updated.emit(self._probe_smu_connected(), self._probe_relay_connected(), False)
        except Exception as exc:
            self._log_warning(f"Chamber polling failed: {exc}")
            self.env_data_updated.emit(None, None)
            self.hardware_status_updated.emit(self._probe_smu_connected(), self._probe_relay_connected(), False)

    # ---------------------------------------------------------
    # Hardware init
    # ---------------------------------------------------------
    @pyqtSlot()
    def initialize_hardware(self):
        if self.is_running:
            self._log_warning("量測進行中，忽略重新偵測硬體命令。")
            self._emit_current_hardware_status()
            return

        self._log_info("初始化硬體中（僅重連未連線設備）...")

        smu_connected = self._connect_smu_if_needed()
        relay_connected = self._connect_relay_if_needed()
        chamber_connected = self._connect_chamber_if_needed()

        self.hardware_status_updated.emit(smu_connected, relay_connected, chamber_connected)

    def is_hardware_ready(self):
        smu_ok = self._probe_smu_connected()
        relay_ok = self._probe_relay_connected()

        if smu_ok and relay_ok:
            return True

        if not smu_ok:
            self._log_error("硬體未就緒: SMU 未連線")
        if not relay_ok:
            self._log_error("硬體未就緒: Relay 未連線")
        return False

    def load_configs(self):
        try:
            self.ch_settings, _ = migrate_channel_settings_file(config.CHANNEL_SETTINGS_FILE, save=True)
            self.cal_settings = config.load_json_file(config.CALIBRATION_SETTINGS_FILE)
            config.HARDWARE_MAP = config.load_hardware_map()

            config.get_safe_data_dir()
            config.get_safe_log_dir()
            return True
        except Exception as e:
            self._log_error(f"載入設定失敗: {e}")
            return False

    # ---------------------------------------------------------
    # Main scan cycle
    # ---------------------------------------------------------
    def _format_dt(self, value):
        if isinstance(value, datetime.datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value) if value else ""

    def _channel_label(self, ch_data):
        raw_id = ch_data.get("ch_id")
        try:
            fallback = f"CH{int(raw_id):02d}"
        except Exception:
            fallback = f"CH{raw_id}"
        return ch_data.get("channel_label") or fallback

    def _sleep_until_next_due(self, scheduler):
        """Sleep in short slices until the next channel is due."""
        seconds = scheduler.next_sleep_seconds(datetime.datetime.now())
        if seconds is None:
            return False
        if seconds <= 0:
            return True
        self.channel_status_updated.emit(
            {"ch_id": -1, "message": f"等待下一個 channel 到期 ({seconds:.0f}s)..."}
        )
        self._interruptible_sleep(min(seconds, 1.0))
        return True

    def _load_schedule_state(self):
        try:
            state = config.load_json_file(getattr(config, "RUNTIME_SCHEDULE_STATE_FILE", config.BASE_CONFIG_DIR / "runtime_schedule_state.json"))
            return state if isinstance(state, dict) else {}
        except Exception as exc:
            self._log_warning(f"[SCHED] 無法載入 runtime schedule state，將重新建立排程: {exc}")
            return {}

    def _save_schedule_state(self, scheduler, *, status="running"):
        """Persist schedule anchors and the last classified failure."""
        try:
            path = getattr(config, "RUNTIME_SCHEDULE_STATE_FILE", config.BASE_CONFIG_DIR / "runtime_schedule_state.json")
            payload = scheduler.to_state_dict(status=status) if hasattr(scheduler, "to_state_dict") else {}
            payload["last_channel_failure"] = self.last_channel_failure
            payload["completed_channel_count"] = self.completed_channel_count
            payload["failed_channel_count"] = self.failed_channel_count
            if not config.save_json_file(path, payload):
                self._log_error(f"[SCHED] runtime state write failed | path={path} | status={status}")
        except Exception as exc:
            self._log_warning(f"[SCHED] 無法儲存 runtime schedule state: {exc}")

    def _estimate_channel_duration_sec(self, ch_data):
        try:
            v_start = float(ch_data.get("v_start", 0.0))
            v_stop = float(ch_data.get("v_stop", 0.0))
            v_step = abs(float(ch_data.get("v_step", 0.02) or 0.02))
            delay_sec = max(0.0, float(ch_data.get("delay_time", 50) or 50) / 1000.0)
            point_count = int(abs(v_stop - v_start) / v_step) + 1 if v_step > 0 else 1
            # forward + reverse; include relay settling, SMU settling/readback overhead and analysis/logging margin
            return max(1.0, (point_count * 2 * (delay_sec + 0.12)) + 1.0)
        except Exception:
            return 10.0

    def _check_scheduler_overload(self, active_channels_data):
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
                pass
        if not intervals:
            return {"overloaded": False, "total_required_sec": total_required}
        min_interval = min(intervals)
        overloaded = total_required > min_interval
        info = {
            "overloaded": overloaded,
            "total_required_sec": total_required,
            "min_interval_sec": min_interval,
            "active_channel_count": len(active),
            "load_ratio": (total_required / min_interval) if min_interval > 0 else 0,
        }
        if overloaded:
            self._log_scan(
                "排程超載警告："
                f"預估單輪量測時間 {total_required:.1f}s > 最短量測間隔 {min_interval:.1f}s；"
                "系統將排隊延遲量測並完整記錄 delay/conflict metadata。"
                "請考慮增加 interval、減少 active channels、放大 V step 或縮短 delay_time。",
                level="warning",
            )
        return info


    def _record_scheduler_skip(self, ch_data, skip_meta, overload_meta, reason):
        """Persist a scheduler skip occurrence for traceability without IV data."""
        record = dict(ch_data or {})
        record.update(skip_meta or {})
        record.update(overload_meta or {})
        record["scheduler_skip_reason"] = reason
        record["scan_dir"] = "SKIPPED"
        record["scan_direction"] = "SKIPPED"
        record.setdefault("start_time", (skip_meta or {}).get("actual_start_time") or datetime.datetime.now())
        record.setdefault("actual_end_time", (skip_meta or {}).get("actual_end_time") or record.get("start_time"))
        params = ["Voc", "Isc", "Jsc", "FF", "PCE", "Rs", "Rsh", "Pmpp", "Vmpp", "Impp", "Jmpp"]
        for suffix in ["F_Raw", "R_Raw", "F_Corr", "R_Corr"]:
            for param in params:
                record.setdefault(f"{param}_{suffix}", np.nan)
        record.setdefault("HI_Raw", np.nan)
        record.setdefault("HI_Corr", np.nan)
        try:
            self.summary_logger.update_summary_report(record)
        except Exception as exc:
            self._log_warning(f"[SCHED] skipped occurrence summary write failed: {exc}")
        try:
            self.channel_status_updated.emit({
                "ch_id": record.get("ch_id", -1),
                "status": "skipped",
                "message": f"排程延遲超過容忍值，已跳過本輪：{reason}",
            })
        except Exception:
            pass

    @pyqtSlot(list)
    def start_scan_cycle(self, active_channels_data):
        """Start the measurement scheduler.

        The previous implementation completed all active channels and then used
        the first channel's `interval_min` as the whole-round wait time. This
        implementation keeps one `next_due` timestamp per logical channel, so
        every channel can run at its own interval while still measuring one
        relay path at a time.
        """
        if self.is_running:
            self._log_warning("量測已在執行中，忽略重複啟動。")
            return

        self._reset_scan_state()
        run_session_id = ""
        for item in active_channels_data or []:
            if isinstance(item, dict) and item.get("run_session_id"):
                run_session_id = str(item.get("run_session_id"))
                break
        if not run_session_id:
            run_session_id = generate_run_session_id()
        self._run_session_id = run_session_id
        active_channels_data = [
            normalize_channel_record(item, item.get("ch_id"), run_session_id=run_session_id, assign_experiment_uid=True)
            for item in (active_channels_data or [])
            if isinstance(item, dict)
        ]
        self.total_channel_count = len(active_channels_data or [])

        if not self.is_hardware_ready() or not self.load_configs():
            self.last_finish_reason = "hardware_not_ready"
            self.scan_finished.emit(self._build_finish_info())
            return

        previous_state = self._load_schedule_state()
        scheduler_policy = config.get_scheduler_runtime_settings()
        scheduler = MeasurementScheduler(active_channels_data, previous_state=previous_state, scheduler_policy=scheduler_policy)
        overload_info = self._check_scheduler_overload(active_channels_data)
        self._save_schedule_state(scheduler, status="starting")
        if not scheduler.items:
            self.last_finish_reason = "no_active_channels"
            self.scan_finished.emit(self._build_finish_info())
            return

        self.is_running = True
        self.scan_started.emit()
        self._log_scan("per-channel 排程量測已啟動（單一 SMU/Relay 資源，衝突時排隊；next_due 以原 scheduled due time + interval 推進）...")

        try:
            if self.relay:
                self.relay.prepare_for_measurement()

            while self.is_running:
                self._apply_channel_commands(scheduler)
                if self.stop_requested:
                    self.last_finish_reason = "stopped_after_current_channel"
                    self._log_scan("已到安全停止邊界；不再進入下一顆元件")
                    break

                now = datetime.datetime.now()
                due_items = scheduler.due_items(now)

                if not due_items:
                    if not scheduler.has_active():
                        if any(item.paused for item in scheduler.items):
                            self.channel_status_updated.emit({"ch_id": -1, "message": "全部通道已暫停，等待個別啟動"})
                            self._interruptible_sleep(0.2)
                            continue
                        self.last_finish_reason = "completed"
                        self._log_scan("所有 one-shot channel 已完成")
                        break
                    self._sleep_until_next_due(scheduler)
                    continue

                conflict_group_size = len(due_items)
                conflict_labels = [item.label for item in due_items]
                if conflict_group_size > 1:
                    self._log_scan(
                        "量測時間衝突："
                        f"{conflict_group_size} 個 channel 同時/逾期到期，將依 due time、priority、interval、建立順序排隊。"
                        f" Queue={', '.join(conflict_labels)}",
                        level="warning",
                    )

                for queue_idx, item in enumerate(due_items, start=1):
                    self._apply_channel_commands(scheduler)
                    if not item.active:
                        continue
                    if self.stop_requested:
                        self.last_finish_reason = "stopped_after_current_channel"
                        self._log_scan("已到安全停止邊界；不再進入下一顆元件")
                        break

                    ch_data = item.channel
                    ch_id = ch_data.get("ch_id")
                    start_time = datetime.datetime.now()
                    schedule_meta = item.mark_started(
                        start_time,
                        conflict_group_size=conflict_group_size,
                        queue_position=queue_idx,
                        conflict_peer_labels=conflict_labels,
                    )
                    overload_meta = {
                        "scheduler_overloaded": bool(overload_info.get("overloaded")),
                        "scheduler_load_ratio": overload_info.get("load_ratio", ""),
                        "scheduler_total_required_sec": overload_info.get("total_required_sec", ""),
                        "scheduler_min_interval_sec": overload_info.get("min_interval_sec", ""),
                        "scheduler_policy": scheduler.policy_mode,
                        "scheduler_max_allowed_delay_sec": scheduler.max_allowed_delay_sec,
                    }

                    if scheduler.should_skip_due_item(item, start_time):
                        reason = (
                            f"strict_skip_delay_exceeded: delay={max(0.0, (start_time - item.next_due).total_seconds()):.1f}s "
                            f"> max_allowed_delay={scheduler.max_allowed_delay_sec}s"
                        )
                        skip_meta = item.mark_skipped(
                            start_time,
                            reason=reason,
                            conflict_group_size=conflict_group_size,
                            queue_position=queue_idx,
                            conflict_peer_labels=conflict_labels,
                        )
                        self._log_scan(
                            f"{item.label} 本輪已跳過 | scheduled={self._format_dt(skip_meta.get('scheduled_time'))} | "
                            f"actual={self._format_dt(start_time)} | {reason} | next_due={self._format_dt(item.next_due)}",
                            level="warning",
                        )
                        self._record_scheduler_skip(ch_data, skip_meta, overload_meta, reason)
                        self._save_schedule_state(scheduler, status="running")
                        continue

                    ch_data_for_measurement = {**ch_data, **schedule_meta, **overload_meta}

                    self._log_scan(
                        f"{item.label} 到期，開始量測 | "
                        f"scheduled={self._format_dt(schedule_meta.get('scheduled_time'))} | "
                        f"actual_start={self._format_dt(start_time)} | "
                        f"delay={schedule_meta.get('schedule_delay_sec', 0):.1f}s | "
                        f"queue={queue_idx}/{conflict_group_size} | "
                        f"conflict={schedule_meta.get('conflict_flag')}"
                    )

                    outcome = self.measure_single_channel(ch_data_for_measurement, start_time)
                    if not outcome.succeeded:
                        self.failed_channel_count += 1
                        self.last_channel_failure = outcome.to_dict()
                        self.last_finish_reason = "failed"
                        self._log_scan(
                            f"{item.label} 量測失敗，停止全部排程 | status={outcome.status} | "
                            f"reason={outcome.error} | cleanup_errors={outcome.cleanup_errors}", level="error",
                        )
                        break
                    end_time = datetime.datetime.now()
                    item.mark_completed(end_time)
                    self.last_finished_channel_id = ch_id
                    self.completed_channel_count += 1
                    self._save_schedule_state(scheduler, status="running")

                    self._log_scan(
                        f"{item.label} 量測完成 | "
                        f"actual_end={self._format_dt(end_time)} | "
                        f"next_due={self._format_dt(item.next_due) if item.active else 'one-shot completed'} | "
                        "next_due_rule=scheduled_due_plus_interval"
                    )

                    if self.stop_requested:
                        self.last_finish_reason = "stopped_after_current_channel"
                        self._log_scan(
                            f"CH{int(ch_id):02d} 已完成當前正逆掃；依停止請求不再進入下一顆"
                        )
                        break

                self._apply_channel_commands(scheduler)
                if self.stop_requested and self.last_finish_reason != "failed":
                    self.last_finish_reason = "stopped_after_current_channel"
                if self.last_finish_reason in {"stopped_after_current_channel", "failed"}:
                    break

                if not scheduler.has_active() and not any(item.paused for item in scheduler.items):
                    self.last_finish_reason = "completed"
                    self._log_scan("本次排程內所有 one-shot channel 已完成")
                    break

        except MeasurementInterrupted:
            self.last_finish_reason = "interrupted_immediate"
            self._log_warning("[SCAN] 掃描被立即中斷。")
        except Exception as e:
            self.last_finish_reason = "failed"
            self._log_error(f"[SCAN] 量測引擎發生未預期錯誤: {e}", exc_info=True)
        finally:
            if self.smu:
                try:
                    self.smu.set_output_verified(False)
                except Exception as exc:
                    self.last_finish_reason = "failed"
                    self._log_error(f"[SCAN cleanup] SMU OFF 未確認: {exc}", exc_info=True)

            if self.relay and self._probe_relay_connected():
                try:
                    self._interruptible_sleep(0.1)
                except Exception:
                    pass
                try:
                    if not self.relay.reset_all():
                        raise IOError("Relay all-off 讀回失敗")
                except Exception as exc:
                    self.last_finish_reason = "failed"
                    self._log_error(f"[SCAN cleanup] Relay 未確認: {exc}", exc_info=True)

            self.is_running = False

            if not self.last_finish_reason:
                self.last_finish_reason = "completed"

            if self.last_finish_reason == "stopped_after_current_channel":
                self._log_scan("掃描循環已停止（原因：使用者要求於當前元件完成後停止）")
            elif self.last_finish_reason == "completed":
                self._log_scan("掃描循環已正常完成")
            elif self.last_finish_reason == "failed":
                self._log_scan("掃描循環異常結束", level="error")
            else:
                self._log_scan(f"掃描循環已結束（原因：{self.last_finish_reason}）", level="warning")

            self._log_scan("掃描循環已停止；已執行硬體安全清理，請依錯誤紀錄確認設備狀態。")
            try:
                if 'scheduler' in locals():
                    self._save_schedule_state(scheduler, status=self.last_finish_reason or "finished")
            except Exception:
                pass

            finish_info = self._build_finish_info()
            self.scan_finished.emit(finish_info)
            self._emit_current_hardware_status()

    @pyqtSlot()
    def stop_scan_cycle(self):
        if not self.is_running:
            self._log_scan("收到停止請求，但目前沒有進行中的量測", "warning")
            return

        if self.stop_requested:
            self._log_scan("停止請求已存在，忽略重複停止命令", "warning")
            return

        self.stop_requested = True
        self.stop_request_reason = "user_requested_after_current_channel"
        self.stop_request_at = datetime.datetime.now()
        self._log_scan("收到停止請求；將於目前通道正逆掃完成後停止")

    # ---------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------
    def _report_diagnostic_stage(self, operation, stage):
        """Emit attempted stage, not a success claim, through a queued GUI signal.

        Args:
            operation: Diagnostic operation name.
            stage: Stable stage identifier.
        """
        message = STAGES.get(stage, stage)
        self._log_info(f"[DIAGNOSTIC STAGE] operation={operation} stage={stage} {message}")
        self.diagnostic_progress.emit({"request_id": getattr(self, "_active_diagnostic_request_id", None),
                                       "operation": operation, "stage": stage, "message": message})

    def measure_line_resistance(self, pos_pin, neg_pin):
        """Measure relay-pair line resistance with current-source diagnostics.

        Args:
            pos_pin: Physical SMU+ relay pin.
            neg_pin: Physical SMU- relay pin.

        Returns:
            dict | None: Resistance and raw diagnostic values when successful;
            otherwise None and ``_last_line_resistance_error`` is set.
        """
        self._last_line_resistance_error = ""
        self._last_line_resistance_report = None
        if self.is_running:
            self._last_line_resistance_error = "量測進行中，拒絕重入線阻診斷。"
            self._log_error(self._last_line_resistance_error)
            return None
        if not self.is_hardware_ready():
            self._last_line_resistance_error = "硬體未就緒，無法量測線路電阻。"
            self._log_error(self._last_line_resistance_error)
            return None

        total = int(config.RELAY_CONFIG.get("TOTAL_CHANNELS", 64))
        if pos_pin == neg_pin or not (0 <= pos_pin < total and 0 <= neg_pin < total):
            self._last_line_resistance_error = f"無效 Relay pair: {pos_pin}/{neg_pin} (0..{total - 1})"
            self._log_error(self._last_line_resistance_error)
            return None
        self._log_info(f"[線阻診斷] 開始量測 - 使用實體接腳 SMU+: {pos_pin:02d}, SMU-: {neg_pin:02d}")
        self.is_running = True
        result = None
        cleanup_errors = []
        failure = None
        stage = "smu_off"
        facts = {"relay_pos": pos_pin, "relay_neg": neg_pin, "relay_pair_confirmed": False,
                 "output_attempted": False, "output_on_confirmed": False, "sample_acquired": False,
                 "resource": getattr(getattr(self.smu, "device", None), "resource_name", "unknown"),
                 "idn": getattr(self.smu, "idn", "unknown"),
                 "relay_port": getattr(getattr(self.relay, "ser", None), "port", "unknown"),
                 "source_current_A": 0.01, "voltage_limit_V": 1.5}

        try:
            self._report_diagnostic_stage("線阻量測", stage)
            self.smu.set_output_verified(False)
            stage = "relay_reset"
            self._report_diagnostic_stage("線阻量測", stage)
            if not self.relay.reset_all():
                raise IOError("Relay 初始 all-off 未確認，禁止量測")
            self._interruptible_sleep(0.2)

            stage = "relay_pair"
            self._report_diagnostic_stage("線阻量測", stage)
            res1 = self.relay.switch_on(pos_pin)
            res2 = self.relay.switch_on(neg_pin)
            if not (res1 and res2):
                raise IOError("Relay 切換失敗，請檢查硬體連線。")
            if not self.relay.verify_state({pos_pin, neg_pin}):
                raise IOError("Relay 完整狀態讀回不符選定 pair，禁止量測")
            facts["relay_pair_confirmed"] = True

            source_current = 0.01
            voltage_limit = 1.5
            stage = "smu_setup"
            self._report_diagnostic_stage("線阻量測", stage)
            self.smu.configure_current_source_verified(current=source_current, v_limit=voltage_limit)
            stage = "smu_on"
            self._report_diagnostic_stage("線阻量測", stage)
            facts["output_attempted"] = True
            self.smu.set_output_verified(True)
            facts["output_on_confirmed"] = True
            self._interruptible_sleep(0.5)

            stage = "sample"
            self._report_diagnostic_stage("線阻量測", stage)
            v_meas, i_meas = self.smu.read_vi()
            facts.update(sample_acquired=True, measured_voltage_V=v_meas, measured_current_A=i_meas)
            stage = "compliance"
            self._report_diagnostic_stage("線阻量測", stage)
            compliance = self.smu.read_voltage_compliance()
            facts["voltage_compliance"] = compliance
            self._log_info(f"[R-line SAMPLE] relay={pos_pin}/{neg_pin} V={v_meas!r} V I={i_meas!r} A I_set={source_current} A V_limit={voltage_limit} V compliance={compliance!r}")
            stage = "qualification"
            self._report_diagnostic_stage("線阻量測", stage)
            resistance = calculate_line_resistance(v_meas, i_meas, source_current, voltage_limit, compliance)
            result = {
                "resistance": float(resistance),
                "measured_voltage_V": float(v_meas),
                "measured_current_A": float(i_meas),
                "source_current_A": float(source_current),
                "voltage_limit_V": float(voltage_limit),
                "voltage_compliance": compliance,
                "validation_version": 2,
            }

        except (IOError, ValueError, MeasurementInterrupted) as e:
            failure = e
            self._last_line_resistance_error = str(e)
            self._log_error(f"線路電阻量測失敗: {e}", exc_info=True)
        except Exception as e:
            failure = e
            self._last_line_resistance_error = str(e)
            self._log_error(f"線路電阻量測發生未知錯誤: {e}", exc_info=True)
        finally:
            facts["cleanup_attempted"] = True
            facts["smu_off_confirmed"] = facts["relay_off_confirmed"] = False
            self._report_diagnostic_stage("線阻量測", "cleanup")
            try:
                self.smu.set_output_verified(False)
                facts["smu_off_confirmed"] = True
            except Exception as exc:
                cleanup_errors.append(f"SMU output OFF 未確認: {exc}")
                self._log_error(cleanup_errors[-1], exc_info=True)
            try:
                if not self.relay.reset_all():
                    raise IOError("Relay all-off 狀態讀回失敗")
                facts["relay_off_confirmed"] = True
            except Exception as exc:
                cleanup_errors.append(f"Relay cleanup 未確認: {exc}")
                self._log_error(cleanup_errors[-1], exc_info=True)
            self.is_running = False
            self._emit_current_hardware_status()
        if cleanup_errors:
            self._last_line_resistance_error = " | ".join(filter(None, [self._last_line_resistance_error, *cleanup_errors]))
        if self._last_line_resistance_error:
            facts["cleanup_errors"] = cleanup_errors
            self._last_line_resistance_report = build_diagnostic_report(
                failure or RuntimeError(self._last_line_resistance_error),
                operation="線阻量測", stage=stage if failure else "cleanup", facts=facts,
            )
            self._log_error(f"[R-line REJECTED] {self._last_line_resistance_error}; 未產生可儲存校正值")
            return None
        self._log_info(f"[R-line ACCEPTED] {result!r}; SMU OFF / Relay all-off 已讀回確認")
        result["diagnostic_facts"] = facts
        return result

    def _check_solar_polarity(self, ch_id, current_limit, facts=None):
        """Test the already selected illuminated solar-cell path at zero volts.

        Args:
            ch_id: Channel for the diagnostic log.
            current_limit: Channel current limit, additionally capped at 0.1 A.
            facts: Optional mutable progress evidence, updated at each boundary.

        Returns:
            Measured V/I, limit and authoritative polarity classification.
        """
        facts = facts if facts is not None else {}
        facts["stage"] = "smu_setup"
        limit = min(float(current_limit), 0.1, float(config.GLOBAL_SAFETY["I_MAX"]))
        if not np.isfinite(limit) or limit <= 0:
            raise ValueError("極性測試限流設定無效")
        self.smu.configure_voltage_source_verified(0.0, limit)
        facts["stage"] = "smu_on"
        facts["output_attempted"] = True
        self.smu.set_output_verified(True)
        facts["output_on_confirmed"] = True
        self._interruptible_sleep(0.1)
        facts["stage"] = "sample"
        v_msd, i_msd = self.smu.read_vi()
        facts.update(sample_acquired=True, measured_voltage_V=v_msd, measured_current_A=i_msd)
        facts["stage"] = "compliance"
        compliance = self.smu.read_current_compliance()
        offset = float(self.cal_settings.get("offset_current", 0.0) or 0.0)
        classification = classify_solar_polarity(v_msd, i_msd, offset, compliance)
        corrected_current = None
        if all(np.isfinite(value) for value in (v_msd, i_msd, offset)):
            _, corrected_current = correct_iv_point(v_msd, i_msd, offset, 0.0)
        result = {"v_msd": v_msd, "i_msd": i_msd, "offset_current_A": offset,
                  "i_corrected_A": corrected_current,
                  "classification": classification, "current_limit_A": limit,
                  "current_compliance": compliance}
        self._log_info(f"[POLARITY] CH{ch_id:02d} V_set=0 V result={result!r}")
        return result

    def perform_spot_check(self, ch_id, pos_pin, neg_pin):
        """Run a queued solar-cell diagnostic with the formal polarity policy.

        Args:
            ch_id: Logical channel ID.
            pos_pin: Positive physical relay ID.
            neg_pin: Negative physical relay ID.

        Returns:
            Diagnostic classification, or None if IO/cleanup failed.
        """
        self._last_spot_check_report = None
        if self.is_running or not self.is_hardware_ready():
            return None
        total = int(config.RELAY_CONFIG.get("TOTAL_CHANNELS", 64))
        if pos_pin == neg_pin or not (0 <= pos_pin < total and 0 <= neg_pin < total):
            self._log_error(f"Spot Check 無效 Relay pair {pos_pin}/{neg_pin}")
            return None
        result = None
        failed = False
        failure = None
        facts = {"stage": "relay_pair", "relay_pos": pos_pin, "relay_neg": neg_pin,
                 "relay_pair_confirmed": False, "output_attempted": False,
                 "output_on_confirmed": False, "sample_acquired": False}
        self.is_running = True
        try:
            self._prepare_channel_path(ch_id, pos_pin, neg_pin)
            facts["relay_pair_confirmed"] = True
            result = self._check_solar_polarity(ch_id, 0.1, facts=facts)
        except Exception as e:
            failure = e
            failed = True
            self._log_error(f"Spot Check 失敗: {e}", exc_info=True)
        finally:
            facts["cleanup_attempted"] = True
            facts["smu_off_confirmed"] = facts["relay_off_confirmed"] = False
            facts["cleanup_errors"] = []
            try:
                self.smu.set_output_verified(False)
                facts["smu_off_confirmed"] = True
            except Exception as exc:
                facts["cleanup_errors"].append(str(exc))
                failed = True
                self._log_error(f"Spot Check SMU OFF 未確認: {exc}", exc_info=True)
            try:
                if not self.relay.reset_all():
                    raise IOError("Relay all-off 未確認")
                facts["relay_off_confirmed"] = True
            except Exception as exc:
                facts["cleanup_errors"].append(str(exc))
                failed = True
                self._log_error(f"Spot Check Relay cleanup 失敗: {exc}", exc_info=True)
            self.is_running = False
            self._emit_current_hardware_status()
        if failed:
            self._last_spot_check_report = build_diagnostic_report(
                failure or RuntimeError(" | ".join(facts["cleanup_errors"])), operation="極性診斷",
                stage=facts["stage"] if failure else "cleanup", facts=facts,
            )
        elif result is not None:
            result["diagnostic_facts"] = facts
        return None if failed else result

    # ---------------------------------------------------------
    # Single-channel measurement
    # ---------------------------------------------------------
    def measure_single_channel(self, ch_data, start_time):
        """Measure and persist one channel, then return an explicit outcome.

        Args:
            ch_data: Channel configuration and scheduler metadata.
            start_time: Actual attempt start time.

        Returns:
            ChannelOutcome classifying success, validation, IO or cleanup failure.

        Raises:
            MeasurementInterrupted: Immediate abort after mandatory cleanup.
        """
        if not self.is_running:
            raise MeasurementInterrupted()

        ch_id = ch_data["ch_id"]
        dev_name = ch_data.get("device_name", "N/A")

        config_error = validate_channel_for_measurement(
            ch_data, config.GLOBAL_SAFETY, int(config.RELAY_CONFIG.get("TOTAL_CHANNELS", 64)),
        )
        if config_error:
            self._log_error(f"CH{ch_id:02d} blocked_config | {config_error}")
            self.channel_status_updated.emit({"ch_id": ch_id, "message": f"設定錯誤: {config_error}"})
            return ChannelOutcome(ch_id, "blocked_config", config_error)

        relay_pos = ch_data.get("relay_pos")
        relay_neg = ch_data.get("relay_neg")

        if relay_pos is None or relay_neg is None:
            self._log_error(f"通道 {ch_id} 沒有有效硬體映射 (Relay Pos/Neg is missing)，略過量測")
            self.channel_status_updated.emit({"ch_id": ch_id, "message": "映射錯誤"})
            return ChannelOutcome(ch_id, "blocked_config", "Relay Pos/Neg is missing")

        self._log_scan(f"開始執行 CH{ch_id:02d} 正逆掃")
        self.channel_status_updated.emit({"ch_id": ch_id, "message": "切換路徑..."})

        rline_key = f"{relay_pos}_{relay_neg}"
        rline_max_age_days = config.get_rline_calibration_max_age_days()
        rline_status = config.evaluate_rline_calibration(
            relay_pos, relay_neg, calibration_data=self.cal_settings, max_age_days=rline_max_age_days
        )
        line_res_value = rline_status.get("value")
        line_res_date = ""
        line_res_age_days = rline_status.get("age_days") if rline_status.get("age_days") is not None else ""
        line_res_expired = bool(rline_status.get("expired"))

        if not rline_status.get("exists") or line_res_value is None:
            self._log_error(
                f"CH{ch_id:02d} 禁止啟動：找不到 {rline_key} 的 R-line 線路電阻紀錄。"
                f"請先於 Channel 設定頁量測此 relay pair。原因: {rline_status.get('invalid_reason', 'missing')}"
            )
            self.channel_status_updated.emit({"ch_id": ch_id, "message": "R-line 未量測"})
            return ChannelOutcome(ch_id, "blocked_calibration", f"Missing R-line: {rline_key}")

        rline_record = rline_status.get("record") or {}
        if isinstance(rline_record, dict):
            line_res_date = rline_record.get("time", "") or ""

        if line_res_expired:
            age_text = "無時間戳" if rline_status.get("age_days") is None else f"{rline_status.get('age_days'):.0f} 天前"
            self._log_error(
                f"CH{ch_id:02d} 禁止啟動：{rline_key} 的 R-line 校正已過期或不可追溯 "
                f"({age_text}，門檻 {rline_max_age_days} 天)。請重新量測線阻。"
            )
            self.channel_status_updated.emit({"ch_id": ch_id, "message": "R-line 過期"})
            return ChannelOutcome(ch_id, "blocked_calibration", f"Expired/untraceable R-line: {rline_key}")

        line_res_value = float(line_res_value)

        channel_completed = False
        outcome = ChannelOutcome(ch_id, "failed_read", "Measurement did not complete")
        stage = "relay_failure"
        cleanup_errors = []
        self._active_channel_context = {"ch_id": ch_id, "relay_pos": relay_pos, "relay_neg": relay_neg}

        try:
            self._prepare_channel_path(ch_id, relay_pos, relay_neg, settle_sec=0.3)

            stage = "polarity_failure"
            polarity = self._check_solar_polarity(ch_id, ch_data["i_limit"])
            if polarity["classification"] != "normal":
                raise ValueError(f"極性檢查未通過: {polarity!r}；禁止正逆掃")
            self.smu.set_output_verified(False)

            self.channel_scan_pre_start.emit(ch_id)
            self.channel_scan_prepared.emit(ch_data)

            stage = "blocked_config"
            v_step = ch_data.get("v_step", 0.02)
            v_range = build_voltage_sweep(ch_data["v_start"], ch_data["v_stop"], v_step)

            stage = "failed_read"
            fwd_raw = self.scan_sequence(ch_id, v_range, ch_data, "fwd", line_res_value)
            self._log_scan(f"CH{ch_id:02d} 正掃完成")

            rev_raw = self.scan_sequence(ch_id, v_range[::-1], ch_data, "rev", line_res_value)
            self._log_scan(f"CH{ch_id:02d} 逆掃完成")
            self.smu.set_output_verified(False)

            self.channel_status_updated.emit({"ch_id": ch_id, "message": "分析中..."})
            stage = "failed_analysis"
            analysis_results = calculate_iv_parameters(fwd_raw, rev_raw, ch_data.get("area", 0))
            invalid_scans = [suffix for suffix in ("F_Raw", "R_Raw", "F_Corr", "R_Corr")
                             if analysis_results.get(f"valid_{suffix}") is False]
            if invalid_scans:
                raise ValueError(f"Invalid IV analysis: {', '.join(invalid_scans)}")

            measurement_timestamp = datetime.datetime.now()
            save_meta = {
                **ch_data,
                "line_res": line_res_value,
                "rline_validation_version": rline_record.get("validation_version"),
                "line_res_date": line_res_date,
                "line_res_age_days": line_res_age_days,
                "line_res_expired": line_res_expired,
                "rline_max_age_days": rline_max_age_days,
                "offset_current": float(self.cal_settings.get("offset_current", 0.0) or 0.0),
                "polarity_check": polarity,
                "start_time": start_time,
                "actual_end_time": measurement_timestamp,
            }

            stage = "failed_logger"
            config.get_safe_data_dir()
            raw_file_path = self.iv_curve_logger.save_iv_curve(save_meta, fwd_raw, rev_raw, analysis_results)

            summary_data = {
                **save_meta,
                **analysis_results,
                "file_path": raw_file_path,
                "timestamp": measurement_timestamp,
                "temp": ch_data.get("temp"),
                "hum": ch_data.get("hum"),
                "scan_stop_requested_during_channel": bool(self.stop_requested),
            }
            self.summary_logger.update_summary_report(summary_data)

            channel_completed = True
            outcome = ChannelOutcome(ch_id, "completed")

        except Exception as e:
            if not isinstance(e, MeasurementInterrupted):
                outcome = ChannelOutcome(ch_id, stage, f"{type(e).__name__}: {e}")
                self._log_error(
                    f"通道 {ch_id} 量測失敗 | status={stage} | relay={relay_pos}/{relay_neg} | "
                    f"device={dev_name} | reason={outcome.error}", exc_info=True,
                )
            else:
                raise
        finally:
            if self.smu and self._probe_smu_connected():
                try:
                    self.smu.set_output_verified(False)
                except Exception as e:
                    self._log_warning(f"CH{ch_id:02d} 量測後 SMU output OFF 失敗: {e}")
                    cleanup_errors.append(f"SMU OFF: {type(e).__name__}: {e}")
                if not getattr(self.smu, "is_connected", False):
                    cleanup_errors.append("SMU disconnected during output OFF")
            else:
                cleanup_errors.append("SMU unavailable; output OFF unconfirmed")

            if self.relay and self._probe_relay_connected():
                try:
                    self._cleanup_channel_path(settle_sec=0.05)
                except Exception as e:
                    self._log_warning(f"CH{ch_id:02d} 量測後 Relay 清空失敗: {e}")
                    cleanup_errors.append(f"Relay reset: {type(e).__name__}: {e}")
            else:
                cleanup_errors.append("Relay unavailable; all-off unconfirmed")

            self._active_channel_context = None
            if cleanup_errors:
                self._log_error(f"CH{ch_id:02d} cleanup unconfirmed | errors={cleanup_errors}")

        if cleanup_errors:
            outcome = ChannelOutcome(
                ch_id, "cleanup_failure" if channel_completed else outcome.status,
                outcome.error or "Hardware cleanup unconfirmed", tuple(cleanup_errors),
            )
        if outcome.succeeded:
            self.channel_measurement_finished.emit(summary_data)
            self.channel_status_updated.emit({"ch_id": ch_id, "message": "已完成"})
        else:
            self.channel_status_updated.emit({
                "ch_id": ch_id, "status": "failed",
                "message": f"量測失敗 [{outcome.status}]: {outcome.error}",
            })
        return outcome

    def scan_sequence(self, ch_id, v_list, ch_data, direction, r_line_ohm):
        """Sweep a verified source, preserving measured V/I and signed correction.

        Args:
            ch_id: Logical channel ID.
            v_list: Ordered source-voltage levels.
            ch_data: Validated channel settings.
            direction: Forward or reverse label.
            r_line_ohm: Qualified pair resistance in ohms.

        Returns:
            Raw and corrected measurement point dictionaries.

        Raises:
            HardwareReadError: Compliance or a nonfinite sample is detected.
        """
        results = []
        i_limit = ch_data.get("i_limit", 0.5)

        if direction == "fwd":
            self.smu.set_output_verified(False)
        self.smu.configure_voltage_source_verified(v_list[0], i_limit)
        self.smu.set_output_verified(True)

        delay_sec = ch_data.get("delay_time", 50) / 1000.0
        offset_current = float(self.cal_settings.get("offset_current", 0.0) or 0.0)

        for v in v_list:
            if not self.is_running:
                raise MeasurementInterrupted()

            self.smu.set_voltage_verified(v)
            self._interruptible_sleep(delay_sec)

            try:
                v_msd, i_msd = self.smu.read_vi()
                compliance = self.smu.read_current_compliance()
                self._log_info(f"[IV SAMPLE] CH{ch_id:02d} {direction} V_set={v!r} V_meas={v_msd!r} I_meas={i_msd!r} compliance={compliance!r}")
                if compliance is not False:
                    raise HardwareReadError("正式掃描觸發限流或狀態未知；本次掃描無效")
            except (HardwareReadError, HardwareCommunicationError) as exc:
                self._log_error(
                    f"CH{ch_id:02d} {direction} 掃描於設定電壓 {v:.4f} V 發生 SMU 讀值失敗；"
                    f"本次通道量測將標記失敗且不寫入偽造 0.0/0.0 數據: {exc}"
                )
                raise

            v_corr, i_corr = correct_iv_point(v_msd, i_msd, offset_current, r_line_ohm)

            point = {
                "v_src": v,
                "v_msd": v_msd,
                "i_msd": i_msd,
                "v_corr": v_corr,
                "i_corr": i_corr,
                "offset_current": offset_current,
            }
            results.append(point)

            self.channel_status_updated.emit({"ch_id": ch_id, "message": f"{v_corr:.2f}V"})
            self.point_measured.emit({**point, "ch_id": ch_id, "direction": direction})

        return results

    @pyqtSlot(int, int, int)
    def request_line_resistance_measurement(self, request_id, pos_pin, neg_pin):
        """Return qualified results or an evidence-based operator failure report.

        Args:
            request_id: GUI correlation token.
            pos_pin: Positive physical relay.
            neg_pin: Negative physical relay.
        """
        result = {"request_id": request_id, "ok": False, "resistance": None, "pos_pin": pos_pin, "neg_pin": neg_pin, "error": ""}
        self._active_diagnostic_request_id = request_id
        try:
            measurement = self.measure_line_resistance(pos_pin, neg_pin)
            if measurement is None:
                result["error"] = getattr(self, "_last_line_resistance_error", "") or "線路電阻量測失敗，請檢查 log。"
                result["diagnostic"] = getattr(self, "_last_line_resistance_report", None) or build_diagnostic_report(result["error"])
            else:
                if isinstance(measurement, dict):
                    result.update({"ok": True, **measurement})
                else:
                    result.update({"ok": True, "resistance": float(measurement)})
        except Exception as exc:
            result["error"] = str(exc)
            result["diagnostic"] = build_diagnostic_report(exc)
            self._log_error(f"線阻 queued request 失敗: {exc}", exc_info=True)
        finally:
            self._active_diagnostic_request_id = None
        self.line_resistance_result.emit(result)

    @pyqtSlot(int, int, int, int)
    def request_spot_check(self, request_id, ch_id, pos_pin, neg_pin):
        """Queued GUI entry point for spot-check diagnostics."""
        result = {"request_id": request_id, "ok": False, "ch_id": ch_id, "pos_pin": pos_pin, "neg_pin": neg_pin, "error": ""}
        try:
            values = self.perform_spot_check(ch_id, pos_pin, neg_pin)
            if values is None:
                result["error"] = "即時連線測試失敗，請檢查 log。"
                result["diagnostic"] = getattr(self, "_last_spot_check_report", None) or build_diagnostic_report(result["error"], operation="極性診斷")
            else:
                result.update({"ok": True, **values})
        except Exception as exc:
            result["error"] = str(exc)
            result["diagnostic"] = build_diagnostic_report(exc, operation="極性診斷")
            self._log_error(f"Spot-check queued request 失敗: {exc}", exc_info=True)
        self.spot_check_result.emit(result)

    # ---------------------------------------------------------
    # Shutdown
    # ---------------------------------------------------------
    def force_safe_hardware_state(self, close_connections=False):
        """Force hardware to an electrically safe state.

        This method is intentionally idempotent and is used by
        `core.shutdown_manager.ShutdownManager` for both safe process shutdown
        and emergency shutdown.  It first removes electrical output, then opens
        relay paths, and only then closes communication handles when requested.
        """
        self._log_info("[SHUTDOWN] 強制硬體進入安全狀態：SMU output OFF -> Relay reset_all")

        if self.smu:
            try:
                self.smu.set_output_verified(False)
                self._log_info("[SHUTDOWN] SMU output OFF readback confirmed.")
            except Exception as e:
                self._log_warning(f"[SHUTDOWN] 關閉 SMU output 時發生例外: {e}")

        if self.relay:
            try:
                if not self.relay.reset_all():
                    raise IOError("Relay all-off 未確認")
                self._log_info("[SHUTDOWN] Relay all-off readback confirmed.")
            except Exception as e:
                self._log_warning(f"[SHUTDOWN] Relay reset_all 時發生例外: {e}")

        if close_connections:
            if self.smu:
                try:
                    self.smu.close()
                except Exception as e:
                    self._log_warning(f"[SHUTDOWN] 關閉 SMU 連線時發生例外: {e}")

            if self.relay:
                try:
                    self.relay.close()
                except Exception as e:
                    self._log_warning(f"[SHUTDOWN] 關閉 Relay 連線時發生例外: {e}")

            if self.chamber_driver and hasattr(self.chamber_driver, "close"):
                try:
                    self.chamber_driver.close()
                except Exception as e:
                    self._log_warning(f"[SHUTDOWN] 關閉 Chamber 連線時發生例外: {e}")

        self._emit_current_hardware_status()

    @pyqtSlot()
    def emergency_shutdown(self):
        """Immediate abort path for operator emergency shutdown.

        This differs from `stop_scan_cycle()`: it does not wait for the current
        channel boundary.  The current data point/curve may be incomplete, but
        SMU output and relay state are forced safe as quickly as possible.
        """
        self._log_error("[SHUTDOWN] EMERGENCY_SHUTDOWN_AND_EXIT requested; current scan may be incomplete.")
        self.stop_requested = True
        self.stop_request_reason = "emergency_shutdown_and_exit"
        self.stop_request_at = datetime.datetime.now()
        self.last_finish_reason = "emergency_shutdown_and_exit"
        self.is_running = False
        self.force_safe_hardware_state(close_connections=True)
        self.scan_finished.emit(self._build_finish_info())

    @pyqtSlot()
    def shutdown_hardware(self):
        self._log_info("正在關閉硬體連線...")
        self.force_safe_hardware_state(close_connections=True)
        self._log_info("所有硬體連線已安全關閉。")
