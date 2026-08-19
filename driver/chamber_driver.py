# -*- coding: utf-8 -*-
"""driver/chamber_driver.py

Chamber communication diagnostics update (202606021625):
- Treat serial-port-open and telemetry-read success as separate states.
- Add full TX/RX ASCII + HEX diagnostics for the RS-485 ASCII protocol.
- Support FCS probing modes for on-site diagnosis; field tests confirmed
  XOR8 including @ is the active FCS mode for Signal 01.
- Parse Signal 01 fixed-width hexadecimal PV/SV fields per the chamber manual.
- Keep the model/driver layer free of PyQt imports.
- Guard serial transactions with a non-blocking IO lock so repeated UI edits or
  simultaneous main-window polling cannot freeze the GUI.
- Log complete TX/RX/FCS context for every chamber setpoint write failure so
  GUI dialogs can remain concise while logs remain scientifically diagnostic.
"""

from __future__ import annotations

import time
import traceback
import threading
from typing import Dict, Iterable, Optional, Tuple

import serial


class ChamberDriver:
    """RS-485/RS-232 ASCII driver for the temperature-humidity chamber.

    The vendor manual provided by the operator specifies 9600 bps, 8E1,
    half-duplex communication, CR+LF for TX termination, CR for RX termination,
    and Signal ``01`` for analog PV/SV data.  This driver intentionally separates
    three states: serial open, raw protocol response, and successfully parsed
    telemetry.  The GUI should mark the chamber as ready only after telemetry is
    parsed.
    """

    #: FCS modes exposed only for diagnostics.  Field diagnostics on 2026-06-02
    #: confirmed that Signal 01 responds to XOR8 including the leading ``@``.
    #: Put the confirmed mode first to avoid unnecessary timeout delays.
    FCS_MODES = (
        "xor8_include_at",
        "sum8_include_at",
        "xor8_exclude_at",
        "sum8_exclude_at",
        "lrc8_include_at",
        "no_fcs",
    )

    FCS_LABELS = {
        "sum8_include_at": "SUM8 including '@' (current legacy mode)",
        "sum8_exclude_at": "SUM8 excluding '@'",
        "xor8_include_at": "XOR8 including '@'",
        "xor8_exclude_at": "XOR8 excluding '@'",
        "lrc8_include_at": "LRC8 / two's complement including '@'",
        "no_fcs": "No FCS diagnostic frame",
    }

    def __init__(self, station_id: int = 1, log_manager=None, fcs_mode: str = "xor8_include_at"):
        """Create a chamber driver.

        Args:
            station_id: Communication station number shown as two ASCII digits.
            log_manager: Optional ReliabilityX log manager.
            fcs_mode: Default FCS calculation mode.  Field diagnostics showed the
                chamber replies to ``xor8_include_at`` for Signal ``01``;
                diagnostics can still probe additional modes.
        """
        self.ser = None
        self.port = None
        self.baudrate = 9600
        self.station_id = str(station_id).zfill(2)
        self.log_mgr = log_manager
        self.fcs_mode = fcs_mode if fcs_mode in self.FCS_MODES else "xor8_include_at"
        self.last_transaction: Dict[str, object] = {}
        self.last_status: Optional[Dict[str, float]] = None
        self.last_protocol_ok = False
        self.last_error = ""
        self._io_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------
    def _log_info(self, message: str) -> None:
        """Write an informational driver event."""
        if self.log_mgr and hasattr(self.log_mgr, "log_info"):
            self.log_mgr.log_info(message)
        else:
            print(f"[Chamber][INFO] {message}")

    def _log_warning(self, message: str) -> None:
        """Write a warning driver event."""
        if self.log_mgr and hasattr(self.log_mgr, "log_warning"):
            self.log_mgr.log_warning(message)
        else:
            print(f"[Chamber][WARNING] {message}")

    def _log_error(self, message: str) -> None:
        """Write an error driver event."""
        if self.log_mgr and hasattr(self.log_mgr, "log_error"):
            try:
                self.log_mgr.log_error(message)
            except TypeError:
                self.log_mgr.log_error(str(message))
        else:
            print(f"[Chamber][ERROR] {message}")

    # ------------------------------------------------------------------
    # Connection state
    # ------------------------------------------------------------------
    def connect(self, port: str, baudrate: int = 9600, parity=serial.PARITY_EVEN) -> bool:
        """Open the USB/RS-485 serial port using manual-specified 8E1 defaults.

        Args:
            port: Windows COM port, for example ``COM8``.
            baudrate: Communication baudrate.  Manual default is 9600.
            parity: Serial parity.  Manual default is even parity.

        Returns:
            bool: True when the serial port is open.  This does *not* imply that
            telemetry has been successfully read.
        """
        try:
            with self._io_lock:
                if self.ser and self.ser.is_open:
                    self.ser.close()

                self.port = str(port).strip()
                self.baudrate = int(baudrate)
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=parity,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1.5,
                    write_timeout=1.5,
                )
                ok = bool(self.ser and self.ser.is_open)
                if ok:
                    self._log_info(f"Chamber serial open: {self.port} @ {self.baudrate}, 8E1, TX=CRLF, RX=CR")
                return ok
        except Exception as exc:
            self.last_error = f"Serial open failed: {exc}"
            self._log_error(self.last_error)
            return False

    def disconnect(self) -> None:
        """Close the chamber serial port if it is open."""
        with self._io_lock:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.last_protocol_ok = False

    def close(self) -> None:
        """Alias for shutdown code paths that call ``close``."""
        self.disconnect()

    def is_connected(self) -> bool:
        """Return whether the serial port is open, not whether telemetry is valid."""
        try:
            return bool(self.ser and self.ser.is_open)
        except Exception:
            return False

    def is_telemetry_ready(self) -> bool:
        """Return whether the latest protocol/telemetry read succeeded."""
        return bool(self.is_connected() and self.last_protocol_ok and self.last_status)

    # ------------------------------------------------------------------
    # Frame / FCS helpers
    # ------------------------------------------------------------------
    def _calculate_fcs(self, command_string: str, mode: Optional[str] = None) -> str:
        """Calculate a two-character FCS using the requested diagnostic mode.

        Args:
            command_string: ASCII frame body beginning with ``@``.
            mode: One of ``FCS_MODES``.

        Returns:
            str: Two uppercase hexadecimal characters.  ``no_fcs`` returns an
            empty string and is only used for diagnostics.
        """
        selected = mode or self.fcs_mode
        if selected == "no_fcs":
            return ""

        payload = command_string
        if selected.endswith("exclude_at") and payload.startswith("@"):
            payload = payload[1:]

        if selected.startswith("xor8"):
            value = 0
            for char in payload:
                value ^= ord(char)
            return f"{value & 0xFF:02X}"

        total = sum(ord(char) for char in payload)
        if selected.startswith("lrc8"):
            return f"{(-total) & 0xFF:02X}"
        return f"{total & 0xFF:02X}"

    def _build_command(self, signal_id: str, data_segment: str = "", mode: Optional[str] = None) -> Tuple[str, bytes]:
        """Build one complete TX command with CR+LF termination."""
        signal = str(signal_id).strip().upper()
        data = str(data_segment or "").strip().upper()
        base_cmd = f"@{self.station_id}{signal}{data}"
        fcs = self._calculate_fcs(base_cmd, mode)
        full_cmd = f"{base_cmd}{fcs}*\r\n"
        return full_cmd, full_cmd.encode("ascii", errors="ignore")

    @staticmethod
    def _bytes_to_hex(data: bytes) -> str:
        """Format raw bytes for operator-visible diagnostics."""
        return " ".join(f"{byte:02X}" for byte in data) if data else ""

    @staticmethod
    def _safe_ascii(data: bytes) -> str:
        """Decode bytes while preserving enough context for diagnostics."""
        return data.decode("ascii", errors="replace").replace("\r", "\\r").replace("\n", "\\n")

    def _validate_response_fcs(self, response: str, mode: Optional[str] = None) -> bool:
        """Validate response FCS when a candidate mode is known."""
        selected = mode or self.fcs_mode
        if selected == "no_fcs":
            return True
        clean = str(response or "").strip()
        if "*" not in clean:
            return False
        content, _tail = clean.split("*", 1)
        if len(content) < 3:
            return False
        actual = content[-2:].upper()
        data_part = content[:-2]
        if not all(c in "0123456789ABCDEFabcdef" for c in actual):
            return False
        return actual == self._calculate_fcs(data_part, selected)

    def _transaction(self, signal_id: str, data_segment: str = "", mode: Optional[str] = None) -> Dict[str, object]:
        """Send one frame and capture full TX/RX diagnostics.

        Args:
            signal_id: Two-character signal number, for example ``01``.
            data_segment: Optional command data segment.
            mode: FCS mode for this trial.

        Returns:
            dict: Diagnostic payload containing TX/RX ASCII, HEX, timeout flag,
            raw response, FCS validity, and error text.
        """
        selected = mode or self.fcs_mode
        full_cmd, tx_bytes = self._build_command(signal_id, data_segment, selected)
        result: Dict[str, object] = {
            "mode": selected,
            "mode_label": self.FCS_LABELS.get(selected, selected),
            "tx_ascii": self._safe_ascii(tx_bytes),
            "tx_hex": self._bytes_to_hex(tx_bytes),
            "rx_ascii": "",
            "rx_hex": "",
            "response": "",
            "timeout": False,
            "fcs_valid": False,
            "error": "",
        }

        acquired = self._io_lock.acquire(blocking=False)
        if not acquired:
            result["error"] = "Serial transaction busy; skipped to keep GUI responsive."
            self.last_transaction = result
            return result

        try:
            if not self.ser or not self.ser.is_open:
                result["error"] = "Serial port is not open."
                self.last_transaction = result
                return result

            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                self.ser.write(tx_bytes)
                self.ser.flush()
                rx_bytes = self.ser.read_until(b"\r")
                result["rx_hex"] = self._bytes_to_hex(rx_bytes)
                result["rx_ascii"] = self._safe_ascii(rx_bytes)

                if not rx_bytes:
                    result["timeout"] = True
                    result["error"] = "No Response / Timeout"
                else:
                    response = rx_bytes.decode("ascii", errors="ignore").strip()
                    result["response"] = response
                    result["fcs_valid"] = self._validate_response_fcs(response, selected)
                    if not response.startswith("@"): 
                        result["error"] = "Response does not start with '@'."
                    elif not result["fcs_valid"]:
                        result["error"] = "Response received, but FCS check did not pass for this mode."
            except Exception as exc:
                result["error"] = f"Serial transaction error: {exc}"
                result["traceback"] = traceback.format_exc()

            self.last_transaction = result
            return result
        finally:
            self._io_lock.release()
    # ------------------------------------------------------------------
    # Operator diagnostics
    # ------------------------------------------------------------------
    def split_manual_input(self, command_text: str) -> Tuple[str, str]:
        """Split manual debug input into signal ID and data segment.

        Args:
            command_text: Text typed by the operator.  The first two characters
                are treated as Signal ID; remaining characters are sent as data.

        Returns:
            tuple[str, str]: ``(signal_id, data_segment)``.
        """
        text = str(command_text or "").strip().upper().replace(" ", "")
        if len(text) <= 2:
            return text, ""
        return text[:2], text[2:]

    def diagnose_signal(self, signal_id: str = "01", data_segment: str = "") -> Dict[str, object]:
        """Probe all supported FCS modes for one signal.

        Args:
            signal_id: Signal number such as ``01``.
            data_segment: Optional data segment.

        Returns:
            dict: A diagnostic bundle with one trial per FCS mode.
        """
        trials = []
        ok_trial = None
        for mode in self.FCS_MODES:
            trial = self._transaction(signal_id, data_segment, mode)
            trials.append(trial)
            response = str(trial.get("response") or "")
            if response.startswith("@"):
                parsed = self._parse_status_response(response) if signal_id == "01" else None
                if signal_id != "01" or parsed is not None:
                    ok_trial = trial
                    self.fcs_mode = mode
                    if parsed is not None:
                        self.last_status = parsed
                        self.last_protocol_ok = True
                    break
        if ok_trial is None:
            self.last_protocol_ok = False
            self.last_status = None
        return {"ok": ok_trial is not None, "selected_mode": self.fcs_mode, "trials": trials, "ok_trial": ok_trial}

    def format_diagnostic_report(self, diagnostic: Dict[str, object]) -> str:
        """Format a multi-line diagnostic report for the GUI debug terminal."""
        lines = [
            "[CHAMBER DIAGNOSTIC] RS-485 ASCII | 9600 8E1 | TX CR+LF | RX CR",
            f"Port={self.port or '-'} | Baud={self.baudrate} | Station ID={self.station_id} | Active FCS={self.fcs_mode}",
        ]
        for trial in diagnostic.get("trials", []) or []:
            lines.extend([
                f"--- FCS mode: {trial.get('mode')} | {trial.get('mode_label')} ---",
                f"TX ASCII: {trial.get('tx_ascii', '')}",
                f"TX HEX  : {trial.get('tx_hex', '')}",
                f"RX ASCII: {trial.get('rx_ascii', '') or '(none)'}",
                f"RX HEX  : {trial.get('rx_hex', '') or '(none)'}",
                f"Result  : {'OK/selected' if trial is diagnostic.get('ok_trial') else (trial.get('error') or 'Response received')}",
            ])
        if not diagnostic.get("ok"):
            lines.append("[判斷] COM port 已開啟，但 Signal 沒有可解析回應；請檢查站號、RS485 A/B、Remote/通訊啟用，以及 FCS 演算法頁面。")
        return "\n".join(lines)

    def send_manual_command(self, signal_id: str, data_segment: str = "") -> str:
        """Send one manual command and return a legacy short response string."""
        signal, data = self.split_manual_input(signal_id + str(data_segment or ""))
        trial = self._transaction(signal, data, self.fcs_mode)
        if trial.get("response"):
            return str(trial.get("response"))
        return str(trial.get("error") or "No Response / Timeout")

    def send_manual_command_detailed(self, command_text: str) -> str:
        """Send a manual command and return full TX/RX diagnostics.

        Args:
            command_text: Operator input.  Example: ``01``.

        Returns:
            str: Multi-line report suitable for a QTextEdit terminal.
        """
        signal, data = self.split_manual_input(command_text)
        if not signal:
            return "[錯誤] Signal ID 不可為空。"
        diagnostic = self.diagnose_signal(signal, data)
        return self.format_diagnostic_report(diagnostic)

    # ------------------------------------------------------------------
    # Telemetry and control
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_hex_word(word: str, *, signed: bool = False, scale: float = 100.0) -> Optional[float]:
        """Parse one fixed-width hexadecimal analog word from Signal ``01``.

        The chamber manual's analog-data frame stores PV/SV values as four
        ASCII hexadecimal characters.  Temperature uses signed 16-bit values
        scaled by 100.  Humidity is unsigned and also scaled by 100.  ``7FFF``
        and dash-filled fields are treated as not available because field data
        shows humidity SV may be returned as ``7FFF`` when that loop is unused.

        Args:
            word: Four-character hexadecimal field.
            signed: Whether to decode as two's-complement signed 16-bit.
            scale: Engineering scale divisor.

        Returns:
            Parsed value, or ``None`` when the chamber reports an invalid/unused
            sentinel field.
        """
        token = str(word or "").strip().upper()
        if not token or set(token) == {"-"} or token in {"7FFF", "FFFF"}:
            return None
        if len(token) != 4 or any(char not in "0123456789ABCDEF" for char in token):
            raise ValueError(f"invalid hex analog word: {word!r}")
        value = int(token, 16)
        if signed and value >= 0x8000:
            value -= 0x10000
        return value / float(scale)

    def _parse_status_response(self, response: str) -> Optional[Dict[str, Optional[float]]]:
        """Parse Signal ``01`` analog PV/SV response.

        The response is a fixed-width RS-485 ASCII frame.  Based on the manual
        and field response example, the first fields are:

        ``@`` + station(2) + signal(2) + temp_pv(4 hex) + hum_pv(4 hex)
        + temp_sv(4 hex) + hum_sv(4 hex) + ... + fcs(2) + ``*``.

        Example field response from the chamber::

            @01010A9127100A917FFF...72*

        This is decoded as temperature PV 27.05 °C, humidity PV 100.00 %,
        temperature SV 27.05 °C, and humidity SV unavailable.

        Args:
            response: Raw ASCII response string beginning with ``@``.

        Returns:
            Parsed values in engineering units, or ``None`` when the frame is
            too short or not a Signal ``01`` response for the configured station.
        """
        frame = str(response or "").strip()
        if "*" in frame:
            frame = frame.split("*", 1)[0]
        if not frame.startswith(f"@{self.station_id}01"):
            return None
        if len(frame) < 21:
            self.last_error = f"Parse failed: Signal 01 frame too short | Raw={response}"
            self._log_warning(self.last_error)
            return None

        try:
            temp_pv = self._parse_hex_word(frame[5:9], signed=True)
            hum_pv = self._parse_hex_word(frame[9:13], signed=False)
            temp_sv = self._parse_hex_word(frame[13:17], signed=True)
            hum_sv = self._parse_hex_word(frame[17:21], signed=False)

            if temp_pv is None or hum_pv is None:
                self.last_error = f"Parse failed: PV field is unavailable | Raw={response}"
                self._log_warning(self.last_error)
                return None

            return {
                "temp_pv": temp_pv,
                "hum_pv": hum_pv,
                "temp_sv": temp_sv,
                "hum_sv": hum_sv,
            }
        except Exception as exc:
            self.last_error = f"Parse failed: {exc} | Raw={response}"
            self._log_warning(self.last_error)
            return None

    def read_status(self) -> Optional[Dict[str, float]]:
        """Read Signal 01 analog data using the currently selected FCS mode.

        Returns:
            Optional[dict]: Temperature/humidity PV/SV values, or ``None`` when
            serial communication, protocol response, or parsing failed.
        """
        trial = self._transaction("01", "", self.fcs_mode)
        response = str(trial.get("response") or "")
        parsed = self._parse_status_response(response)
        if parsed is None:
            self.last_protocol_ok = False
            self.last_status = None
            self.last_error = str(trial.get("error") or "No parsable telemetry response")
            return None
        self.last_protocol_ok = True
        self.last_status = parsed
        self.last_error = ""
        return parsed

    def test_telemetry(self, probe_all: bool = True) -> Tuple[bool, Optional[Dict[str, float]], str]:
        """Verify that the chamber can return parsable PV/SV telemetry.

        Args:
            probe_all: Whether to try diagnostic FCS modes before failing.

        Returns:
            tuple: ``(ok, status, diagnostic_report)``.
        """
        if not self.is_connected():
            return False, None, "Serial port is not open."

        if probe_all:
            diagnostic = self.diagnose_signal("01")
            report = self.format_diagnostic_report(diagnostic)
            status = self.last_status if diagnostic.get("ok") else None
            return bool(status), status, report

        status = self.read_status()
        return bool(status), status, self.format_diagnostic_report({"ok": bool(status), "trials": [self.last_transaction], "ok_trial": self.last_transaction if status else None})

    def _format_transaction_details(
        self,
        title: str,
        *,
        operation: str,
        signal_id: str,
        data_segment: str,
        trial: Dict[str, object],
        extra: Optional[Dict[str, object]] = None,
    ) -> str:
        """Format a transaction into a complete diagnostic log block.

        Args:
            title: Log block title, for example ``CHAMBER WRITE_SETPOINTS FAILED``.
            operation: Human-readable operation name.
            signal_id: Vendor signal number sent to the chamber.
            data_segment: ASCII data segment before FCS and terminator.
            trial: Transaction dictionary returned by ``_transaction``.
            extra: Optional additional key/value diagnostics.

        Returns:
            Multi-line string suitable for persistent log files.
        """
        lines = [
            f"[{title}]",
            f"Operation={operation}",
            f"Port={self.port or '-'} | Baud={self.baudrate} | Station ID={self.station_id} | Serial=8E1 | FCS={self.fcs_mode}",
            f"Signal={signal_id} | DataLength={len(str(data_segment or ''))} | DataSegment={data_segment or '(none)'}",
            f"TX ASCII: {trial.get('tx_ascii', '') or '(none)'}",
            f"TX HEX  : {trial.get('tx_hex', '') or '(none)'}",
            f"RX ASCII: {trial.get('rx_ascii', '') or '(none)'}",
            f"RX HEX  : {trial.get('rx_hex', '') or '(none)'}",
            f"Response: {trial.get('response', '') or '(none)'}",
            f"FCS valid: {trial.get('fcs_valid')}",
            f"Timeout: {trial.get('timeout')}",
            f"Failure reason: {trial.get('error', '') or '(none)'}",
        ]
        for key, value in (extra or {}).items():
            lines.append(f"{key}: {value}")
        if trial.get("traceback"):
            lines.append("Traceback:")
            lines.append(str(trial.get("traceback")))
        return "\n".join(lines)

    def write_setpoints(self, temp_sv: float, hum_sv: float) -> bool:
        """Write manual temperature/humidity setpoints with full failure logging.

        This method intentionally keeps the currently implemented legacy write
        signal so field testing can reveal the exact rejected frame.  If the
        chamber rejects the command, the persistent log records serial settings,
        Signal number, TX/RX ASCII, TX/RX HEX, FCS result, timeout state, and a
        protocol note.  The GUI should show a concise message and point the
        operator to the log.

        Args:
            temp_sv: Temperature setpoint in degree Celsius.
            hum_sv: Humidity setpoint in RH percent.

        Returns:
            bool: True when the chamber echoes the write-setpoint signal without
            transaction errors.
        """
        operation = "Chamber write_setpoints / manual SV send"
        signal_id = "05"
        data_segment = ""
        try:
            temp_value = float(temp_sv)
            hum_value = float(hum_sv)
            temp_str = f"{int(round(temp_value * 100)):06d}"
            hum_str = f"{int(round(hum_value * 100)):06d}"
            data_segment = f"{temp_str}{hum_str}"
        except Exception as exc:
            pseudo_trial: Dict[str, object] = {
                "tx_ascii": "",
                "tx_hex": "",
                "rx_ascii": "",
                "rx_hex": "",
                "response": "",
                "fcs_valid": False,
                "timeout": False,
                "error": f"Invalid setpoint input: {exc}",
                "traceback": traceback.format_exc(),
            }
            self.last_error = f"Chamber write_setpoints failed: invalid input ({exc})"
            self._log_error(self._format_transaction_details(
                "CHAMBER WRITE_SETPOINTS FAILED",
                operation=operation,
                signal_id=signal_id,
                data_segment=data_segment,
                trial=pseudo_trial,
                extra={
                    "Target Temp SV (degC)": temp_sv,
                    "Target Hum SV (%)": hum_sv,
                    "Safety action": "No command was sent.",
                },
            ))
            return False

        trial = self._transaction(signal_id, data_segment, self.fcs_mode)
        response = str(trial.get("response") or "")
        expected_prefix = f"@{self.station_id}{signal_id}"
        prefix_ok = response.startswith(expected_prefix)
        success = bool(prefix_ok and not trial.get("error"))

        common_extra = {
            "Target Temp SV (degC)": f"{float(temp_sv):.3f}",
            "Target Hum SV (%)": f"{float(hum_sv):.3f}",
            "Expected response prefix": expected_prefix,
            "Response prefix OK": prefix_ok,
            "Protocol note": "Current implementation sends legacy Signal 05. Manual pages indicate FIX setpoint may require Signal 15 and readback Signal 25; confirm payload format before changing production write command.",
        }

        if success:
            self.last_error = ""
            self._log_info(
                "[CHAMBER WRITE_SETPOINTS OK] "
                f"signal={signal_id} | target={float(temp_sv):.3f} °C / {float(hum_sv):.3f} % | "
                f"TX={trial.get('tx_ascii', '')} | RX={trial.get('rx_ascii', '')}"
            )
            return True

        if not response and not trial.get("error"):
            trial["error"] = "No response was received from chamber."
        elif response and not prefix_ok and not trial.get("error"):
            trial["error"] = f"Unexpected response prefix: {response!r}"

        reason = str(trial.get("error") or "Unknown chamber write failure")
        self.last_error = f"Chamber write_setpoints failed: {reason}"
        self._log_error(self._format_transaction_details(
            "CHAMBER WRITE_SETPOINTS FAILED",
            operation=operation,
            signal_id=signal_id,
            data_segment=data_segment,
            trial=trial,
            extra={
                **common_extra,
                "Safety action": "No setpoint change is assumed unless a valid write echo and readback confirmation are obtained.",
            },
        ))
        return False
