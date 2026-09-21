
"""Strict SMU IO, documented GSM level queries and structured failures (OI-057)."""

import time
import math
import traceback
from functools import wraps

import pyvisa
import config


class SMUDriverError(RuntimeError):
    """Base exception for SMU driver failures."""


class VisaBackendUnavailableError(SMUDriverError):
    """Raised when neither the default VISA backend nor pyvisa-py can initialize."""


class HardwareCommunicationError(SMUDriverError):
    """Raised when SMU communication fails before a valid instrument response is obtained."""

    def __init__(self, message, *, command=None, response=None, code="smu_communication"):
        """Preserve transport evidence for operator-facing reports.

        Args:
            message: Technical description.
            command: Failed SCPI command, if known.
            response: Raw response, or None when none was obtained.
            code: Stable diagnostic category, not derived from translated text.
        """
        super().__init__(message)
        self.command = command
        self.response = response
        self.code = code


class HardwareReadError(SMUDriverError):
    """Raised when :READ? cannot provide a trustworthy voltage/current pair."""


class HardwareParseError(HardwareReadError):
    """Raised when a SMU response is present but cannot be parsed as V/I data."""


def visa_command(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        is_read_vi = func.__name__ == "read_vi"

        if not self.is_connected and func.__name__ not in ["connect", "close"]:
            message = f"指令 '{func.__name__}' 執行失敗，SMU 未連線。"
            self._log("WARNING", message)
            if is_read_vi:
                raise HardwareCommunicationError(message)
            if "read" in func.__name__ or "get" in func.__name__ or "is_" in func.__name__:
                return False
            return None

        try:
            return func(self, *args, **kwargs)
        except pyvisa.errors.VisaIOError as e:
            is_conn_lost = e.error_code in [
                pyvisa.constants.StatusCode.error_connection_lost,
                pyvisa.constants.StatusCode.error_io,
                pyvisa.constants.StatusCode.error_timeout,
            ]

            if is_conn_lost:
                self._log(
                    "ERROR",
                    f"執行 '{func.__name__}' 時發生 VISA 通訊錯誤 ({e.description})，"
                    f"已中止本次指令並關閉連線，等待後續重新初始化。",
                )
                self.close()
            else:
                self._log("ERROR", f"執行 '{func.__name__}' 時發生 VISA 錯誤: {e.description}")

            if is_read_vi:
                raise HardwareReadError(f"SMU read_vi VISA communication failure: {e.description}") from e
            if "read" in func.__name__ or "get" in func.__name__ or "is_" in func.__name__:
                return False
            return None
        except HardwareReadError:
            raise
        except Exception as e:
            self._log("ERROR", f"執行 '{func.__name__}' 時發生未知錯誤: {e}")
            if is_read_vi:
                raise HardwareReadError(f"SMU read_vi unexpected failure: {e}") from e
            if "read" in func.__name__ or "get" in func.__name__ or "is_" in func.__name__:
                return False
            return None

    return wrapper

class SMUDriver:
    """
    專業級 GSM-20H10 驅動程式
    重點修正：
    1. 將 VISA timeout 預設縮短，降低 stop latency。
    2. 發生通訊錯誤時，不在 driver 內做同步自動重連，避免卡住 worker thread。
    3. 保留既有 API 介面，維持與 MeasureEngine 相容。
    """

    def __init__(self, log_manager=None):
        self.log_mgr = log_manager
        self.visa_backend = "uninitialized"
        self.rm = self._create_resource_manager()
        self.device = None
        self.is_connected = False
        self.last_config = {}
        self.idn = None
        self.command_timeout_ms = 3000

    def _calibration_command(self, command, query=False):
        """Execute a calibration command without swallowing communication errors.

        Args:
            command: SCPI command.
            query: Whether a response is required.

        Returns:
            Stripped raw response for queries, otherwise None.

        Raises:
            HardwareCommunicationError: IO failure or disconnected resource.
        """
        raw = None
        try:
            if not self.is_connected or self.device is None:
                raise IOError("SMU 未連線")
            if query:
                raw = self.device.query(command)
                result = raw.strip()
            else:
                self.device.write(command)
                result = None
            self._log("INFO", f"[SMU VERIFIED] resource={getattr(self.device, 'resource_name', '?')} TX={command!r} RX={raw!r}")
            return result
        except Exception as exc:
            self._log("ERROR", f"[SMU VERIFIED] resource={getattr(self.device, 'resource_name', '?')} TX={command!r} RX={raw!r} {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            code = "smu_timeout" if (
                isinstance(exc, pyvisa.errors.VisaIOError)
                and exc.error_code == pyvisa.constants.StatusCode.error_timeout
            ) else "smu_communication"
            raise HardwareCommunicationError(
                f"SMU command {command!r} failed: {exc}", command=command,
                response=raw, code=code,
            ) from exc

    def set_output_verified(self, enabled):
        """Set output and require an exact state readback.

        Args:
            enabled: Requested boolean output state.

        Raises:
            HardwareCommunicationError: Output cannot be confirmed.
        """
        self._calibration_command(":OUTP ON" if enabled else ":OUTP OFF")
        raw = self._calibration_command(":OUTP:STAT?", query=True)
        if raw != ("1" if enabled else "0"):
            raise HardwareCommunicationError(f"SMU output state mismatch: requested={enabled}, RX={raw!r}")

    def configure_current_source_verified(self, current, v_limit):
        """Configure fixed current sourcing and verify mode, level and limit.

        Args:
            current: Requested current in A.
            v_limit: Voltage compliance in V.

        Raises:
            HardwareCommunicationError: Any setting is not confirmed.
        """
        for command in (":SOUR:FUNC CURR", ":SOUR:CURR:MODE FIXED",
                        f":SOUR:CURR:LEV {current}", f":SENS:VOLT:PROT:LEV {v_limit}"):
            self._calibration_command(command)
        for query, expected in ((":SOUR:FUNC?", "CURR"), (":SOUR:CURR:MODE?", "FIX")):
            raw = self._calibration_command(query, query=True).upper()
            if raw not in ({"CURR", "CURRENT"} if expected == "CURR" else {"FIX", "FIXED"}):
                raise HardwareCommunicationError(f"SMU setting mismatch: {query} RX={raw!r}")
        # GSM manual printed pp.252-253 explicitly specifies CURRent?/VOLTage?.
        # V1.22 field logs time out on the optional-LEVel query spelling.
        for query, expected in ((":SOUR:CURR?", current), (":SENS:VOLT:PROT:LEV?", v_limit)):
            raw = self._calibration_command(query, query=True)
            if not math.isclose(float(raw), expected, rel_tol=1e-6, abs_tol=1e-12):
                raise HardwareCommunicationError(f"SMU setting mismatch: {query} expected={expected} RX={raw!r}")

    def read_voltage_compliance(self):
        """Return explicit voltage-compliance state, raising on unknown replies.

        Returns:
            bool: Whether the current-source voltage limit has tripped.

        Raises:
            HardwareCommunicationError: Unknown or unavailable status.
        """
        raw = self._calibration_command(":SENS:VOLT:PROT:TRIP?", query=True)
        if raw not in ("0", "1"):
            raise HardwareCommunicationError(f"SMU compliance unknown: RX={raw!r}")
        return raw == "1"

    def configure_voltage_source_verified(self, voltage, current_limit):
        """Configure fixed voltage sourcing and verify mode, level and compliance.

        Args:
            voltage: Requested source voltage in V.
            current_limit: Positive current compliance in A.

        Raises:
            HardwareCommunicationError: Setting or readback failed.
        """
        for command in (":SOUR:FUNC VOLT", ":SOUR:VOLT:MODE FIXED",
                        f":SENS:CURR:PROT:LEV {current_limit}"):
            self._calibration_command(command)
        self.set_voltage_verified(voltage)
        for query, accepted in ((":SOUR:FUNC?", {"VOLT", "VOLTAGE"}),
                                (":SOUR:VOLT:MODE?", {"FIX", "FIXED"})):
            raw = self._calibration_command(query, query=True).upper()
            if raw not in accepted:
                raise HardwareCommunicationError(f"SMU setting mismatch: {query} RX={raw!r}")
        raw = self._calibration_command(":SENS:CURR:PROT:LEV?", query=True)
        if not math.isclose(float(raw), current_limit, rel_tol=1e-6, abs_tol=1e-12):
            raise HardwareCommunicationError(f"SMU current limit mismatch: expected={current_limit} RX={raw!r}")

    def set_voltage_verified(self, voltage):
        """Set and verify the voltage-source level.

        Args:
            voltage: Source voltage in V.

        Raises:
            HardwareCommunicationError: Level readback mismatch.
        """
        self._calibration_command(f":SOUR:VOLT:LEV {voltage}")
        raw = self._calibration_command(":SOUR:VOLT?", query=True)
        if not math.isclose(float(raw), voltage, rel_tol=1e-6, abs_tol=1e-12):
            raise HardwareCommunicationError(f"SMU voltage mismatch: expected={voltage} RX={raw!r}")

    def read_current_compliance(self):
        """Read voltage-source current compliance, rejecting unknown responses.

        Returns:
            bool: Current limit tripped.

        Raises:
            HardwareCommunicationError: Status is not an explicit zero or one.
        """
        raw = self._calibration_command(":SENS:CURR:PROT:TRIP?", query=True)
        if raw not in ("0", "1"):
            raise HardwareCommunicationError(f"SMU current compliance unknown: RX={raw!r}")
        return raw == "1"

    def _create_resource_manager(self):
        """Create a VISA resource manager with actionable backend diagnostics.

        Returns:
            pyvisa.ResourceManager: The first available VISA backend.

        Raises:
            VisaBackendUnavailableError: If neither NI-VISA/default nor
                pyvisa-py can initialize.
        """
        errors = []
        for backend in (None, "@py"):
            try:
                if backend is None:
                    manager = pyvisa.ResourceManager()
                    backend_type = type(getattr(manager, "visalib", None))
                    self.visa_backend = f"default/{backend_type.__module__}.{backend_type.__name__}"
                    return manager
                manager = pyvisa.ResourceManager(backend)
                self.visa_backend = backend
                return manager
            except Exception as exc:
                backend_name = "default" if backend is None else backend
                errors.append(f"{backend_name}: {type(exc).__name__}: {exc}")

        message = (
            "Unable to initialize a VISA backend. Install NI-VISA or pyvisa-py, "
            "then restart ReliabilityX Pro. Details: " + " | ".join(errors)
        )
        raise VisaBackendUnavailableError(message)

    def _log(self, level, message):
        if self.log_mgr:
            if level == "INFO":
                self.log_mgr.log_info(message)
            elif level == "ERROR":
                self.log_mgr.log_error(message)
            elif level == "WARNING":
                self.log_mgr.log_warning(message)
            else:
                self.log_mgr.log_info(message)
        else:
            print(f"[{level}] SMU: {message}")

    @staticmethod
    def list_available_resources():
        try:
            rm = pyvisa.ResourceManager()
            resources = rm.list_resources()
            rm.close()
            return list(resources)
        except Exception as e:
            print(f"[ERROR] 掃描 VISA 資源時出錯: {e}")
            return []

    def _resolve_timeout_ms(self, config_source):
        raw = None
        try:
            raw = config_source.get("COMMAND_TIMEOUT_MS")
        except Exception:
            raw = None

        try:
            value = int(raw)
            if value < 500:
                value = 500
            return value
        except Exception:
            return 3000

    def connect(self, temp_config=None):
        """Connect to the configured SMU and log every identification stage.

        Args:
            temp_config: Optional connection settings used by a GUI test.

        Returns:
            bool: True only when the VISA resource opens, ``*IDN?`` returns a
            non-empty identity, and the initialization sequence stays connected.
        """
        config_source = temp_config if temp_config is not None else config.SMU_CONFIG
        address = config_source.get("VISA_ADDRESS", "")
        if_type = config_source.get("INTERFACE_TYPE", "LAN")
        res_name = ""
        available_resources = []
        stage = "resolve_configuration"

        try:
            if if_type == "LAN":
                res_name = f"TCPIP0::{address}::inst0::INSTR" if "::" not in address else address
            else:
                res_name = address

            self.command_timeout_ms = self._resolve_timeout_ms(config_source)
            if not str(address or "").strip():
                self._log(
                    "ERROR",
                    "[SMU CONNECT] 連線設定無效"
                    f" | interface={if_type}"
                    " | address=(empty)"
                    f" | backend={self.visa_backend}"
                    " | reason=missing_visa_address"
                    " | action=請在 Hardware Connection / SMU 設定 VISA address 或 LAN IP。",
                )
                return False

            stage = "list_resources"
            try:
                available_resources = list(self.rm.list_resources())
                self._log(
                    "INFO",
                    "[SMU CONNECT] VISA resources"
                    f" | backend={self.visa_backend}"
                    f" | count={len(available_resources)}"
                    f" | resources={available_resources or '(none)'}",
                )
            except Exception as list_exc:
                self._log(
                    "WARNING",
                    "[SMU CONNECT] VISA resource 枚舉失敗，仍會嘗試設定的 resource"
                    f" | backend={self.visa_backend}"
                    f" | exception={type(list_exc).__name__}: {list_exc}"
                    f"\nTraceback:\n{traceback.format_exc().strip()}",
                )

            self._log(
                "INFO",
                "[SMU CONNECT] 開始連線"
                f" | interface={if_type}"
                f" | resource={res_name}"
                f" | backend={self.visa_backend}"
                f" | timeout_ms={self.command_timeout_ms}"
                " | TX=*IDN?",
            )
            stage = "open_resource"
            self.device = self.rm.open_resource(res_name)

            self.device.timeout = self.command_timeout_ms
            self.device.read_termination = "\n"
            self.device.write_termination = "\n"
            stage = "clear_resource"
            self.device.clear()

            stage = "query_idn"
            idn_str = self.device.query("*IDN?").strip()
            if not idn_str:
                raise HardwareCommunicationError("*IDN? returned an empty response")

            self.idn = idn_str
            self.is_connected = True
            self.last_config = config_source.copy()
            self._log(
                "INFO",
                "[SMU CONNECT] 識別成功"
                f" | resource={res_name}"
                f" | TX=*IDN?"
                f" | RX={self.idn}"
                " | validation=non_empty_idn",
            )

            stage = "initialize_instrument"
            self.reset_system()
            if not self.is_connected or self.device is None:
                self._log(
                    "ERROR",
                    "[SMU CONNECT] *IDN? 成功，但初始化指令失敗後連線已關閉"
                    f" | resource={res_name}"
                    " | commands=*RST; :FORM:ELEM VOLT,CURR; :SENS:FUNC:CONC ON; "
                    ":SOUR:VOLT:MODE FIXED; :SENS:CURR:PROT:LEV 0.5"
                    " | safety=driver 已依 VISA error path 嘗試關閉連線。",
                )
                return False
            return True

        except Exception as e:
            safety_actions = []
            if self.device is not None:
                try:
                    self.device.write(":OUTP OFF")
                    safety_actions.append("SMU output OFF command sent")
                except Exception as safety_exc:
                    safety_actions.append(
                        f"SMU output OFF not confirmed ({type(safety_exc).__name__}: {safety_exc})"
                    )
                try:
                    self.device.close()
                    safety_actions.append("VISA resource closed")
                except Exception as close_exc:
                    safety_actions.append(
                        f"VISA close failed ({type(close_exc).__name__}: {close_exc})"
                    )
            else:
                safety_actions.append("resource was not opened; no SMU command sent")
            self.device = None
            self.is_connected = False
            self.idn = None
            self._log(
                "ERROR",
                "[SMU CONNECT] 連線失敗"
                f" | stage={stage}"
                f" | interface={if_type}"
                f" | resource={res_name or '(unresolved)'}"
                f" | backend={self.visa_backend}"
                f" | timeout_ms={self.command_timeout_ms}"
                f" | available_resources={available_resources or '(none)'}"
                f" | exception={type(e).__name__}: {e}"
                f" | safety={'; '.join(safety_actions)}"
                " | action=依 stage 檢查 VISA backend、IP/USB resource、網路、儀器 Remote 狀態與 timeout。"
                f"\nTraceback:\n{traceback.format_exc().strip()}",
            )
            return False

    @visa_command
    def get_idn(self):
        if self.idn:
            return self.idn
        self.idn = self.device.query("*IDN?").strip()
        return self.idn

    @visa_command
    def configure_source(self, voltage, current_limit):
        self.device.write(":SOUR:FUNC VOLT")
        self.device.write(f":SOUR:VOLT:LEV {voltage}")
        self.device.write(f":SENS:CURR:PROT:LEV {current_limit}")
        self._log("INFO", f"SMU Source 設定完成: Voltage={voltage}V, Current Limit={current_limit}A")

    @visa_command
    def configure_source_curr(self, current, v_limit):
        self.device.write(":SOUR:FUNC CURR")
        self.device.write(f":SOUR:CURR:LEV {current}")
        self.device.write(f":SENS:VOLT:PROT:LEV {v_limit}")
        self._log("INFO", f"SMU Source 設定完成: Current={current}A, Voltage Limit={v_limit}V")

    @visa_command
    def is_output_on(self):
        state = self.device.query(":OUTP:STAT?").strip()
        return state == "1"

    @visa_command
    def reset_system(self):
        self.device.write("*RST")
        self.device.write(":FORM:ELEM VOLT,CURR")
        self.device.write(":SENS:FUNC:CONC ON")
        self.device.write(":SOUR:VOLT:MODE FIXED")
        self.device.write(":SENS:CURR:PROT:LEV 0.5")
        self._log("INFO", "SMU 系統重置並完成資料格式 (:FORM:ELEM) 設定")

    @visa_command
    def read_vi(self):
        raw_data = self.device.query(":READ?").strip()

        if not raw_data:
            message = "SMU :READ? 回應為空；本次讀值無效，不得寫入為 0.0/0.0。"
            self._log("ERROR", message)
            raise HardwareReadError(message)

        try:
            parts = [float(x.strip()) for x in raw_data.split(",")]
        except (ValueError, IndexError) as e:
            message = f"SMU :READ? 數據解析失敗，raw='{raw_data}': {e}"
            self._log("ERROR", message)
            raise HardwareParseError(message) from e

        if len(parts) != 2:
            message = f"SMU :READ? 數據格式錯誤，預期 2 個值但收到 {len(parts)} 個，raw='{raw_data}'"
            self._log("ERROR", message)
            raise HardwareParseError(message)

        return parts[0], parts[1]

    @visa_command
    def output_control(self, state):
        cmd = "ON" if state in [True, "ON", 1] else "OFF"
        self.device.write(f":OUTP {cmd}")

    @visa_command
    def set_voltage(self, voltage):
        self.device.write(f":SOUR:VOLT:LEV {voltage}")

    def close(self):
        if self.device:
            try:
                self.device.write(":OUTP OFF")
            except Exception:
                pass
            try:
                self.device.close()
            except Exception:
                pass
        self.device = None
        self.is_connected = False
        self.idn = None
        self._log("INFO", "SMU 連線已安全釋放")
