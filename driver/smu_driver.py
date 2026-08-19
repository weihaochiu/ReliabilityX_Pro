
import time
from functools import wraps

import pyvisa
import config


class SMUDriverError(RuntimeError):
    """Base exception for SMU driver failures."""


class VisaBackendUnavailableError(SMUDriverError):
    """Raised when neither the default VISA backend nor pyvisa-py can initialize."""


class HardwareCommunicationError(SMUDriverError):
    """Raised when SMU communication fails before a valid instrument response is obtained."""


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
        self.rm = self._create_resource_manager()
        self.device = None
        self.is_connected = False
        self.last_config = {}
        self.idn = None
        self.command_timeout_ms = 3000

    def _create_resource_manager(self):
        errors = []
        for backend in (None, "@py"):
            try:
                if backend is None:
                    return pyvisa.ResourceManager()
                return pyvisa.ResourceManager(backend)
            except Exception as exc:
                backend_name = "default" if backend is None else backend
                errors.append(f"{backend_name}: {exc}")

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
        config_source = temp_config if temp_config is not None else config.SMU_CONFIG
        address = config_source.get("VISA_ADDRESS", "")
        if_type = config_source.get("INTERFACE_TYPE", "LAN")

        try:
            if if_type == "LAN":
                res_name = f"TCPIP0::{address}::inst0::INSTR" if "::" not in address else address
            else:
                res_name = address

            self.command_timeout_ms = self._resolve_timeout_ms(config_source)

            self._log("INFO", f"正在連線至: {res_name}")
            self.device = self.rm.open_resource(res_name)

            self.device.timeout = self.command_timeout_ms
            self.device.read_termination = "\n"
            self.device.write_termination = "\n"
            self.device.clear()

            idn_str = self.device.query("*IDN?").strip()
            self.idn = idn_str
            self.is_connected = True
            self.last_config = config_source.copy()
            self._log("INFO", f"成功連線至: {self.idn}")

            self.reset_system()
            return True

        except Exception as e:
            self.is_connected = False
            self.idn = None
            self._log("ERROR", f"連線失敗: {e}")
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
