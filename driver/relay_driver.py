"""driver/relay_driver.py

ReliabilityX Pro Relay driver for Numato 64-Ch relay boards.
OI-054: require command echo, reject errors, and verify controller state masks.

Safety patch 2026-06-02:
- ``reset_all()`` now uses explicit Numato all-off command
  ``relay writeall 0000000000000000`` for 64 relay channels instead of the
  ambiguous ``reset`` command.
- Runtime relay settings are read from ``config.RELAY_CONFIG`` by default,
  including PORT, BAUDRATE, SAFE_MODE, IDENTIFIER, and TOTAL_CHANNELS.
- If the vector all-off command does not receive a valid prompt response, the
  driver falls back to per-channel ``relay off NN`` commands and does not issue
  ``reset``.
"""

import math
import time
import traceback
from typing import Any, Dict, Optional

import serial
import serial.tools.list_ports

import config


class RelayDriver:
    """Numato relay board driver with explicit all-off safety behavior.

    Args:
        baudrate: Optional baudrate override. If omitted, ``config.RELAY_CONFIG``
            is used.
        log_manager: Optional ReliabilityX Pro log manager.
    """

    def __init__(self, baudrate: Optional[int] = None, log_manager=None):
        self.ser = None
        self.log_mgr = log_manager
        self.is_connected = False
        self.scan_timeout_sec = 0.35
        self.command_timeout_sec = 0.35
        self.command_retry_delay_sec = 0.05

        relay_cfg = self._runtime_config()
        self.baudrate = int(baudrate or relay_cfg.get("BAUDRATE", 19200) or 19200)
        self.port = str(relay_cfg.get("PORT", "") or "").strip()
        self.identifier = str(relay_cfg.get("IDENTIFIER", "Numato") or "Numato")
        self.total_channels = int(relay_cfg.get("TOTAL_CHANNELS", 64) or 64)
        self.safe_mode = bool(relay_cfg.get("SAFE_MODE", True))

    def _runtime_config(self) -> Dict[str, Any]:
        """Return a normalized relay runtime config from config.py."""
        cfg = getattr(config, "RELAY_CONFIG", {})
        return cfg if isinstance(cfg, dict) else {}

    def _refresh_runtime_config(self, override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Refresh runtime config fields before connecting or switching relays.

        Args:
            override: Optional temporary config, typically from the config dialog
                connection test.

        Returns:
            Dict[str, Any]: Effective relay config.
        """
        base = self._runtime_config()
        effective = dict(base)
        if isinstance(override, dict):
            effective.update({k: v for k, v in override.items() if v not in (None, "")})

        try:
            self.baudrate = int(effective.get("BAUDRATE", self.baudrate) or self.baudrate)
        except (TypeError, ValueError):
            self.baudrate = 19200
        self.port = str(effective.get("PORT", self.port) or "").strip()
        self.identifier = str(effective.get("IDENTIFIER", self.identifier) or "Numato")
        try:
            self.total_channels = int(effective.get("TOTAL_CHANNELS", self.total_channels) or self.total_channels)
        except (TypeError, ValueError):
            self.total_channels = 64
        self.total_channels = max(1, min(self.total_channels, 256))
        self.safe_mode = bool(effective.get("SAFE_MODE", self.safe_mode))
        return effective

    def _log(self, level: str, message: str) -> None:
        """Log a driver message to the configured log manager or stdout."""
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
            print(f"[{level}] {message}")

    @staticmethod
    def _format_serial_ascii(payload: bytes) -> str:
        """Return serial bytes as readable ASCII with escaped terminators.

        Args:
            payload: Raw serial response bytes.

        Returns:
            str: Readable text, or ``(none)`` when no bytes were received.
        """
        if not payload:
            return "(none)"
        return (
            payload.decode(errors="replace")
            .replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
        )

    @staticmethod
    def _format_serial_hex(payload: bytes) -> str:
        """Return serial bytes as a space-separated hexadecimal string.

        Args:
            payload: Raw serial response bytes.

        Returns:
            str: Hexadecimal bytes, or ``(none)`` when the payload is empty.
        """
        return " ".join(f"{byte:02X}" for byte in payload) if payload else "(none)"

    @staticmethod
    def _describe_serial_port(port_info: Any) -> str:
        """Build a diagnostic description for a pyserial port record.

        Args:
            port_info: Object returned by ``serial.tools.list_ports.comports``.

        Returns:
            str: Device, description, hardware ID, vendor/product ID, and
            manufacturer fields when they are available.
        """
        device = str(getattr(port_info, "device", "") or "(unknown)")
        description = str(getattr(port_info, "description", "") or "(none)")
        hwid = str(getattr(port_info, "hwid", "") or "(none)")
        manufacturer = str(getattr(port_info, "manufacturer", "") or "(none)")
        vid = getattr(port_info, "vid", None)
        pid = getattr(port_info, "pid", None)
        vid_pid = (
            f"VID:PID={int(vid):04X}:{int(pid):04X}"
            if isinstance(vid, int) and isinstance(pid, int)
            else "VID:PID=(none)"
        )
        return (
            f"device={device} | description={description} | hwid={hwid} | "
            f"{vid_pid} | manufacturer={manufacturer}"
        )

    def auto_scan(self, temp_config: Optional[Dict[str, Any]] = None) -> bool:
        """Connect to the Numato relay board.

        If ``PORT`` is present in config_settings.json / temp_config, only that
        COM port is attempted. Otherwise all serial ports are scanned.

        Args:
            temp_config: Optional temporary relay configuration.

        Returns:
            bool: True when a compatible relay board is connected.
        """
        effective = self._refresh_runtime_config(temp_config)
        if temp_config and self.is_connected:
            self.close()

        configured_port = str(effective.get("PORT", "") or "").strip()
        scan_mode = "configured_port" if configured_port else "auto_scan"
        tx_payload = b"ver\r"
        self._log(
            "INFO",
            "[RELAY CONNECT] 開始連線"
            f" | mode={scan_mode}"
            f" | configured_port={configured_port or '(auto)'}"
            f" | baud={self.baudrate}"
            f" | identifier={self.identifier or 'Numato'}"
            f" | timeout={self.scan_timeout_sec:.2f}s"
            f" | safe_mode={self.safe_mode}",
        )

        try:
            detected_ports = list(serial.tools.list_ports.comports())
        except Exception as exc:
            detected_ports = []
            self._log(
                "ERROR",
                "[RELAY CONNECT] 無法列舉 Windows COM Port"
                f" | exception={type(exc).__name__}: {exc}"
                f"\nTraceback:\n{traceback.format_exc().strip()}",
            )

        if detected_ports:
            self._log("INFO", f"[RELAY CONNECT] Windows 偵測到 {len(detected_ports)} 個序列埠。")
            for port_info in detected_ports:
                self._log("INFO", f"[RELAY CONNECT] Port detected | {self._describe_serial_port(port_info)}")
        else:
            self._log(
                "WARNING",
                "[RELAY CONNECT] Windows/pyserial 未列舉到任何 COM Port。"
                "請檢查 Relay 供電、USB 資料線、USB 插槽、裝置管理員與 USB-to-Serial 驅動。",
            )

        if configured_port:
            ports_to_scan = [configured_port]
            detected_names = {
                str(getattr(port_info, "device", "") or "").casefold()
                for port_info in detected_ports
            }
            if configured_port.casefold() not in detected_names:
                self._log(
                    "WARNING",
                    "[RELAY CONNECT] 設定的 COM Port 不在目前 Windows 枚舉清單中，仍會嘗試開啟"
                    f" | configured_port={configured_port}",
                )
        else:
            ports_to_scan = [
                str(getattr(port_info, "device", "") or "").strip()
                for port_info in detected_ports
                if str(getattr(port_info, "device", "") or "").strip()
            ]

        if not ports_to_scan:
            self._log(
                "ERROR",
                "找不到 Numato Relay 設備。"
                " | reason=no_serial_ports"
                " | attempted_ports=0"
                " | action=先讓 Windows 裝置管理員辨識 Relay 的 COM Port，再重新連線。",
            )
            return False

        failures = []
        for port_name in ports_to_scan:
            temp_ser = None
            try:
                self._log(
                    "INFO",
                    "[RELAY CONNECT] 嘗試 Relay probe"
                    f" | port={port_name}"
                    f" | baud={self.baudrate}"
                    f" | TX_ASCII={self._format_serial_ascii(tx_payload)}"
                    f" | TX_HEX={self._format_serial_hex(tx_payload)}",
                )
                temp_ser = serial.Serial(
                    port_name,
                    self.baudrate,
                    timeout=self.scan_timeout_sec,
                    write_timeout=self.scan_timeout_sec,
                )
                try:
                    temp_ser.reset_input_buffer()
                    temp_ser.reset_output_buffer()
                except Exception:
                    pass

                temp_ser.write(tx_payload)
                response_bytes = temp_ser.read(100)
                response = response_bytes.decode(errors="ignore")
                identifier_ok = self.identifier in response if self.identifier else "Numato" in response

                if identifier_ok or "Numato" in response or "0000" in response:
                    if identifier_ok:
                        validation = "configured_identifier_matched"
                    elif "Numato" in response:
                        validation = "Numato_fallback_matched"
                    else:
                        validation = "0000_fallback_matched"
                    self._log(
                        "INFO",
                        "[RELAY CONNECT] Relay probe 回覆有效"
                        f" | port={port_name}"
                        f" | RX_ASCII={self._format_serial_ascii(response_bytes)}"
                        f" | RX_HEX={self._format_serial_hex(response_bytes)}"
                        f" | bytes={len(response_bytes)}"
                        f" | validation={validation}",
                    )
                    temp_ser.timeout = self.command_timeout_sec
                    temp_ser.write_timeout = self.command_timeout_sec
                    self.ser = temp_ser
                    self.is_connected = True
                    if not self.reset_all():
                        self.is_connected = False
                        self.ser = None
                        raise IOError("Relay identified but all-off readback failed; connection not ready")
                    self._log(
                        "INFO",
                        f"成功連線至 Relay 板: {port_name} | baud={self.baudrate} | safe_mode={self.safe_mode} | all_off=verified",
                    )
                    return True

                if response_bytes:
                    failure_reason = "identifier_mismatch"
                    validation = (
                        f"expected '{self.identifier or 'Numato'}', "
                        "and fallback markers 'Numato'/'0000' were absent"
                    )
                else:
                    failure_reason = "timeout_or_no_response"
                    validation = "0 bytes received before timeout"
                failures.append(f"{port_name}: {failure_reason}")
                self._log(
                    "WARNING",
                    "[RELAY CONNECT] Relay probe 未通過"
                    f" | port={port_name}"
                    f" | baud={self.baudrate}"
                    f" | RX_ASCII={self._format_serial_ascii(response_bytes)}"
                    f" | RX_HEX={self._format_serial_hex(response_bytes)}"
                    f" | bytes={len(response_bytes)}"
                    f" | reason={failure_reason}"
                    f" | validation={validation}"
                    " | safety=未接受此連線，未送出任何 Relay 狀態切換指令。",
                )
            except Exception as exc:
                failure_reason = f"{type(exc).__name__}: {exc}"
                failures.append(f"{port_name}: {failure_reason}")
                self._log(
                    "ERROR",
                    "[RELAY CONNECT] Relay probe 發生例外"
                    f" | port={port_name}"
                    f" | baud={self.baudrate}"
                    f" | exception={failure_reason}"
                    " | safety=未確認 Relay 就緒；若已識別設備，可能已嘗試 all-off，請查看 TX/RX 與讀回紀錄。"
                    f"\nTraceback:\n{traceback.format_exc().strip()}",
                )
            finally:
                if temp_ser is not None and temp_ser is not self.ser:
                    try:
                        temp_ser.close()
                    except Exception as close_exc:
                        self._log(
                            "WARNING",
                            "[RELAY CONNECT] 關閉失敗的 probe port 時發生例外"
                            f" | port={port_name}"
                            f" | exception={type(close_exc).__name__}: {close_exc}",
                        )

        self._log(
            "ERROR",
            "找不到 Numato Relay 設備。"
            f" | mode={scan_mode}"
            f" | attempted_ports={len(ports_to_scan)}"
            f" | failures={'; '.join(failures) or '(none recorded)'}"
            " | action=依上方逐埠紀錄檢查 COM 埠占用/權限、baudrate、USB 驅動、線材，"
            "以及 ver 指令回覆是否包含設定的 identifier。",
        )
        return False

    def prepare_for_measurement(self) -> None:
        """Force a safe all-off relay state before a measurement sequence."""
        self._log("INFO", "[安全機制] 執行量測前全面清零...")
        self.reset_all()
        time.sleep(0.05)

    def _send_command(self, cmd: str, retries: int = 0) -> bool:
        """Send a write command and require an error-free echo and prompt.

        Args:
            cmd: Numato command without terminator.
            retries: Additional attempts after invalid responses.

        Returns:
            bool: Whether a complete, matching acknowledgement was received.
        """
        if not self.is_connected or not self.ser:
            self._log("ERROR", "Relay 未連線，無法發送指令。")
            return False

        full_cmd = f"{cmd}\r".encode()
        for attempt in range(retries + 1):
            try:
                try:
                    self.ser.reset_input_buffer()
                except Exception:
                    pass

                self.ser.write(full_cmd)
                response = self.ser.read_until(b">").decode("ascii")
                self._log("INFO", f"[RELAY TX/RX] port={getattr(self.ser, 'port', '?')} baud={getattr(self.ser, 'baudrate', '?')} TX={full_cmd!r} RX={response!r}")
                lines = [line.strip() for line in response.replace(">", "\n").splitlines() if line.strip()]
                if response.rstrip().endswith(">") and lines == [cmd]:
                    return True

                self._log(
                    "WARNING",
                    f"Relay 指令 '{cmd}' 無效回饋: '{response}'. 第 {attempt + 1} 次嘗試...",
                )
            except serial.SerialException as e:
                self._log("ERROR", f"發送 Relay 指令 '{cmd}' 時發生序列埠錯誤: {e}. 連線中斷。\n{traceback.format_exc()}")
                self.is_connected = False
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                return False
            except Exception as e:
                self._log("ERROR", f"發送 Relay 指令 '{cmd}' 時發生未知錯誤: {e}\n{traceback.format_exc()}")
                return False

            if attempt < retries:
                time.sleep(self.command_retry_delay_sec)

        self._log("ERROR", f"Relay 指令 '{cmd}' 在 {retries + 1} 次嘗試後最終失敗。")
        return False

    def verify_state(self, channels):
        """Read the complete controller mask and compare it with selected relays.

        Args:
            channels: Iterable of zero-based decimal relay IDs expected ON.

        Returns:
            bool: Exact controller-reported match; not proof of contact isolation.
        """
        raw = b""
        try:
            selected = set(channels)
            if any(not 0 <= pin < self.total_channels for pin in selected):
                raise ValueError(f"Relay IDs out of range: {selected}")
            expected = sum(1 << pin for pin in selected)
            if not self.is_connected or not self.ser:
                raise IOError("Relay disconnected")
            self.ser.reset_input_buffer()
            self.ser.write(b"relay readall\r")
            raw = self.ser.read_until(b">")
            response = raw.decode("ascii")
            lines = [s.strip() for s in response.replace(">", "\n").splitlines() if s.strip()]
            digits = len(self._all_off_payload())
            if (not response.rstrip().endswith(">") or len(lines) != 2
                    or lines[0] != "relay readall" or len(lines[1]) != digits
                    or any(c not in "0123456789abcdefABCDEF" for c in lines[1])):
                raise ValueError("Invalid relay readall frame/echo/mask")
            actual = int(lines[1], 16)
            if actual != expected:
                raise ValueError(f"Relay mask mismatch expected={expected:0{digits}X} actual={actual:0{digits}X}")
            self._log("INFO", f"[RELAY VERIFY] TX='relay readall\\r' RX={raw!r} expected={expected:0{digits}X} controller_state=confirmed")
            return True
        except Exception as exc:
            self._log("ERROR", f"[RELAY VERIFY] port={getattr(self.ser, 'port', '?')} TX='relay readall\\r' RX={raw!r} {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            return False

    def switch_on(self, channel: int) -> bool:
        """Turn on one physical relay channel."""
        return self._send_command(f"relay on {int(channel):02d}")

    def switch_off(self, channel: int) -> bool:
        """Turn off one physical relay channel."""
        return self._send_command(f"relay off {int(channel):02d}")

    def switch_pair(self, battery_id: int, state) -> bool:
        """Switch a logical battery pair using hardware_map.json.

        Args:
            battery_id: Logical channel/battery id.
            state: True/"ON" to turn on; False/"OFF" to turn off.

        Returns:
            bool: True if both physical relay commands succeeded.
        """
        self._refresh_runtime_config()
        is_turning_on = (isinstance(state, str) and state.upper() == "ON") or state

        if is_turning_on and self.safe_mode:
            self._log("INFO", f"[安全機制] Channel {battery_id}: 執行 '先斷後開' -> 全板 all-off。")
            if not self.reset_all():
                self._log("ERROR", f"為通道 {battery_id} 執行 '先斷後開' 失敗，無法 all-off Relay。")
                return False
            time.sleep(0.03)
        elif is_turning_on:
            self._log("WARNING", f"[安全模式關閉] Channel {battery_id}: 未先執行 reset_all，僅供受控診斷使用。")

        mapping = config.HARDWARE_MAP.get(f"CH{battery_id}")
        if not mapping:
            self._log("ERROR", f"在 hardware_map.json 中找不到通道 {battery_id} 的映射。")
            return False

        ch_pos, ch_neg = mapping["pos"], mapping["neg"]

        if is_turning_on:
            res1 = self.switch_on(ch_pos)
            res2 = self.switch_on(ch_neg)
            action_log = "ON"
        else:
            res1 = self.switch_off(ch_pos)
            res2 = self.switch_off(ch_neg)
            action_log = "OFF"

        success = res1 and res2
        log_level = "INFO" if success else "ERROR"
        self._log(
            log_level,
            f"切換邏輯通道 {battery_id} (實體: {ch_pos:02d}/{ch_neg:02d}) -> {action_log}. "
            f"結果: {'成功' if success else '失敗'}",
        )

        return success

    def _all_off_payload(self) -> str:
        """Return the hex payload for Numato ``relay writeall`` all-off."""
        hex_digits = max(1, int(math.ceil(self.total_channels / 4.0)))
        return "0" * hex_digits

    def reset_all(self) -> bool:
        """Turn off every relay using explicit Numato all-off semantics.

        Returns:
            bool: True when the vector all-off command or the fallback per-relay
            all-off sequence succeeds.
        """
        self._refresh_runtime_config()
        command = f"relay writeall {self._all_off_payload()}"
        if self._send_command(command, retries=1) and self.verify_state(set()):
            self._log("INFO", f"Relay all-off 完成: {command}")
            return True

        self._log("WARNING", "relay writeall all-off 未取得有效回饋，改用逐路 relay off fallback。")
        fallback_ok = True
        for channel in range(self.total_channels):
            fallback_ok = self.switch_off(channel) and fallback_ok
        fallback_ok = self.verify_state(set()) and fallback_ok
        if fallback_ok:
            self._log("INFO", "Relay all-off fallback 完成：所有 relay off 指令已送出。")
        else:
            self._log("ERROR", "Relay all-off fallback 失敗：至少一個 relay off 指令未成功。")
        return fallback_ok

    def close(self) -> None:
        """Safely turn all relays off and close the serial connection."""
        if self.ser and self.ser.is_open:
            try:
                self.reset_all()
            except Exception:
                pass
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.is_connected = False
        self._log("INFO", "Relay 串口已關閉。")
