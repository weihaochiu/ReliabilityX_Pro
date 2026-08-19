import contextlib
from typing import Callable, Optional, Tuple


class HardwareManager:
    """Manage hardware health checks, reconnect, and shutdown.

    This class owns no UI logic. It centralizes connection probing,
    reconnect-if-needed behavior, and safe hardware shutdown.

    Args:
        smu_driver: SMU driver instance.
        relay_driver: Relay driver instance.
        chamber_driver: Chamber driver instance.
        log_info: Logger callback for info-level messages.
        log_warning: Logger callback for warning-level messages.
        log_error: Logger callback for error-level messages.
    """

    def __init__(
        self,
        smu_driver=None,
        relay_driver=None,
        chamber_driver=None,
        log_info: Optional[Callable[[str], None]] = None,
        log_warning: Optional[Callable[[str], None]] = None,
        log_error: Optional[Callable[[str], None]] = None,
    ):
        self.smu = smu_driver
        self.relay = relay_driver
        self.chamber_driver = chamber_driver
        self._log_info = log_info or (lambda msg: None)
        self._log_warning = log_warning or (lambda msg: None)
        self._log_error = log_error or (lambda msg: None)

    def probe_smu_connected(self) -> bool:
        """Return whether the SMU is healthy and connected."""
        if not self.smu:
            return False
        if not getattr(self.smu, "is_connected", False):
            return False
        try:
            if hasattr(self.smu, "get_idn"):
                idn = self.smu.get_idn()
                return isinstance(idn, str) and bool(idn.strip())
            return True
        except Exception as exc:
            self._log_warning(f"SMU 狀態驗證失敗，視為未連線: {exc}")
            with contextlib.suppress(Exception):
                self.smu.close()
            return False

    def probe_relay_connected(self) -> bool:
        """Return whether the relay board is healthy and connected."""
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

    def probe_chamber_connected(self) -> bool:
        """Return whether the chamber is healthy and connected."""
        if not self.chamber_driver:
            return False
        return bool(getattr(self.chamber_driver, "is_connected", False))

    def connect_smu_if_needed(self) -> bool:
        """Reconnect the SMU only when it is not already connected."""
        if not self.smu:
            self._log_warning("SMU driver 不存在。")
            return False

        if self.probe_smu_connected():
            self._log_info("SMU 已連線，略過重連。")
            return True

        self._log_info("SMU 未連線，開始重新連線...")
        try:
            ok = bool(self.smu.connect())
        except Exception as exc:
            self._log_error(f"SMU 重連失敗: {exc}")
            ok = False

        if ok:
            self._log_info("SMU 連線: 成功")
        else:
            self._log_error("SMU 連線: 失敗")
        return ok

    def connect_relay_if_needed(self, *, allow_reset_all: bool = True, active_measurement: bool = False) -> bool:
        """Reconnect the relay board only when it is not already connected.

        ``reset_all`` is only safe at idle/startup/shutdown boundaries.  During
        an active measurement, reconnecting and immediately resetting every
        relay can physically cut the active IV path and pollute the data.
        """
        if not self.relay:
            self._log_warning("Relay driver 不存在。")
            return False

        if self.probe_relay_connected():
            self._log_info("Relay 已連線，略過重連。")
            return True

        self._log_info("Relay 未連線，開始重新連線...")
        try:
            ok = bool(self.relay.auto_scan())
            if ok and allow_reset_all and not active_measurement:
                with contextlib.suppress(Exception):
                    self.relay.reset_all()
            elif ok and active_measurement:
                self._log_error(
                    "Relay 於 active measurement 期間重新連線；已禁止自動 reset_all。"
                    "上層量測流程應中止或標記目前 channel 失敗。"
                )
                return False
        except Exception as exc:
            self._log_error(f"Relay 重連失敗: {exc}")
            ok = False

        if ok:
            self._log_info("Relay 連線: 成功")
        else:
            self._log_warning("Relay 連線: 失敗")
        return ok

    def connect_chamber_if_needed(self) -> bool:
        """Reconnect the chamber only when it is not already connected."""
        if not self.chamber_driver:
            return False

        if self.probe_chamber_connected():
            self._log_info("Chamber 已連線，略過重連。")
            return True

        connect_func = getattr(self.chamber_driver, "connect", None)
        if not callable(connect_func):
            return bool(getattr(self.chamber_driver, "is_connected", False))

        self._log_info("Chamber 未連線，開始重新連線...")
        try:
            ok = bool(connect_func())
        except Exception as exc:
            self._log_error(f"Chamber 重連失敗: {exc}")
            ok = False

        if ok:
            self._log_info("Chamber 連線: 成功")
        else:
            self._log_warning("Chamber 連線: 失敗")
        return ok

    def initialize_hardware(self) -> Tuple[bool, bool, bool]:
        """Initialize or reconnect all supported hardware as needed.

        Returns:
            Tuple[bool, bool, bool]: SMU, relay, and chamber connection states.
        """
        self._log_info("初始化硬體中（僅重連未連線設備）...")
        smu_connected = self.connect_smu_if_needed()
        relay_connected = self.connect_relay_if_needed()
        chamber_connected = self.connect_chamber_if_needed()
        return smu_connected, relay_connected, chamber_connected

    def emit_status(self, emitter: Callable[[bool, bool, bool], None]) -> Tuple[bool, bool, bool]:
        """Emit current hardware status through a provided callback.

        Args:
            emitter: Callable that accepts SMU/Relay/Chamber booleans.

        Returns:
            Tuple[bool, bool, bool]: Current connection states.
        """
        smu_ok = self.probe_smu_connected()
        relay_ok = self.probe_relay_connected()
        chamber_ok = self.probe_chamber_connected()
        emitter(smu_ok, relay_ok, chamber_ok)
        return smu_ok, relay_ok, chamber_ok

    def is_measurement_ready(self) -> bool:
        """Return whether the measurement-critical devices are ready."""
        smu_ok = self.probe_smu_connected()
        relay_ok = self.probe_relay_connected()

        if smu_ok and relay_ok:
            return True

        if not smu_ok:
            self._log_error("硬體未就緒: SMU 未連線")
        if not relay_ok:
            self._log_error("硬體未就緒: Relay 未連線")
        return False

    def shutdown_hardware(self) -> None:
        """Safely close all hardware connections."""
        self._log_info("正在關閉硬體連線...")

        if self.smu:
            try:
                self.smu.close()
            except Exception as exc:
                self._log_warning(f"關閉 SMU 時發生例外: {exc}")

        if self.relay:
            try:
                self.relay.close()
            except Exception as exc:
                self._log_warning(f"關閉 Relay 時發生例外: {exc}")

        if self.chamber_driver and hasattr(self.chamber_driver, "close"):
            try:
                self.chamber_driver.close()
            except Exception as exc:
                self._log_warning(f"關閉 Chamber 時發生例外: {exc}")

        self._log_info("所有硬體連線已安全關閉。")
