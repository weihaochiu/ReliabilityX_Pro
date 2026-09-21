"""IV curve export, using measured raw voltage for v2 diagnostics (OI-054)."""

import csv
import datetime
import re
import threading
from itertools import zip_longest
from pathlib import Path

from core.measurement_schema import IV_PARAMETER_KEYS, SUMMARY_SUB_HEADERS, IV_CURVE_POINT_HEADERS, SCHEMA_VERSION
from core.numeric_utils import parse_float_or_none


class IVCurveLogger:
    """
    負責處理單次 I-V 掃描的原始數據存檔，並產生符合 temp 範例格式的 CSV 檔案。
    重點：
    1. 固定輸出 19 欄。
    2. 優先相容既有扁平 analysis_results key（例如 Voc_F_Raw）。
    3. 同時相容巢狀 analysis_results 結構（例如 analysis_results['Forward_Raw']['Voc']）。
    4. 資料列維持 temp 範例欄名、欄序、單位與分隔欄配置。
    """

    SUMMARY_COLS = 19
    SUMMARY_PARAMS = IV_PARAMETER_KEYS
    SUMMARY_HEADERS = SUMMARY_SUB_HEADERS
    POINT_HEADERS = IV_CURVE_POINT_HEADERS
    SCHEMA_VERSION = SCHEMA_VERSION
    SUMMARY_SUFFIXES = ["F_Raw", "R_Raw", "F_Corr", "R_Corr"]
    SUMMARY_ROW_LABELS = {
        "F_Raw": "Forward_Raw",
        "R_Raw": "Reversed_Raw",
        "F_Corr": "Forward_Corr",
        "R_Corr": "Reversed_Corr",
    }

    def __init__(self, root_path="data"):
        self.root_path = Path(root_path)
        self.lock = threading.Lock()

    def _sanitize_name(self, name, max_len=50):
        if not isinstance(name, str):
            name = str(name)
        name = re.sub(r'[\\/:*?"<>| ]', "_", name)
        name = re.sub(r'[^\w\u4e00-\u9fff.-]', '', name)
        name = re.sub(r'_+', '_', name)
        name = name[:max_len].strip('._ ')
        return name or "unnamed_item"

    @staticmethod
    def _solar_output_power(voltage, current):
        return -(voltage * current)

    @staticmethod
    def _is_blank(value):
        return value is None or value == ""

    def _first_non_blank(self, *values):
        for value in values:
            if not self._is_blank(value):
                return value
        return ""

    def _coerce_datetime(self, value):
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            return datetime.datetime.combine(value, datetime.time())
        if isinstance(value, str) and value.strip():
            text = value.strip()
            for parser in (
                datetime.datetime.fromisoformat,
                lambda x: datetime.datetime.strptime(x, "%Y/%m/%d %H:%M:%S"),
                lambda x: datetime.datetime.strptime(x, "%Y/%m/%d %H:%M"),
                lambda x: datetime.datetime.strptime(x, "%Y-%m-%d %H:%M:%S"),
                lambda x: datetime.datetime.strptime(x, "%Y-%m-%d %H:%M"),
            ):
                try:
                    return parser(text)
                except Exception:
                    continue
        return datetime.datetime.now()

    def _coerce_float(self, value, default=None, *, field_name: str = ""):
        number = parse_float_or_none(value, field_name=field_name, context="IVCurveLogger", warn_invalid=True)
        return default if number is None else number

    def _pad(self, row, total_len=None):
        total_len = total_len or self.SUMMARY_COLS
        row = list(row)
        if len(row) < total_len:
            row.extend([""] * (total_len - len(row)))
        return row[:total_len]

    def _get_meta(self, data_dict, *keys, default=""):
        for key in keys:
            if key in data_dict and not self._is_blank(data_dict.get(key)):
                return data_dict.get(key)
        return default

    def _get_env_value(self, data_dict, env_data, *keys):
        env_data = env_data or {}
        for key in keys:
            if key in env_data and not self._is_blank(env_data.get(key)):
                return env_data.get(key)
        for key in keys:
            if key in data_dict and not self._is_blank(data_dict.get(key)):
                return data_dict.get(key)
        return ""

    def _get_analysis_value(self, analysis_results, param, suffix):
        analysis_results = analysis_results or {}

        flat_keys = [
            f"{param}_{suffix}",
            f"{param.lower()}_{suffix}",
            f"{param.upper()}_{suffix}",
        ]
        for key in flat_keys:
            if key in analysis_results and not self._is_blank(analysis_results.get(key)):
                return analysis_results.get(key)

        container_names = {
            "F_Raw": ["Forward_Raw", "F_Raw", "forward_raw", "forwardRaw"],
            "R_Raw": ["Reversed_Raw", "Reverse_Raw", "R_Raw", "reversed_raw", "reverse_raw", "reversedRaw"],
            "F_Corr": ["Forward_Corr", "F_Corr", "forward_corr", "forwardCorr"],
            "R_Corr": ["Reversed_Corr", "Reverse_Corr", "R_Corr", "reversed_corr", "reverse_corr", "reversedCorr"],
        }.get(suffix, [suffix])

        param_aliases = [
            param,
            param.lower(),
            param.upper(),
        ]
        if param == "Rsh":
            param_aliases.extend(["Rsh_kOhm", "rsh_kohm", "RSH_KOHM"])

        for container_name in container_names:
            sub = analysis_results.get(container_name)
            if isinstance(sub, dict):
                for alias in param_aliases:
                    if alias in sub and not self._is_blank(sub.get(alias)):
                        return sub.get(alias)
        return ""

    def _fmt_meta(self, value):
        return "" if value is None else str(value)

    def _fmt_summary(self, value):
        number = self._coerce_float(value, default=None)
        if number is None:
            return ""
        text = f"{number:.6f}".rstrip("0").rstrip(".")
        if text == "-0":
            return "0"
        return text

    def _fmt_data(self, value):
        number = self._coerce_float(value, default=None)
        if number is None:
            return ""
        if number == 0:
            return "0"
        abs_number = abs(number)
        if 1e-3 <= abs_number < 1e4:
            text = f"{number:.6g}"
        else:
            text = f"{number:.2E}"
        return text.replace("e", "E")

    def _extract_point(self, point):
        """Normalize a point using measured voltage, with legacy schema fallback.

        Args:
            point: Current or historical IV point dictionary.

        Returns:
            Normalized point tuple, or None for unusable data.
        """
        if not point:
            return None
        v_raw = self._first_non_blank(point.get("v_msd"), point.get("v_src"), point.get("voltage_raw"), point.get("v_raw"), point.get("voltage"))
        i_raw = self._first_non_blank(point.get("i_msd"), point.get("current_raw"), point.get("i_raw"), point.get("current"))
        v_corr = self._first_non_blank(point.get("v_corr"), point.get("voltage_corr"), point.get("v_corrected"), v_raw)
        i_corr = self._first_non_blank(point.get("i_corr"), point.get("current_corr"), point.get("i_corrected"), i_raw)

        v_raw = self._coerce_float(v_raw, default=None)
        i_raw = self._coerce_float(i_raw, default=None)
        v_corr = self._coerce_float(v_corr, default=None)
        i_corr = self._coerce_float(i_corr, default=None)

        if v_raw is None or i_raw is None or v_corr is None or i_corr is None:
            return None
        return v_raw, i_raw, v_corr, i_corr

    def save_iv_curve(self, data_dict, fwd_data, rev_data, analysis_results, env_data=None):
        data_dict = data_dict or {}
        analysis_results = analysis_results or {}
        env_data = env_data or {}

        start_time = self._coerce_datetime(self._get_meta(data_dict, "start_time", "measurement_start_time", default=datetime.datetime.now()))
        timestamp_str = start_time.strftime("%Y%m%d_%H%M%S")

        user_original = self._get_meta(data_dict, "user", default="default_user")
        project_original = self._get_meta(data_dict, "project", default="default_project")
        device_original = self._get_meta(data_dict, "device_name", default="Device")

        user = self._sanitize_name(user_original)
        project = self._sanitize_name(project_original)
        device_name = self._sanitize_name(device_original)

        ch_value = self._get_meta(data_dict, "ch_id", "channel", default=0)
        try:
            ch_id = int(ch_value)
        except Exception:
            ch_id = 0

        target_dir = self.root_path / user / project / device_name
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{timestamp_str}_{device_name}_CH{ch_id:02d}_IV curve.csv"

        area = self._coerce_float(self._get_meta(data_dict, "area", "area_cm2", default=1.0), default=1.0)
        if not area or area <= 0:
            area = 1.0

        with self.lock:
            with open(file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                writer.writerow(self._pad(["#System_Information:"]))
                writer.writerow(self._pad(["# Unit_Schema_Version:", self.SCHEMA_VERSION]))
                writer.writerow(self._pad(["# Raw_Voltage_Source:", "SMU measured v_msd; legacy fallback v_src"]))
                writer.writerow(self._pad(["# Polarity_Check:", self._fmt_meta(data_dict.get("polarity_check", ""))]))
                writer.writerow(self._pad(["# Rline_Validation_Version:", self._fmt_meta(data_dict.get("rline_validation_version", ""))]))
                writer.writerow(self._pad(["# Channel:", self._fmt_meta(ch_id)]))
                writer.writerow(self._pad(["# SMU+ relay #:", self._fmt_meta(self._get_meta(data_dict, "relay_pos", "smu_pos_relay", "smu_pos", "relay_positive"))]))
                writer.writerow(self._pad(["# SMU- relay #:", self._fmt_meta(self._get_meta(data_dict, "relay_neg", "smu_neg_relay", "smu_neg", "relay_negative"))]))
                writer.writerow(self._pad(["# Line_resistance_Ohm:", self._fmt_meta(self._get_meta(data_dict, "line_res", "line_resistance", default=""))]))
                writer.writerow(self._pad(["# Line_resistance_Measurement_Date:", self._fmt_meta(self._get_meta(data_dict, "line_res_date", "line_resistance_measurement_date", default=""))]))
                writer.writerow(self._pad(["# Line_resistance_Age_Days:", self._fmt_meta(self._get_meta(data_dict, "line_res_age_days", default=""))]))
                writer.writerow(self._pad(["# Rline_Calibration_Max_Age_Days:", self._fmt_meta(self._get_meta(data_dict, "rline_max_age_days", default=""))]))
                writer.writerow(self._pad(["# Line_resistance_Expired:", self._fmt_meta(self._get_meta(data_dict, "line_res_expired", default=""))]))
                writer.writerow(self._pad(["# Offset_current_A:", self._fmt_meta(self._get_meta(data_dict, "offset_current", "offset_current_A", default=""))]))
                writer.writerow(self._pad([]))

                writer.writerow(self._pad(["#Device_Information"]))
                writer.writerow(self._pad(["# User_Name:", self._fmt_meta(user_original)]))
                writer.writerow(self._pad(["# Project_Name:", self._fmt_meta(project_original)]))
                writer.writerow(self._pad(["# Device_Name:", self._fmt_meta(device_original)]))
                writer.writerow(self._pad(["# Experiment_UID:", self._fmt_meta(self._get_meta(data_dict, "experiment_uid", default=""))]))
                writer.writerow(self._pad(["# Run_Session_ID:", self._fmt_meta(self._get_meta(data_dict, "run_session_id", default=""))]))
                writer.writerow(self._pad(["# Channel_Label:", self._fmt_meta(self._get_meta(data_dict, "channel_label", default=""))]))
                writer.writerow(self._pad(["# Area_cm2:", self._fmt_meta(self._get_meta(data_dict, "area", "area_cm2", default=area))]))
                writer.writerow(self._pad([]))

                writer.writerow(self._pad(["#Measurement_Information:"]))
                writer.writerow(self._pad(["# Start_Time:", start_time.isoformat()]))
                writer.writerow(self._pad(["# Scan_Direction:", self._fmt_meta(self._get_meta(data_dict, "scan_direction", "scan_dir", default="Forward+Reverse"))]))
                writer.writerow(self._pad(["# Voltage_Start_V:", self._fmt_meta(self._get_meta(data_dict, "v_start", default=""))]))
                writer.writerow(self._pad(["# Voltage_Stop_V:", self._fmt_meta(self._get_meta(data_dict, "v_stop", default=""))]))
                writer.writerow(self._pad(["# V_Step_V:", self._fmt_meta(self._get_meta(data_dict, "v_step", default=""))]))
                writer.writerow(self._pad(["# Delay_ms:", self._fmt_meta(self._get_meta(data_dict, "delay_time", "delay", default=""))]))
                writer.writerow(self._pad(["# Measurement_Interval_Min:", self._fmt_meta(self._get_meta(data_dict, "interval_min", "meas_interval", "interval", default=""))]))
                writer.writerow(self._pad(["# Scheduled_Time:", self._fmt_meta(self._get_meta(data_dict, "scheduled_time", default=""))]))
                writer.writerow(self._pad(["# Actual_Start_Time:", self._fmt_meta(self._get_meta(data_dict, "actual_start_time", default=""))]))
                writer.writerow(self._pad(["# Actual_End_Time:", self._fmt_meta(self._get_meta(data_dict, "actual_end_time", default=""))]))
                writer.writerow(self._pad(["# Schedule_Delay_Sec:", self._fmt_meta(self._get_meta(data_dict, "schedule_delay_sec", default=""))]))
                writer.writerow(self._pad(["# Queue_Position:", self._fmt_meta(self._get_meta(data_dict, "queue_position", default=""))]))
                writer.writerow(self._pad(["# Conflict_Flag:", self._fmt_meta(self._get_meta(data_dict, "conflict_flag", default=""))]))
                writer.writerow(self._pad(["# Conflict_Group_Size:", self._fmt_meta(self._get_meta(data_dict, "conflict_group_size", default=""))]))
                writer.writerow(self._pad(["# Conflict_Peers:", self._fmt_meta(self._get_meta(data_dict, "conflict_peer_labels", default=""))]))
                writer.writerow(self._pad(["# Next_Due_Basis:", self._fmt_meta(self._get_meta(data_dict, "next_due_time_basis", default=""))]))
                writer.writerow(self._pad(["# Scheduler_Overloaded:", self._fmt_meta(self._get_meta(data_dict, "scheduler_overloaded", default=""))]))
                writer.writerow(self._pad(["# Scheduler_Load_Ratio:", self._fmt_meta(self._get_meta(data_dict, "scheduler_load_ratio", default=""))]))
                writer.writerow(self._pad(["# Scheduler_Total_Required_Sec:", self._fmt_meta(self._get_meta(data_dict, "scheduler_total_required_sec", default=""))]))
                writer.writerow(self._pad(["# Scheduler_Min_Interval_Sec:", self._fmt_meta(self._get_meta(data_dict, "scheduler_min_interval_sec", default=""))]))
                writer.writerow(self._pad([]))

                writer.writerow(self._pad(["#Environment_Information:"]))
                writer.writerow(self._pad(["# Temp_oC:", self._fmt_meta(self._get_env_value(data_dict, env_data, "temp", "env_temp", "temperature"))]))
                writer.writerow(self._pad(["# Hum_RH%:", self._fmt_meta(self._get_env_value(data_dict, env_data, "hum", "env_hum", "humidity"))]))
                writer.writerow(self._pad([]))

                writer.writerow(self._pad(["# Analysis Summary Matrix"]))
                writer.writerow(self._pad(["", *self.SUMMARY_HEADERS, "Hysteresis_Index"]))

                for suffix in self.SUMMARY_SUFFIXES:
                    row = [self.SUMMARY_ROW_LABELS[suffix]]
                    for param in self.SUMMARY_PARAMS:
                        row.append(self._fmt_summary(self._get_analysis_value(analysis_results, param, suffix)))
                    row.append("")
                    writer.writerow(self._pad(row))
                writer.writerow(self._pad([]))

                writer.writerow([*self.POINT_HEADERS, "", *self.POINT_HEADERS])

                for f_point, r_point in zip_longest(fwd_data or [], rev_data or [], fillvalue=None):
                    row = []

                    f_values = self._extract_point(f_point)
                    if f_values is None:
                        row.extend([""] * 9)
                    else:
                        v_raw, i_raw, v_corr, i_corr = f_values
                        row.extend([
                            "Forward",
                            self._fmt_data(v_raw),
                            self._fmt_data(i_raw),
                            self._fmt_data(i_raw / area),
                            self._fmt_data(self._solar_output_power(v_raw, i_raw)),
                            self._fmt_data(v_corr),
                            self._fmt_data(i_corr),
                            self._fmt_data(i_corr / area),
                            self._fmt_data(self._solar_output_power(v_corr, i_corr)),
                        ])

                    row.append("")

                    r_values = self._extract_point(r_point)
                    if r_values is None:
                        row.extend([""] * 9)
                    else:
                        v_raw, i_raw, v_corr, i_corr = r_values
                        row.extend([
                            "Reversed",
                            self._fmt_data(v_raw),
                            self._fmt_data(i_raw),
                            self._fmt_data(i_raw / area),
                            self._fmt_data(self._solar_output_power(v_raw, i_raw)),
                            self._fmt_data(v_corr),
                            self._fmt_data(i_corr),
                            self._fmt_data(i_corr / area),
                            self._fmt_data(self._solar_output_power(v_corr, i_corr)),
                        ])

                    writer.writerow(self._pad(row))

        return file_path
