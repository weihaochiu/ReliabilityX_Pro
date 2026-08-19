import csv
import datetime
import re
import threading
from pathlib import Path

from core.measurement_schema import IV_PARAMETER_KEYS, SUMMARY_SUB_HEADERS, SCHEMA_VERSION
from core.numeric_utils import parse_float_or_none


class SummaryLogger:
    """
    負責維護各專案目錄下的 Summary_report.csv。
    輸出格式對齊 temp 範例，並同時相容：
    1. 扁平 key 結構（例如 Voc_F_Raw）
    2. 巢狀 dict 結構（例如 results['Forward_Raw']['Voc']）
    """

    TOTAL_COLS = 74
    PARAM_KEYS = IV_PARAMETER_KEYS
    SUB_HEADERS = SUMMARY_SUB_HEADERS
    SCHEMA_VERSION = SCHEMA_VERSION

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
    def _is_blank(value):
        return value is None or value == ""

    def _pad(self, row):
        row = list(row)
        if len(row) < self.TOTAL_COLS:
            row.extend([""] * (self.TOTAL_COLS - len(row)))
        return row[:self.TOTAL_COLS]

    def _first_non_blank(self, *values):
        for value in values:
            if not self._is_blank(value):
                return value
        return ""

    def _coerce_float(self, value, default=None, *, field_name: str = ""):
        number = parse_float_or_none(value, field_name=field_name, context="SummaryLogger", warn_invalid=True)
        return default if number is None else number

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
        return None

    def _fmt_number(self, value):
        number = self._coerce_float(value, default=None)
        if number is None:
            return ""
        text = f"{number:.4f}".rstrip("0").rstrip(".")
        if text == "-0":
            return "0"
        return text

    def _fmt_meta(self, value):
        return "" if value is None else str(value)

    def _fmt_summary_time(self, value):
        dt = self._coerce_datetime(value)
        if dt is None:
            return ""
        return f"{dt.year}/{dt.month}/{dt.day} {dt.hour}:{dt.minute:02d}"

    def _get_result_value(self, results, param, suffix):
        flat_keys = [
            f"{param}_{suffix}",
            f"{param.lower()}_{suffix}",
            f"{param.upper()}_{suffix}",
        ]
        for key in flat_keys:
            if key in results and not self._is_blank(results.get(key)):
                return results.get(key)

        container_names = {
            "F_Raw": ["Forward_Raw", "F_Raw", "forward_raw", "forwardRaw"],
            "R_Raw": ["Reversed_Raw", "Reverse_Raw", "R_Raw", "reversed_raw", "reverse_raw", "reversedRaw"],
            "F_Corr": ["Forward_Corr", "F_Corr", "forward_corr", "forwardCorr"],
            "R_Corr": ["Reversed_Corr", "Reverse_Corr", "R_Corr", "reversed_corr", "reverse_corr", "reversedCorr"],
        }.get(suffix, [suffix])

        param_aliases = [param, param.lower(), param.upper()]
        if param == "Rsh":
            param_aliases.extend(["Rsh_kOhm", "rsh_kohm", "RSH_KOHM"])

        for container_name in container_names:
            sub = results.get(container_name)
            if isinstance(sub, dict):
                for alias in param_aliases:
                    if alias in sub and not self._is_blank(sub.get(alias)):
                        return sub.get(alias)
        return ""

    def _get_meta(self, results, *keys, default=""):
        for key in keys:
            if key in results and not self._is_blank(results.get(key)):
                return results.get(key)
        return default

    def _build_relative_file_path(self, results, file_path_obj, s_user, s_project, s_device):
        if isinstance(file_path_obj, Path):
            try:
                return str(file_path_obj.resolve().relative_to(self.root_path.resolve())).replace('\\', '/')
            except Exception:
                pass
            return str((Path(s_user) / s_project / s_device / file_path_obj.name)).replace('\\', '/')
        if isinstance(file_path_obj, str) and file_path_obj:
            path_value = Path(file_path_obj)
            try:
                return str(path_value.resolve().relative_to(self.root_path.resolve())).replace('\\', '/')
            except Exception:
                return file_path_obj.replace('\\', '/')
        return ""

    def update_summary_report(self, results):
        results = results or {}

        s_user = self._sanitize_name(self._get_meta(results, "user", default="default_user"))
        s_project = self._sanitize_name(self._get_meta(results, "project", default="default_project"))
        s_device = self._sanitize_name(self._get_meta(results, "device_name", default="Device"))

        o_user = self._get_meta(results, "user", default="default_user")
        o_project = self._get_meta(results, "project", default="default_project")
        o_device = self._get_meta(results, "device_name", default="Device")

        target_dir = self.root_path / s_user / s_project / s_device
        target_dir.mkdir(parents=True, exist_ok=True)
        summary_path = target_dir / "Summary_report.csv"
        file_exists = summary_path.exists()

        with self.lock:
            with open(summary_path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                if not file_exists:
                    writer.writerow(self._pad(["# User:", self._fmt_meta(o_user)]))
                    writer.writerow(self._pad(["# Project:", self._fmt_meta(o_project)]))
                    writer.writerow(self._pad(["# Device:", self._fmt_meta(o_device)]))
                    writer.writerow(self._pad([]))

                    writer.writerow(self._pad(["#Device_Information:"]))
                    writer.writerow(self._pad(["# Channel:", self._fmt_meta(self._get_meta(results, "ch_id", "channel", default=""))]))
                    writer.writerow(self._pad(["#SMU+ relay #:", self._fmt_meta(self._get_meta(results, "smu_pos_relay", "relay_pos", "smu_pos", default=""))]))
                    writer.writerow(self._pad(["#SMU- relay #:", self._fmt_meta(self._get_meta(results, "smu_neg_relay", "relay_neg", "smu_neg", default=""))]))
                    writer.writerow(self._pad(["#Line_resistance_Ohm:", self._fmt_meta(self._get_meta(results, "line_res", "line_resistance", default=""))]))
                    writer.writerow(self._pad(["#Line_resistance_Measurement_Date:", self._fmt_meta(self._get_meta(results, "line_res_date", "line_resistance_measurement_date", default=""))]))
                    writer.writerow(self._pad(["#Line_resistance_Age_Days:", self._fmt_meta(self._get_meta(results, "line_res_age_days", default=""))]))
                    writer.writerow(self._pad(["#Rline_Calibration_Max_Age_Days:", self._fmt_meta(self._get_meta(results, "rline_max_age_days", default=""))]))
                    writer.writerow(self._pad(["#Line_resistance_Expired:", self._fmt_meta(self._get_meta(results, "line_res_expired", default=""))]))
                    writer.writerow(self._pad(["#Offset_current_A:", self._fmt_meta(self._get_meta(results, "offset_current", "offset_current_A", default=""))]))
                    writer.writerow(self._pad([]))

                    writer.writerow(self._pad(["#Device_Information:"]))
                    writer.writerow(self._pad(["# Device:", self._fmt_meta(o_device)]))
                    writer.writerow(self._pad(["# Experiment_UID:", self._fmt_meta(self._get_meta(results, "experiment_uid", default=""))]))
                    writer.writerow(self._pad(["# Run_Session_ID:", self._fmt_meta(self._get_meta(results, "run_session_id", default=""))]))
                    writer.writerow(self._pad(["# Channel_Label:", self._fmt_meta(self._get_meta(results, "channel_label", default=""))]))
                    writer.writerow(self._pad(["# Area_cm2:", self._fmt_meta(self._get_meta(results, "area", "area_cm2", default=""))]))
                    writer.writerow(self._pad([]))

                    writer.writerow(self._pad(["#Measurement_Information:"]))
                    writer.writerow(self._pad(["# Scan_Direction:", self._fmt_meta(self._get_meta(results, "scan_dir", "scan_direction", default=""))]))
                    writer.writerow(self._pad(["#Voltage_Start_V:", self._fmt_meta(self._get_meta(results, "v_start", default=""))]))
                    writer.writerow(self._pad(["#Voltage_Stop_V:", self._fmt_meta(self._get_meta(results, "v_stop", default=""))]))
                    writer.writerow(self._pad(["# V_Step:", self._fmt_meta(self._get_meta(results, "v_step", default=""))]))
                    writer.writerow(self._pad(["# Delay_ms:", self._fmt_meta(self._get_meta(results, "delay", "delay_time", default=""))]))
                    writer.writerow(self._pad(["#Measurement_Interval_Min:", self._fmt_meta(self._get_meta(results, "meas_interval", "interval_min", "interval", default=""))]))

                    writer.writerow(self._pad([]))
                    writer.writerow(self._pad([]))
                    writer.writerow(self._pad(["#File_Information:"]))
                    writer.writerow(self._pad(["#Unit_Schema_Version:", self.SCHEMA_VERSION]))
                    writer.writerow(self._pad(["#File_Path:", ""]))
                    writer.writerow(self._pad([]))

                    line28 = ["", "Temp", "Hum", ""]
                    line28.extend(["Forward_Raw"] * 11)
                    line28.extend(["Reversed_Raw"] * 11)
                    line28.extend(["Raw", ""])
                    line28.extend(["Forward_Corr"] * 11)
                    line28.extend(["Reversed_Corr"] * 11)
                    line28.extend(["Corr", "", ""])
                    line28.extend(["Identity"] * 4)
                    line28.extend(["Scheduler"] * 16)
                    writer.writerow(self._pad(line28))

                    line29 = ["Start_Time", "(oC)", "(RH%)", ""]
                    line29.extend(self.SUB_HEADERS)
                    line29.extend(self.SUB_HEADERS)
                    line29.extend(["Hysteresis_Index", ""])
                    line29.extend(self.SUB_HEADERS)
                    line29.extend(self.SUB_HEADERS)
                    line29.extend(["Hysteresis_Index", "", "Raw_Data_File"])
                    line29.extend(["Experiment_UID", "Run_Session_ID", "Channel_Label", "Internal_CH_ID"])
                    line29.extend([
                        "Scheduled_Time",
                        "Actual_Start_Time",
                        "Actual_End_Time",
                        "Schedule_Delay_Sec",
                        "Queue_Position",
                        "Conflict_Flag",
                        "Conflict_Group_Size",
                        "Conflict_Peers",
                        "Next_Due_Basis",
                        "Scheduler_Overloaded",
                        "Scheduler_Load_Ratio",
                        "Scheduler_Total_Required_Sec",
                        "Scheduler_Min_Interval_Sec",
                        "Scheduler_Policy",
                        "Scheduler_Max_Allowed_Delay_Sec",
                        "Scheduler_Skip_Reason",
                    ])
                    writer.writerow(self._pad(line29))

                row_data = [self._fmt_summary_time(self._get_meta(results, "start_time", default=""))]
                row_data.append(self._fmt_number(self._get_meta(results, "temp", "env_temp", default="")))
                row_data.append(self._fmt_number(self._get_meta(results, "hum", "env_hum", default="")))
                row_data.append("")

                for suffix in ["F_Raw", "R_Raw"]:
                    for param in self.PARAM_KEYS:
                        row_data.append(self._fmt_number(self._get_result_value(results, param, suffix)))

                row_data.append(self._fmt_number(self._get_meta(results, "HI_Raw", default="")))
                row_data.append("")

                for suffix in ["F_Corr", "R_Corr"]:
                    for param in self.PARAM_KEYS:
                        row_data.append(self._fmt_number(self._get_result_value(results, param, suffix)))

                row_data.append(self._fmt_number(self._get_meta(results, "HI_Corr", default="")))
                row_data.append("")

                file_path_obj = self._get_meta(results, "file_path", default="")
                row_data.append(self._build_relative_file_path(results, file_path_obj, s_user, s_project, s_device))
                row_data.extend([
                    self._fmt_meta(self._get_meta(results, "experiment_uid", default="")),
                    self._fmt_meta(self._get_meta(results, "run_session_id", default="")),
                    self._fmt_meta(self._get_meta(results, "channel_label", default="")),
                    self._fmt_meta(self._get_meta(results, "internal_ch_id", "ch_id", default="")),
                ])
                row_data.extend([
                    self._fmt_summary_time(self._get_meta(results, "scheduled_time", default="")),
                    self._fmt_summary_time(self._get_meta(results, "actual_start_time", default="")),
                    self._fmt_summary_time(self._get_meta(results, "actual_end_time", default="")),
                    self._fmt_number(self._get_meta(results, "schedule_delay_sec", default="")),
                    self._fmt_meta(self._get_meta(results, "queue_position", default="")),
                    self._fmt_meta(self._get_meta(results, "conflict_flag", default="")),
                    self._fmt_meta(self._get_meta(results, "conflict_group_size", default="")),
                    self._fmt_meta(self._get_meta(results, "conflict_peer_labels", default="")),
                    self._fmt_meta(self._get_meta(results, "next_due_time_basis", default="")),
                    self._fmt_meta(self._get_meta(results, "scheduler_overloaded", default="")),
                    self._fmt_number(self._get_meta(results, "scheduler_load_ratio", default="")),
                    self._fmt_number(self._get_meta(results, "scheduler_total_required_sec", default="")),
                    self._fmt_number(self._get_meta(results, "scheduler_min_interval_sec", default="")),
                    self._fmt_meta(self._get_meta(results, "scheduler_policy", default="")),
                    self._fmt_number(self._get_meta(results, "scheduler_max_allowed_delay_sec", default="")),
                    self._fmt_meta(self._get_meta(results, "scheduler_skip_reason", default="")),
                ])

                writer.writerow(self._pad(row_data))
