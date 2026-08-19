import os
import sys
import json
import re
import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Optional

# =================================================================
# 1. 系統路徑與環境適應 (Path & Env Management)
# =================================================================

def get_resource_path(relative_path: str) -> str:
    """取得打包資源的絕對路徑"""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _detect_runtime_base_dir() -> Path:
    """偵測目前執行環境的基準目錄"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _detect_runtime_base_dir()

# 多層級目錄定義
BASE_DATA_DIR = BASE_DIR / "data"
BASE_LOG_DIR = BASE_DIR / "logs"
BASE_CONFIG_DIR = BASE_DIR / "config"


def _extract_windows_anchor(path_str: str) -> str:
    """擷取 Windows 路徑的磁碟根，例如 G:\\"""
    if not path_str:
        return ""
    match = re.match(r"^[A-Za-z]:[\\/]", str(path_str).strip())
    if match:
        return f"{str(path_str).strip()[0].upper()}:\\"
    return ""


def _is_windows_drive_available(path_str: str) -> bool:
    """檢查 Windows 磁碟是否存在"""
    anchor = _extract_windows_anchor(path_str)
    if not anchor:
        return True
    try:
        return os.path.exists(anchor)
    except OSError:
        return False


def is_safe_path(path_str: Optional[str]) -> bool:
    """
    檢查路徑是否可接受：
    1. 非空
    2. 若為 Windows 磁碟路徑，則磁碟必須存在
    注意：不再禁止 D:/F:/G:/I: 這類磁碟代號本身
    """
    if not path_str:
        return False

    path_s = str(path_str).strip()
    if not path_s:
        return False

    normalized = path_s.replace("/", "\\")

    if not _is_windows_drive_available(normalized):
        return False

    return True


def ensure_directory(path_like: Path, fallback: Optional[Path] = None) -> Path:
    """
    安全建立資料夾；若失敗則回退到 fallback。
    可處理：
    - 磁碟不存在
    - 父目錄不存在
    - 權限不足
    - 其他 OSError
    """
    target = Path(path_like)

    try:
        anchor = _extract_windows_anchor(str(target))
        if anchor and not os.path.exists(anchor):
            raise FileNotFoundError(f"磁碟不存在: {anchor}")

        target.mkdir(parents=True, exist_ok=True)
        return target

    except OSError:
        if fallback is None:
            raise

    fb = Path(fallback)
    fb_anchor = _extract_windows_anchor(str(fb))
    if fb_anchor and not os.path.exists(fb_anchor):
        raise FileNotFoundError(f"備援磁碟不存在: {fb_anchor}")

    fb.mkdir(parents=True, exist_ok=True)
    return fb


def _bootstrap_base_directories() -> None:
    """初始化程式基礎資料夾"""
    for folder in [BASE_DATA_DIR, BASE_LOG_DIR, BASE_CONFIG_DIR]:
        try:
            ensure_directory(folder)
        except OSError as exc:
            print(f"[ERROR] 無法建立目錄: {folder} | {exc}")


_bootstrap_base_directories()

# JSON 設定檔路徑
CHANNEL_SETTINGS_FILE = BASE_CONFIG_DIR / "channel_settings.json"
CALIBRATION_SETTINGS_FILE = BASE_CONFIG_DIR / "calibration_settings.json"
CONFIG_SETTINGS_FILE = BASE_CONFIG_DIR / "config_settings.json"
USER_SETTINGS_FILE = BASE_CONFIG_DIR / "user_settings.json"
HARDWARE_MAP_FILE = BASE_CONFIG_DIR / "hardware_map.json"
PERSONNEL_SETTINGS_FILE = BASE_CONFIG_DIR / "personnel_tab.json"
NOTIFICATION_SETTINGS_FILE = BASE_CONFIG_DIR / "notification_settings.json"
NOTIFICATION_SETTINGS_EXAMPLE_FILE = BASE_CONFIG_DIR / "notification_settings.example.json"
RUNTIME_SCHEDULE_STATE_FILE = BASE_CONFIG_DIR / "runtime_schedule_state.json"
MEASUREMENT_RECIPES_FILE = BASE_CONFIG_DIR / "measurement_recipes.json"
STATION_RECIPES_FILE = BASE_CONFIG_DIR / "station_recipes.json"
ENVIRONMENT_PROFILES_FILE = BASE_CONFIG_DIR / "environment_profiles.json"
ENVIRONMENT_CONTROL_RECIPES_FILE = BASE_CONFIG_DIR / "environment_control_recipes.json"

# Shutdown behavior
# Safe application close waits for the current channel to reach the existing
# graceful stop boundary.  If this timeout is reached, application close is
# cancelled and the operator can choose emergency shutdown instead.
SAFE_SHUTDOWN_WAIT_SEC = 600

# =================================================================
# 2. 設定檔載入與儲存 (Config Load/Save)
# =================================================================

def load_json_file(file_path: Path, default_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """通用 JSON 檔案載入器"""
    if default_data is None:
        default_data = {}

    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default_data

    return default_data


def save_json_file(file_path: Path, data: Dict[str, Any]) -> bool:
    """通用 JSON 檔案儲存器"""
    try:
        ensure_directory(file_path.parent, fallback=BASE_CONFIG_DIR)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except OSError as exc:
        print(f"[ERROR] 儲存 JSON 失敗: {file_path} | {exc}")
        return False


def load_config_settings():
    """載入全域設定檔"""
    return load_json_file(CONFIG_SETTINGS_FILE)


def save_config_settings(settings):
    """儲存全域設定檔"""
    return save_json_file(CONFIG_SETTINGS_FILE, settings)


def load_personnel_settings():
    """載入人員、專案與報告 CC 設定。

    The canonical project ownership model stays simple: each project belongs to
    exactly one user in ``USER_PROJECT_MAP``.  Optional per-user profile records
    hold email and CC recipients for notification/report routing; channel dialogs
    still only need the user->projects mapping.
    """
    default_map = {
        "USER_PROJECT_MAP": {
            "Example_User": ["Example_Project"],
        },
        "USER_PROFILES": {
            "Example_User": {"email": "", "cc": [], "report_times": []},
        },
    }
    settings = load_json_file(PERSONNEL_SETTINGS_FILE, default_data=default_map)
    if not isinstance(settings, dict):
        settings = dict(default_map)
    user_project_map = settings.get("USER_PROJECT_MAP")
    if not isinstance(user_project_map, dict):
        user_project_map = dict(default_map["USER_PROJECT_MAP"])
    normalized_map = {}
    for user, projects in user_project_map.items():
        if isinstance(projects, list):
            normalized_map[str(user)] = [str(item) for item in projects if str(item).strip()]
        else:
            normalized_map[str(user)] = []
    settings["USER_PROJECT_MAP"] = normalized_map

    profiles = settings.get("USER_PROFILES")
    if not isinstance(profiles, dict):
        profiles = {}
    for user in normalized_map:
        raw = profiles.get(user, {}) if isinstance(profiles.get(user), dict) else {}
        cc_raw = raw.get("cc", [])
        if isinstance(cc_raw, str):
            cc_values = [item.strip() for item in cc_raw.replace(";", ",").split(",") if item.strip()]
        elif isinstance(cc_raw, list):
            cc_values = [str(item).strip() for item in cc_raw if str(item).strip()]
        else:
            cc_values = []
        profiles[user] = {
            "email": str(raw.get("email", "")).strip(),
            "cc": cc_values,
            "report_times": raw.get("report_times", []) if isinstance(raw.get("report_times", []), list) else [],
            "notes": str(raw.get("notes", "")),
        }
    settings["USER_PROFILES"] = profiles
    return settings


def save_personnel_settings(settings):
    """儲存人員、專案與報告 CC 設定。"""
    return save_json_file(PERSONNEL_SETTINGS_FILE, load_personnel_settings_from_payload(settings))


def load_personnel_settings_from_payload(settings):
    """Normalize an in-memory personnel payload before saving.

    Args:
        settings: Raw settings from PersonnelTab.

    Returns:
        Dict[str, Any]: Normalized personnel settings.
    """
    payload = settings if isinstance(settings, dict) else {}
    user_project_map = payload.get("USER_PROJECT_MAP", {})
    if not isinstance(user_project_map, dict):
        user_project_map = {}
    profiles = payload.get("USER_PROFILES", {})
    if not isinstance(profiles, dict):
        profiles = {}
    normalized = {"USER_PROJECT_MAP": {}, "USER_PROFILES": {}}
    for user, projects in user_project_map.items():
        user_name = str(user).strip()
        if not user_name:
            continue
        normalized["USER_PROJECT_MAP"][user_name] = [str(item).strip() for item in (projects or []) if str(item).strip()]
        raw_profile = profiles.get(user_name, {}) if isinstance(profiles.get(user_name), dict) else {}
        cc_raw = raw_profile.get("cc", [])
        if isinstance(cc_raw, str):
            cc_list = [item.strip() for item in cc_raw.replace(";", ",").split(",") if item.strip()]
        elif isinstance(cc_raw, list):
            cc_list = [str(item).strip() for item in cc_raw if str(item).strip()]
        else:
            cc_list = []
        normalized["USER_PROFILES"][user_name] = {
            "email": str(raw_profile.get("email", "")).strip(),
            "cc": cc_list,
            "report_times": raw_profile.get("report_times", []) if isinstance(raw_profile.get("report_times", []), list) else [],
            "notes": str(raw_profile.get("notes", "")),
        }
    return normalized


def load_user_settings():
    """載入使用者本機設定 (如自定義路徑)"""
    return load_json_file(USER_SETTINGS_FILE)


def save_user_settings(settings):
    """儲存使用者本機設定"""
    return save_json_file(USER_SETTINGS_FILE, settings)


def _get_default_notification_settings() -> Dict[str, Any]:
    """通知系統預設設定。"""
    return {
        "GENERAL": {
            "timezone": "Asia/Taipei",
        },
        "TELEGRAM": {
            "enabled": False,
            "bot_token": "",
            "chat_id": "",
            "bot_token_file": "",
            "chat_id_file": "",
            "notify_on_critical_error": True,
            "notify_on_measurement_start": True,
            "notify_on_daily_summary": True,
            "daily_report_count": 2,
            "daily_report_hours": [9, 21],
            "cooldown_seconds": 300,
            "max_message_length": 3500,
            "trend_images_enabled": False,
            "trend_metrics": ["PCE (%)"],
            "trend_direction": "逆掃 (Reverse)",
            "trend_path": "修正後 (Corr)",
            "trend_x_axis_mode": "量測序號 (Seq)",
            "trend_group_mode": "overall",
            "trend_normalize": False,
            "trend_show_env": False,
            "trend_smoothing": False,
            "trend_send_as_document": False,
            "trend_pdf_enabled": False,
            "trend_pdf_include_env_when_available": True,
            "trend_image_width": 2400,
            "trend_image_height": 1400,
        },
        "EMAIL": {
            "enabled": False,
        },
        "LINE": {
            "enabled": False,
        },
    }


def load_notification_settings() -> Dict[str, Any]:
    """載入通知設定，若缺少欄位則補齊預設值。"""
    defaults = _get_default_notification_settings()
    settings = load_json_file(NOTIFICATION_SETTINGS_FILE, default_data=defaults)

    if not isinstance(settings, dict):
        settings = defaults

    merged = json.loads(json.dumps(defaults))
    for section_name, section_value in settings.items():
        if isinstance(section_value, dict) and isinstance(merged.get(section_name), dict):
            merged[section_name].update(section_value)
        else:
            merged[section_name] = section_value

    tg = merged.setdefault("TELEGRAM", {})
    report_hours = tg.get("daily_report_hours", [])
    if not isinstance(report_hours, list):
        report_hours = []

    normalized_hours = []
    for value in report_hours:
        try:
            hour = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23 and hour not in normalized_hours:
            normalized_hours.append(hour)

    valid_metrics = [
        "PCE (%)", "Voc (V)", "Jsc (mA/cm²)", "FF (%)", "Rs (Ω·cm²)",
        "Rsh (kΩ·cm²)", "Pmpp (W)", "Vmpp (V)", "Impp (mA)",
        "Jmpp (mA/cm2)", "Hysteresis_Index",
    ]
    metric_values = tg.get("trend_metrics", [])
    if not isinstance(metric_values, list):
        metric_values = []
    normalized_metrics = []
    for value in metric_values:
        text = str(value or "").strip()
        if text in valid_metrics and text not in normalized_metrics:
            normalized_metrics.append(text)

    direction_options = ["逆掃 (Reverse)", "正掃 (Forward)"]
    path_options = ["修正後 (Corr)", "原始 (Raw)"]
    x_axis_options = ["運行時間 (Hours)", "量測序號 (Seq)"]
    group_mode_options = ["overall", "user_project"]

    normalized_hours.sort()
    tg["daily_report_hours"] = normalized_hours
    tg["daily_report_count"] = len(normalized_hours)
    tg["cooldown_seconds"] = max(0, int(tg.get("cooldown_seconds", 300) or 0))
    tg["max_message_length"] = max(100, int(tg.get("max_message_length", 3500) or 3500))
    tg["enabled"] = bool(tg.get("enabled", False))
    tg["notify_on_critical_error"] = bool(tg.get("notify_on_critical_error", True))
    tg["notify_on_measurement_start"] = bool(tg.get("notify_on_measurement_start", True))
    tg["notify_on_daily_summary"] = bool(tg.get("notify_on_daily_summary", True))
    tg["bot_token"] = str(tg.get("bot_token", "") or "")
    tg["chat_id"] = str(tg.get("chat_id", "") or "")
    tg["bot_token_file"] = str(tg.get("bot_token_file", "") or "")
    tg["chat_id_file"] = str(tg.get("chat_id_file", "") or "")
    tg["trend_images_enabled"] = bool(tg.get("trend_images_enabled", False))
    tg["trend_metrics"] = normalized_metrics
    tg["trend_direction"] = str(tg.get("trend_direction", direction_options[0]) or direction_options[0])
    if tg["trend_direction"] not in direction_options:
        tg["trend_direction"] = direction_options[0]
    tg["trend_path"] = str(tg.get("trend_path", path_options[0]) or path_options[0])
    if tg["trend_path"] not in path_options:
        tg["trend_path"] = path_options[0]
    tg["trend_x_axis_mode"] = str(tg.get("trend_x_axis_mode", x_axis_options[1]) or x_axis_options[1])
    if tg["trend_x_axis_mode"] not in x_axis_options:
        tg["trend_x_axis_mode"] = x_axis_options[1]
    tg["trend_group_mode"] = str(tg.get("trend_group_mode", "overall") or "overall").strip().lower()
    if tg["trend_group_mode"] not in group_mode_options:
        tg["trend_group_mode"] = "overall"
    tg["trend_normalize"] = bool(tg.get("trend_normalize", False))
    tg["trend_show_env"] = bool(tg.get("trend_show_env", False))
    tg["trend_smoothing"] = bool(tg.get("trend_smoothing", False))
    tg["trend_send_as_document"] = bool(tg.get("trend_send_as_document", False))
    tg["trend_pdf_enabled"] = bool(tg.get("trend_pdf_enabled", False))
    tg["trend_pdf_include_env_when_available"] = bool(tg.get("trend_pdf_include_env_when_available", True))
    tg["trend_image_width"] = max(1200, int(tg.get("trend_image_width", 2400) or 2400))
    tg["trend_image_height"] = max(800, int(tg.get("trend_image_height", 1400) or 1400))

    return merged



def read_text_secret_file(path_value: str) -> str:
    """Read a local one-line secret file without persisting its content in JSON.

    The returned value is stripped of whitespace. Missing/invalid paths return an
    empty string so notification code can fail closed without crashing scans.
    """
    path_text = str(path_value or "").strip().strip('"')
    if not path_text:
        return ""
    try:
        path = Path(path_text).expanduser()
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def resolve_telegram_secret_fields(telegram_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of TELEGRAM settings with token/chat_id resolved from files.

    Direct values are still supported for backward compatibility, but file paths
    take precedence and are the recommended release-safe method.
    """
    tg = dict(telegram_cfg or {})
    token_from_file = read_text_secret_file(tg.get("bot_token_file", ""))
    chat_from_file = read_text_secret_file(tg.get("chat_id_file", ""))
    if token_from_file:
        tg["bot_token"] = token_from_file
    if chat_from_file:
        tg["chat_id"] = chat_from_file
    return tg

def save_notification_settings(settings: Dict[str, Any]) -> bool:
    """儲存通知設定。"""
    return save_json_file(NOTIFICATION_SETTINGS_FILE, settings)


def load_hardware_map():
    """載入硬體通道映射表，若檔案不存在則建立預設值"""
    default_map = {f"CH{i}": {"pos": i - 1, "neg": i - 1 + 32} for i in range(1, 33)}
    hw_map = load_json_file(HARDWARE_MAP_FILE, default_data=default_map)
    for i in range(1, 33):
        if f"CH{i}" not in hw_map:
            hw_map[f"CH{i}"] = {"pos": i - 1, "neg": i - 1 + 32}
    return hw_map


def save_hardware_map(hw_map):
    """儲存硬體通道映射表"""
    return save_json_file(HARDWARE_MAP_FILE, hw_map)


def _get_default_measurement_recipes() -> Dict[str, Any]:
    """Measurement recipe library 的預設內容。

    The built-in names intentionally encode the intended device family instead
    of adding a separate WBG/NBG/tandem enum.  Operators can duplicate and edit
    these templates for area, current limit, scan delay, or custom voltage range
    without changing the schema consumed by ChannelSettingDialog.
    """
    return {
        "recipes": [
            {
                "name": "Normal Bandgap Perovskite - Standard IV",
                "v_start": -0.10,
                "v_stop": 1.25,
                "v_step": 0.02,
                "delay_time_ms": 50,
                "measurement_interval_min": 10,
                "current_limit_a": 0.20,
                "area_cm2": 0.10,
            },
            {
                "name": "WBG Perovskite - Standard IV",
                "v_start": -0.10,
                "v_stop": 1.45,
                "v_step": 0.02,
                "delay_time_ms": 50,
                "measurement_interval_min": 10,
                "current_limit_a": 0.20,
                "area_cm2": 0.10,
            },
            {
                "name": "NBG Perovskite - Standard IV",
                "v_start": -0.10,
                "v_stop": 1.05,
                "v_step": 0.02,
                "delay_time_ms": 50,
                "measurement_interval_min": 10,
                "current_limit_a": 0.20,
                "area_cm2": 0.10,
            },
            {
                "name": "Perovskite-Si Tandem - Standard IV",
                "v_start": -0.10,
                "v_stop": 2.05,
                "v_step": 0.02,
                "delay_time_ms": 50,
                "measurement_interval_min": 10,
                "current_limit_a": 0.20,
                "area_cm2": 0.10,
            },
        ]
    }

def _normalize_recipe_entry(item: Dict[str, Any], fallback_index: int) -> Optional[Dict[str, Any]]:
    """將 recipe entry 正規化為固定七欄位結構。"""
    if not isinstance(item, dict):
        return None

    name = str(item.get("name") or f"Recipe {fallback_index}").strip()
    if not name:
        name = f"Recipe {fallback_index}"

    def _to_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _to_int(value: Any, default: int) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(default)

    normalized = {
        "name": name,
        "v_start": _to_float(item.get("v_start"), DEFAULT_MEASURE_CONFIG["V_START"]),
        "v_stop": _to_float(item.get("v_stop"), DEFAULT_MEASURE_CONFIG["V_STOP"]),
        "v_step": max(_to_float(item.get("v_step"), DEFAULT_MEASURE_CONFIG["V_STEP"]), 0.0001),
        "delay_time_ms": max(
            _to_int(item.get("delay_time_ms", item.get("delay_time")), DEFAULT_MEASURE_CONFIG["DELAY_MS"]),
            0,
        ),
        "measurement_interval_min": max(
            _to_int(item.get("measurement_interval_min", item.get("interval_min")), DEFAULT_MEASURE_CONFIG["INTERVAL_MIN"]),
            0,
        ),
        "current_limit_a": max(
            _to_float(item.get("current_limit_a", item.get("i_limit")), GLOBAL_SAFETY.get("I_MAX", 0.5)),
            0.0,
        ),
        "area_cm2": max(
            _to_float(item.get("area_cm2", item.get("area")), DEFAULT_MEASURE_CONFIG["AREA_CM2"]),
            0.0,
        ),
    }
    return normalized


def load_measurement_recipes() -> Dict[str, Any]:
    """載入 recipe library，若欄位缺失則補齊預設格式。

    Missing built-in recipes are automatically prepended so a newly opened
    project always exposes WBG / NBG / normal bandgap / perovskite-Si tandem
    templates while preserving existing user recipes.
    """
    defaults = _get_default_measurement_recipes()
    raw = load_json_file(MEASUREMENT_RECIPES_FILE, default_data=defaults)
    recipe_items = raw.get("recipes", []) if isinstance(raw, dict) else []
    normalized: List[Dict[str, Any]] = []
    seen_names = set()

    def _append_entry(item: Dict[str, Any], idx: int) -> None:
        entry = _normalize_recipe_entry(item, idx)
        if entry is None:
            return
        original_name = entry["name"]
        suffix = 2
        while entry["name"] in seen_names:
            entry["name"] = f"{original_name} ({suffix})"
            suffix += 1
        seen_names.add(entry["name"])
        normalized.append(entry)

    for idx, item in enumerate(defaults.get("recipes", []), start=1):
        _append_entry(item, idx)
    for idx, item in enumerate(recipe_items, start=len(normalized) + 1):
        if isinstance(item, dict) and str(item.get("name", "")) in seen_names:
            continue
        _append_entry(item, idx)

    if not normalized:
        normalized = defaults["recipes"]

    return {"recipes": normalized}


def save_measurement_recipes(settings: Dict[str, Any]) -> bool:
    """儲存 recipe library，寫入前做結構正規化。"""
    recipe_items = settings.get("recipes", []) if isinstance(settings, dict) else []
    normalized: List[Dict[str, Any]] = []
    seen_names = set()

    for idx, item in enumerate(recipe_items, start=1):
        entry = _normalize_recipe_entry(item, idx)
        if entry is None:
            continue
        original_name = entry["name"]
        suffix = 2
        while entry["name"] in seen_names:
            entry["name"] = f"{original_name} ({suffix})"
            suffix += 1
        seen_names.add(entry["name"])
        normalized.append(entry)

    if not normalized:
        normalized = _get_default_measurement_recipes()["recipes"]

    return save_json_file(MEASUREMENT_RECIPES_FILE, {"recipes": normalized})



def _get_default_station_recipes() -> Dict[str, Any]:
    """Return the default unified Environment / Station recipe library.

    These recipes describe environmental setpoints and station actions (light,
    hotplate, chamber, vacuum) instead of low-level SMU/relay connection fields.
    Low-level connection settings stay under Hardware Connection; relay ranges
    stay under Relay / Channel Mapping.
    """
    return {
        "recipes": [
            {
                "name": "Indoor Light Soaking 1 Sun",
                "environment_type": "indoor",
                "enabled": True,
                "required_hardware": {
                    "smu": True,
                    "relay": True,
                    "environment_sensor": True,
                    "light_controller": True,
                    "hotplate": False,
                    "chamber": False,
                    "vacuum": False,
                },
                "setpoints": {
                    "temperature_c": 25.0,
                    "humidity_rh": None,
                    "pressure_kpa": None,
                    "light_intensity_percent": 100.0,
                    "hotplate_temperature_c": None,
                },
                "timeline": [
                    {"time_s": 0, "action": "light_on", "target": "LED_1", "value": 100, "duration_s": None, "notes": "Start 1-sun light soaking."}
                ],
                "safety_limits": {"max_temperature_c": 60.0, "max_humidity_rh": 80.0},
                "calibration_profile": "latest",
                "notification_profile": "default",
                "notes": "Indoor station recipe: light schedule only; no chamber/vacuum requirement.",
            },
            {
                "name": "Climate 85C 85RH Reliability",
                "environment_type": "climate",
                "enabled": True,
                "required_hardware": {
                    "smu": True,
                    "relay": True,
                    "environment_sensor": True,
                    "light_controller": False,
                    "hotplate": False,
                    "chamber": True,
                    "vacuum": False,
                },
                "setpoints": {
                    "temperature_c": 85.0,
                    "humidity_rh": 85.0,
                    "pressure_kpa": None,
                    "light_intensity_percent": 0.0,
                    "hotplate_temperature_c": None,
                },
                "timeline": [
                    {"time_s": 0, "action": "chamber_set", "target": "CHAMBER_1", "value": "85C/85RH", "duration_s": None, "notes": "Set damp-heat condition."}
                ],
                "safety_limits": {"max_temperature_c": 90.0, "max_humidity_rh": 90.0},
                "calibration_profile": "latest",
                "notification_profile": "default",
                "notes": "Climate chamber station recipe. Only blocks readiness when selected by active channels.",
            },
            {
                "name": "Vacuum Light Thermal Stress",
                "environment_type": "glovebox",
                "enabled": True,
                "required_hardware": {
                    "smu": True,
                    "relay": True,
                    "environment_sensor": True,
                    "light_controller": True,
                    "hotplate": True,
                    "chamber": False,
                    "vacuum": True,
                },
                "setpoints": {
                    "temperature_c": 65.0,
                    "humidity_rh": None,
                    "pressure_kpa": -95.0,
                    "light_intensity_percent": 100.0,
                    "hotplate_temperature_c": 65.0,
                },
                "timeline": [
                    {"time_s": 0, "action": "vacuum_on", "target": "VACUUM_1", "value": -95, "duration_s": None, "notes": "Enable vacuum environment."},
                    {"time_s": 0, "action": "hotplate_set", "target": "HOTPLATE_1", "value": 65, "duration_s": None, "notes": "Set hotplate temperature."},
                    {"time_s": 0, "action": "light_on", "target": "LED_1", "value": 100, "duration_s": None, "notes": "Enable illumination."},
                ],
                "safety_limits": {"max_temperature_c": 85.0, "max_humidity_rh": 20.0},
                "calibration_profile": "latest",
                "notification_profile": "default",
                "notes": "Vacuum + light + heat station recipe skeleton for PSC reliability tests.",
            },
        ]
    }


def _normalize_station_recipe_entry(item: Dict[str, Any], fallback_index: int) -> Optional[Dict[str, Any]]:
    """Normalize one unified Environment / Station recipe entry.

    Legacy station recipes that contained ``smu`` / ``relay`` / ``chamber``
    connection dictionaries are migrated by preserving those fields under
    ``legacy_hardware_profile`` while the active schema focuses on environment
    setpoints and station timelines.
    """
    if not isinstance(item, dict):
        return None

    defaults = _get_default_station_recipes()["recipes"][0]

    def _to_float_or_none(value: Any, default: Optional[float] = None) -> Optional[float]:
        if value in (None, ""):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _to_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on", "enabled"}:
                return True
            if lowered in {"0", "false", "no", "off", "disabled"}:
                return False
        if value is None:
            return bool(default)
        return bool(value)

    def _to_str(value: Any, default: str = "") -> str:
        text = str(value if value is not None else default).strip()
        return text or default

    name = _to_str(item.get("name"), f"Environment Station Recipe {fallback_index}")
    env_type = _to_str(item.get("environment_type", item.get("station_type")), defaults["environment_type"])
    if env_type == "vacuum_glovebox":
        env_type = "glovebox"

    req_raw = item.get("required_hardware", {}) if isinstance(item.get("required_hardware"), dict) else {}
    legacy_chamber = item.get("chamber", {}) if isinstance(item.get("chamber"), dict) else {}
    required_hardware = {
        "smu": _to_bool(req_raw.get("smu"), True),
        "relay": _to_bool(req_raw.get("relay"), True),
        "environment_sensor": _to_bool(req_raw.get("environment_sensor"), True),
        "light_controller": _to_bool(req_raw.get("light_controller"), False),
        "hotplate": _to_bool(req_raw.get("hotplate"), False),
        "chamber": _to_bool(req_raw.get("chamber"), env_type == "climate" or bool(legacy_chamber.get("enabled"))),
        "vacuum": _to_bool(req_raw.get("vacuum"), env_type in {"glovebox", "vacuum"}),
    }

    set_raw = item.get("setpoints", {}) if isinstance(item.get("setpoints"), dict) else {}
    setpoints = {
        "temperature_c": _to_float_or_none(set_raw.get("temperature_c", item.get("temperature_c")), defaults["setpoints"].get("temperature_c")),
        "humidity_rh": _to_float_or_none(set_raw.get("humidity_rh", item.get("humidity_rh"))),
        "pressure_kpa": _to_float_or_none(set_raw.get("pressure_kpa", item.get("vacuum_kpa"))),
        "light_intensity_percent": _to_float_or_none(set_raw.get("light_intensity_percent", item.get("light_intensity_percent")), 0.0),
        "hotplate_temperature_c": _to_float_or_none(set_raw.get("hotplate_temperature_c", item.get("hotplate_temperature_c"))),
    }

    raw_timeline = item.get("timeline")
    timeline: List[Dict[str, Any]] = []
    if isinstance(raw_timeline, list):
        for idx, step in enumerate(raw_timeline, start=1):
            if not isinstance(step, dict):
                continue
            timeline.append({
                "time_s": int(_to_float_or_none(step.get("time_s"), 0) or 0),
                "action": _to_str(step.get("action"), "note"),
                "target": _to_str(step.get("target"), ""),
                "value": step.get("value", ""),
                "duration_s": step.get("duration_s"),
                "notes": _to_str(step.get("notes"), ""),
            })
    if not timeline:
        timeline = list(defaults["timeline"])

    safety_raw = item.get("safety_limits", {}) if isinstance(item.get("safety_limits"), dict) else {}
    safety_limits = {
        "max_temperature_c": _to_float_or_none(safety_raw.get("max_temperature_c"), defaults["safety_limits"].get("max_temperature_c")),
        "max_humidity_rh": _to_float_or_none(safety_raw.get("max_humidity_rh"), defaults["safety_limits"].get("max_humidity_rh")),
    }

    legacy_profile = item.get("legacy_hardware_profile", {}) if isinstance(item.get("legacy_hardware_profile"), dict) else {}
    for legacy_key in ("smu", "relay", "chamber"):
        if isinstance(item.get(legacy_key), dict):
            legacy_profile[legacy_key] = item.get(legacy_key)

    normalized = {
        "name": name,
        "environment_type": env_type,
        "enabled": _to_bool(item.get("enabled"), True),
        "required_hardware": required_hardware,
        "setpoints": setpoints,
        "timeline": timeline,
        "safety_limits": safety_limits,
        "calibration_profile": _to_str(item.get("calibration_profile"), "latest"),
        "notification_profile": _to_str(item.get("notification_profile"), "default"),
        "notes": _to_str(item.get("notes"), ""),
    }
    if legacy_profile:
        normalized["legacy_hardware_profile"] = legacy_profile
    return normalized


def _station_recipe_to_environment_control(recipe: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """Convert unified station recipe into legacy EnvironmentManager format."""
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", str(recipe.get("name", f"recipe_{idx}")).strip()).strip("_").lower()
    recipe_id = slug or f"station_recipe_{idx}"
    setpoints = recipe.get("setpoints", {}) if isinstance(recipe.get("setpoints"), dict) else {}
    req = recipe.get("required_hardware", {}) if isinstance(recipe.get("required_hardware"), dict) else {}
    return {
        "id": recipe_id,
        "name": recipe.get("name", f"Station Recipe {idx}"),
        "environment_type": recipe.get("environment_type", "indoor"),
        "description": recipe.get("notes", ""),
        "enabled": bool(recipe.get("enabled", True)),
        "temperature_c": setpoints.get("temperature_c"),
        "humidity_rh": setpoints.get("humidity_rh"),
        "vacuum_kpa": setpoints.get("pressure_kpa"),
        "illuminance_lux": None,
        "light_on": bool(req.get("light_controller")),
        "timeline": recipe.get("timeline", []),
        "required_hardware": req,
    }


def _sync_station_recipes_to_environment_control(normalized_recipes: List[Dict[str, Any]]) -> None:
    """Persist unified station recipes into the legacy environment recipe file."""
    payload = {
        "recipes": [
            _station_recipe_to_environment_control(recipe, idx)
            for idx, recipe in enumerate(normalized_recipes, start=1)
        ]
    }
    save_json_file(ENVIRONMENT_CONTROL_RECIPES_FILE, payload)


def load_station_recipes() -> Dict[str, Any]:
    """Load unified Environment / Station recipes with migration-safe defaults."""
    defaults = _get_default_station_recipes()
    raw = load_json_file(STATION_RECIPES_FILE, default_data=defaults)
    recipe_items = raw.get("recipes", []) if isinstance(raw, dict) else []
    normalized: List[Dict[str, Any]] = []
    seen_names = set()

    def _append(item: Dict[str, Any], idx: int) -> None:
        entry = _normalize_station_recipe_entry(item, idx)
        if entry is None:
            return
        original_name = entry["name"]
        suffix = 2
        while entry["name"] in seen_names:
            entry["name"] = f"{original_name} ({suffix})"
            suffix += 1
        seen_names.add(entry["name"])
        normalized.append(entry)

    for idx, item in enumerate(defaults.get("recipes", []), start=1):
        _append(item, idx)
    for idx, item in enumerate(recipe_items, start=len(normalized) + 1):
        if isinstance(item, dict) and str(item.get("name", "")) in seen_names:
            continue
        _append(item, idx)

    if not normalized:
        normalized = defaults["recipes"]
    return {"recipes": normalized}


def save_station_recipes(settings: Dict[str, Any]) -> bool:
    """Save unified Environment / Station recipes after normalization."""
    recipe_items = settings.get("recipes", []) if isinstance(settings, dict) else []
    normalized: List[Dict[str, Any]] = []
    seen_names = set()

    for idx, item in enumerate(recipe_items, start=1):
        entry = _normalize_station_recipe_entry(item, idx)
        if entry is None:
            continue
        original_name = entry["name"]
        suffix = 2
        while entry["name"] in seen_names:
            entry["name"] = f"{original_name} ({suffix})"
            suffix += 1
        seen_names.add(entry["name"])
        normalized.append(entry)

    if not normalized:
        normalized = _get_default_station_recipes()["recipes"]

    saved = save_json_file(STATION_RECIPES_FILE, {"recipes": normalized})
    if saved:
        _sync_station_recipes_to_environment_control(normalized)
    return saved


def _get_default_environment_profiles() -> Dict[str, Any]:
    """Return default environment relay ranges used by Relay Mapping."""
    return {
        "instances": {
            "ENV_A_CLIMATE": {
                "type": "climate",
                "title": "Climate Chamber",
                "smu_plus_start": 0,
                "smu_plus_end": 7,
                "smu_minus_start": 32,
                "smu_minus_end": 39,
                "default_env_recipe": "climate_85c_85rh_reliability",
            },
            "ENV_B_INDOOR": {
                "type": "indoor",
                "title": "Indoor Environment",
                "smu_plus_start": 8,
                "smu_plus_end": 15,
                "smu_minus_start": 40,
                "smu_minus_end": 47,
                "default_env_recipe": "indoor_light_soaking_1_sun",
            },
            "ENV_C_GLOVEBOX": {
                "type": "glovebox",
                "title": "Vacuum Glovebox",
                "smu_plus_start": 16,
                "smu_plus_end": 23,
                "smu_minus_start": 48,
                "smu_minus_end": 55,
                "default_env_recipe": "vacuum_light_thermal_stress",
            },
        }
    }


def load_environment_profiles() -> Dict[str, Any]:
    """Load environment relay-range profiles with defaults and bounds."""
    defaults = _get_default_environment_profiles()
    raw = load_json_file(ENVIRONMENT_PROFILES_FILE, default_data=defaults)
    if not isinstance(raw, dict):
        raw = defaults
    instances = raw.get("instances", {})
    if not isinstance(instances, dict):
        instances = {}
    for key, value in defaults["instances"].items():
        instances.setdefault(key, value)
    normalized = {"instances": {}}
    for key, value in instances.items():
        if not isinstance(value, dict):
            continue
        normalized["instances"][str(key)] = {
            "type": str(value.get("type", "indoor")),
            "title": str(value.get("title", key)),
            "smu_plus_start": int(value.get("smu_plus_start", 0)),
            "smu_plus_end": int(value.get("smu_plus_end", 0)),
            "smu_minus_start": int(value.get("smu_minus_start", 32)),
            "smu_minus_end": int(value.get("smu_minus_end", 32)),
            "default_env_recipe": str(value.get("default_env_recipe", "")),
        }
    return normalized


def save_environment_profiles(settings: Dict[str, Any]) -> bool:
    """Save environment relay-range profiles."""
    payload = settings if isinstance(settings, dict) else {}
    if "instances" not in payload:
        payload = {"instances": payload}
    return save_json_file(ENVIRONMENT_PROFILES_FILE, payload)


def _iter_channel_records(payload: Dict[str, Any], *, enabled_only: bool = False) -> List[Dict[str, Any]]:
    """Return normalized channel records from channel_settings payload."""
    records = []
    if not isinstance(payload, dict):
        return records
    for key, item in payload.items():
        if not str(key).isdigit() or not isinstance(item, dict):
            continue
        if enabled_only and not bool(item.get("is_enabled")):
            continue
        record = dict(item)
        record.setdefault("internal_ch_id", int(key))
        record.setdefault("channel_label", f"CH{int(key):02d}")
        records.append(record)
    return records


def get_active_channel_records(channel_payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return channel records currently enabled for cyclic measurement."""
    payload = channel_payload if isinstance(channel_payload, dict) else load_json_file(CHANNEL_SETTINGS_FILE)
    return _iter_channel_records(payload, enabled_only=True)


def infer_environment_for_relay_pair(pos_pin: Any, neg_pin: Any, profiles: Optional[Dict[str, Any]] = None) -> str:
    """Infer environment instance id from relay pair and environment ranges."""
    try:
        pos = int(pos_pin)
        neg = int(neg_pin)
    except (TypeError, ValueError):
        return ""
    env_profiles = profiles if isinstance(profiles, dict) else load_environment_profiles()
    for env_id, item in (env_profiles.get("instances", {}) or {}).items():
        try:
            if int(item.get("smu_plus_start")) <= pos <= int(item.get("smu_plus_end")) and int(item.get("smu_minus_start")) <= neg <= int(item.get("smu_minus_end")):
                return str(env_id)
        except (TypeError, ValueError):
            continue
    return ""


def build_environment_relay_summary(
    channel_payload: Optional[Dict[str, Any]] = None,
    profiles: Optional[Dict[str, Any]] = None,
    *,
    enabled_only: bool = True,
) -> List[Dict[str, Any]]:
    """Build 3x2-style relay usage summary grouped by environment.

    The counts are split by SMU+ and SMU- relay ranges.  Pair capacity left is
    the lower of available plus and minus relays because one device needs both.
    """
    payload = channel_payload if isinstance(channel_payload, dict) else load_json_file(CHANNEL_SETTINGS_FILE)
    env_profiles = profiles if isinstance(profiles, dict) else load_environment_profiles()
    records = _iter_channel_records(payload, enabled_only=enabled_only)
    summary = []
    for env_id, item in (env_profiles.get("instances", {}) or {}).items():
        try:
            plus_range = range(int(item.get("smu_plus_start")), int(item.get("smu_plus_end")) + 1)
            minus_range = range(int(item.get("smu_minus_start")), int(item.get("smu_minus_end")) + 1)
        except (TypeError, ValueError):
            continue
        plus_total = len(plus_range)
        minus_total = len(minus_range)
        plus_used = set()
        minus_used = set()
        channels = []
        for record in records:
            env = str(record.get("environment_instance") or "")
            if not env:
                env = infer_environment_for_relay_pair(record.get("relay_pos"), record.get("relay_neg"), env_profiles)
            if env != env_id:
                continue
            channels.append(record.get("channel_label") or f"CH{record.get('internal_ch_id', '')}")
            try:
                pos = int(record.get("relay_pos"))
                neg = int(record.get("relay_neg"))
            except (TypeError, ValueError):
                continue
            if pos in plus_range:
                plus_used.add(pos)
            if neg in minus_range:
                minus_used.add(neg)
        plus_free = max(0, plus_total - len(plus_used))
        minus_free = max(0, minus_total - len(minus_used))
        summary.append({
            "environment_id": str(env_id),
            "title": str(item.get("title", env_id)),
            "type": str(item.get("type", "")),
            "plus_range": f"{plus_range.start}–{plus_range.stop - 1}",
            "minus_range": f"{minus_range.start}–{minus_range.stop - 1}",
            "plus_used": len(plus_used),
            "plus_total": plus_total,
            "plus_free": plus_free,
            "minus_used": len(minus_used),
            "minus_total": minus_total,
            "minus_free": minus_free,
            "pair_capacity_left": min(plus_free, minus_free),
            "channels": channels,
        })
    return summary


def evaluate_active_rline_readiness(channel_payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Evaluate R-line only for currently enabled channel relay pairs."""
    payload = channel_payload if isinstance(channel_payload, dict) else load_json_file(CHANNEL_SETTINGS_FILE)
    cal_data = load_json_file(CALIBRATION_SETTINGS_FILE)
    rows = []
    for record in get_active_channel_records(payload):
        pos = record.get("relay_pos")
        neg = record.get("relay_neg")
        status = evaluate_rline_calibration(pos, neg, calibration_data=cal_data)
        rows.append({
            "channel_label": record.get("channel_label") or f"CH{record.get('internal_ch_id', '')}",
            "environment_instance": record.get("environment_instance") or infer_environment_for_relay_pair(pos, neg),
            "device_name": record.get("device_name", ""),
            "pos_pin": pos,
            "neg_pin": neg,
            "exists": status.get("exists"),
            "expired": status.get("expired"),
            "age_days": status.get("age_days"),
            "value": status.get("value"),
            "status": "Missing" if not status.get("exists") else ("Expired" if status.get("expired") else "Valid"),
        })
    return rows

# =================================================================
# 2.2 校正與趨勢顯示設定 (Calibration / Trend Runtime Settings)
# =================================================================

DEFAULT_RLINE_CALIBRATION_MAX_AGE_DAYS = 30
DEFAULT_TREND_CACHE_MAX_POINTS = 50000
DEFAULT_TREND_RENDER_THROTTLE_MS = 1000
DEFAULT_SCHEDULER_POLICY_MODE = "flexible_catch_up"
DEFAULT_SCHEDULER_MAX_ALLOWED_DELAY_SEC = 300


def get_rline_calibration_max_age_days(settings: Optional[Dict[str, Any]] = None) -> int:
    """Return the global R-line calibration reminder threshold in days.

    The value is stored in ``config_settings.json`` under
    ``CALIBRATION_SETTINGS.RLINE_MAX_AGE_DAYS``.  Legacy top-level
    ``RLINE_CALIBRATION_MAX_AGE_DAYS`` is also accepted for migration.
    """
    cfg = settings if isinstance(settings, dict) else load_config_settings()
    cal_cfg = cfg.get("CALIBRATION_SETTINGS", {}) if isinstance(cfg, dict) else {}
    raw_value = None
    if isinstance(cal_cfg, dict):
        raw_value = cal_cfg.get("RLINE_MAX_AGE_DAYS")
    if raw_value in (None, "") and isinstance(cfg, dict):
        raw_value = cfg.get("RLINE_CALIBRATION_MAX_AGE_DAYS")
    try:
        days = int(float(raw_value))
    except (TypeError, ValueError):
        days = DEFAULT_RLINE_CALIBRATION_MAX_AGE_DAYS
    return max(1, min(days, 3650))


def get_trend_runtime_settings(settings: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Return bounded-cache and redraw-throttle settings for TrendChartWindow."""
    cfg = settings if isinstance(settings, dict) else load_config_settings()
    trend_cfg = cfg.get("TREND_CHART", {}) if isinstance(cfg, dict) else {}
    if not isinstance(trend_cfg, dict):
        trend_cfg = {}

    def _to_int(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, min(parsed, max_value))

    return {
        "max_in_memory_points": _to_int(
            trend_cfg.get("MAX_IN_MEMORY_POINTS"),
            DEFAULT_TREND_CACHE_MAX_POINTS,
            1000,
            2_000_000,
        ),
        "render_throttle_ms": _to_int(
            trend_cfg.get("RENDER_THROTTLE_MS"),
            DEFAULT_TREND_RENDER_THROTTLE_MS,
            100,
            10_000,
        ),
    }


def get_scheduler_runtime_settings(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return scheduler delay policy settings.

    ``flexible_catch_up`` records delay and still measures overdue channels.
    ``strict_skip`` skips an overdue channel occurrence when the delay exceeds
    ``max_allowed_delay_sec``; the next due time remains anchored to scheduled
    due + interval.
    """
    cfg = settings if isinstance(settings, dict) else load_config_settings()
    policy_cfg = cfg.get("SCHEDULER_POLICY", {}) if isinstance(cfg, dict) else {}
    if not isinstance(policy_cfg, dict):
        policy_cfg = {}
    mode = str(policy_cfg.get("MODE", DEFAULT_SCHEDULER_POLICY_MODE) or DEFAULT_SCHEDULER_POLICY_MODE).strip().lower()
    if mode not in {"flexible_catch_up", "strict_skip"}:
        mode = DEFAULT_SCHEDULER_POLICY_MODE
    try:
        max_delay = int(float(policy_cfg.get("MAX_ALLOWED_DELAY_SEC", DEFAULT_SCHEDULER_MAX_ALLOWED_DELAY_SEC)))
    except (TypeError, ValueError):
        max_delay = DEFAULT_SCHEDULER_MAX_ALLOWED_DELAY_SEC
    max_delay = max(0, min(max_delay, 7 * 24 * 3600))
    return {
        "mode": mode,
        "max_allowed_delay_sec": max_delay,
    }


def parse_timestamp(value: Any) -> Optional[_dt.datetime]:
    """Parse common timestamp strings used by calibration/scheduler metadata."""
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime.combine(value, _dt.time())
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _dt.datetime.fromisoformat(text)
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return _dt.datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def get_line_resistance_record(pos_pin: Any, neg_pin: Any, calibration_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Return a normalized R-line record for one SMU+/SMU- relay pair."""
    if pos_pin in (None, "") or neg_pin in (None, ""):
        return None
    try:
        key = f"{int(pos_pin)}_{int(neg_pin)}"
    except (TypeError, ValueError):
        key = f"{pos_pin}_{neg_pin}"
    cal_data = calibration_data if isinstance(calibration_data, dict) else load_json_file(CALIBRATION_SETTINGS_FILE)
    line_map = cal_data.get("line_resistance_map", {}) if isinstance(cal_data, dict) else {}
    if not isinstance(line_map, dict):
        return None
    raw = line_map.get(key)
    if isinstance(raw, dict):
        record = dict(raw)
        record.setdefault("key", key)
        return record
    if raw is not None:
        return {"key": key, "value": raw, "time": ""}
    return None


def evaluate_rline_calibration(
    pos_pin: Any,
    neg_pin: Any,
    *,
    calibration_data: Optional[Dict[str, Any]] = None,
    max_age_days: Optional[int] = None,
    now: Optional[_dt.datetime] = None,
) -> Dict[str, Any]:
    """Evaluate whether a relay pair has a usable and fresh R-line record."""
    record = get_line_resistance_record(pos_pin, neg_pin, calibration_data)
    threshold = get_rline_calibration_max_age_days() if max_age_days is None else int(max_age_days)
    current_time = now or _dt.datetime.now()
    status = {
        "exists": record is not None,
        "record": record,
        "max_age_days": threshold,
        "timestamp": None,
        "age_days": None,
        "expired": False,
        "value": None,
    }
    if record is None:
        return status
    try:
        status["value"] = float(record.get("value"))
    except (TypeError, ValueError):
        status["value"] = None
    timestamp = parse_timestamp(record.get("time"))
    status["timestamp"] = timestamp
    if timestamp is None:
        # A legacy numeric R-line value without a timestamp is not traceable
        # enough for machine testing; force remeasurement before use.
        status["expired"] = True
        status["timestamp_missing"] = True
        return status

    age_days = max(0.0, (current_time - timestamp).total_seconds() / 86400.0)
    status["age_days"] = age_days
    status["expired"] = age_days > threshold
    status["timestamp_missing"] = False
    return status

# =================================================================
# 3. 使用者路徑安全解析 (User Path Resolution)
# =================================================================

def resolve_user_dir(
    setting_key: str,
    default_dir: Path,
    *,
    settings: Optional[Dict[str, Any]] = None,
    auto_persist: bool = True,
) -> Path:
    """
    解析 user_settings 中的自定義資料夾。
    原則：
    - 若使用者設定路徑合法且可建立，就使用它
    - 若磁碟不存在或建立失敗，就自動回退到 default_dir
    """
    settings_obj = settings if settings is not None else load_user_settings()
    raw_value = settings_obj.get(setting_key)

    candidate = default_dir
    if raw_value and is_safe_path(raw_value):
        candidate = Path(str(raw_value)).expanduser()

    try:
        resolved = ensure_directory(candidate, fallback=default_dir)
    except OSError:
        resolved = ensure_directory(default_dir)

    if auto_persist and str(settings_obj.get(setting_key, "")) != str(resolved):
        settings_obj[setting_key] = str(resolved)
        save_user_settings(settings_obj)

    return resolved


def get_safe_data_dir() -> Path:
    """取得安全可寫入的 data 目錄"""
    settings = load_user_settings()
    return resolve_user_dir("data_dir", BASE_DATA_DIR, settings=settings, auto_persist=True)


def get_safe_log_dir() -> Path:
    """取得安全可寫入的 log 目錄"""
    settings = load_user_settings()
    return resolve_user_dir("log_dir", BASE_LOG_DIR, settings=settings, auto_persist=True)


def sanitize_user_paths() -> Dict[str, Any]:
    """
    清洗 user_settings.json 中的路徑設定：
    若路徑失效，會自動改成程式目錄下的安全路徑
    """
    settings = load_user_settings()
    settings["data_dir"] = str(resolve_user_dir("data_dir", BASE_DATA_DIR, settings=settings, auto_persist=False))
    settings["log_dir"] = str(resolve_user_dir("log_dir", BASE_LOG_DIR, settings=settings, auto_persist=False))
    save_user_settings(settings)
    return settings


# =================================================================
# 4. 硬體通訊與安全邊界 (Hardware & Safety)
# =================================================================

# 載入硬體映射
HARDWARE_MAP = load_hardware_map()

# 載入全域設定
_config_settings = load_config_settings()

def _merged_config_section(section_name: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Return a config_settings.json section merged with safe defaults.

    Args:
        section_name: Top-level section name in ``config_settings.json``.
        defaults: Default values used when the JSON section is missing or
            incomplete.

    Returns:
        Dict[str, Any]: Merged runtime configuration.
    """
    raw = _config_settings.get(section_name, {}) if isinstance(_config_settings, dict) else {}
    merged = dict(defaults)
    if isinstance(raw, dict):
        merged.update(raw)
    return merged


# SMU (GW Instek GSM-20H10) 設定
SMU_CONFIG = _merged_config_section("SMU_CONFIG", {
    "USB_VID": "0x2184",
    "TIMEOUT_MS": 5000,
    "DEFAULT_NPLC": 1.0,
})

# Relay (Numato 64-Ch USB Relay) 設定
# Must remain synced with config/config_settings.json so the GUI Relay tab's
# PORT / BAUDRATE / SAFE_MODE choices are the same values used by RelayDriver.
RELAY_CONFIG = _merged_config_section("RELAY_CONFIG", {
    "INTERFACE_TYPE": "Serial COM",
    "PORT": "",
    "BAUDRATE": 19200,
    "SAFE_MODE": True,
    "IDENTIFIER": "Numato",
    "TOTAL_CHANNELS": 64,
})

# 硬體保護限值 (Global Compliance)
GLOBAL_SAFETY = _config_settings.get("GLOBAL_SAFETY", {
    "V_MAX": 20.0,
    "I_MAX": 0.5,
})

# 時序補償參數
RELAY_SETTLING_MS = _config_settings.get("RELAY_SETTLING_MS", 50)
SMU_SETTLING_MS = _config_settings.get("SMU_SETTLING_MS", 20)

# =================================================================
# 5. 科學計算與量測預設 (Scientific Defaults)
# =================================================================

# 光學與環境常數
STANDARD_SUN_INTENSITY = _config_settings.get("STANDARD_SUN_INTENSITY", 100.0)

# 分析算法參數
ANALYSIS_PARAMS = _config_settings.get("ANALYSIS_PARAMS", {
    "VOC_INTERP_POINTS": 5,
    "RS_FITTING_RANGE": 0.1,
    "RSH_FITTING_RANGE": 0.1,
})

# 量測設定預設值
DEFAULT_MEASURE_CONFIG = {
    "AREA_CM2": 0.1,
    "V_START": -0.1,
    "V_STOP": 1.2,
    "V_STEP": 0.02,
    "DELAY_MS": 50,
    "INTERVAL_MIN": 60,
}

# =================================================================
# 6. 使用者與專案元數據 (Identity & Project)
# =================================================================

_personnel_settings = load_personnel_settings()
USER_PROJECT_MAP = _personnel_settings["USER_PROJECT_MAP"]

# 衍生預設使用者與專案
DEFAULT_USERNAME = ""
DEFAULT_PROJECT = ""
if USER_PROJECT_MAP:
    DEFAULT_USERNAME = next(iter(USER_PROJECT_MAP))
    if USER_PROJECT_MAP.get(DEFAULT_USERNAME):
        DEFAULT_PROJECT = USER_PROJECT_MAP[DEFAULT_USERNAME][0]

# 命名規則
START_ID_FORMAT = "%Y%m%d%H%M%S"

# =================================================================
# 7. UI 視覺樣式與診斷連動 (Interface & UX)
# =================================================================

# 狀態燈號顏色
COLORS = {
    "SUCCESS": "#2ECC71",
    "ERROR": "#E74C3C",
    "WARNING": "#F1C40F",
    "IDLE": "#BDC3C7",
}

# 日誌視窗風格
default_log_style = {
    "BG_COLOR": "#1E1E1E",
    "FONT_FAMILY": "Consolas",
    "FONT_SIZE": 10,
}
user_log_style = _config_settings.get("LOG_WINDOW_STYLE", {})
LOG_WINDOW_STYLE = {**default_log_style, **user_log_style}

# 診斷助手
ERROR_CODES = {
    "-107": "SMU 連線超時，請檢查 USB 線材。",
    "RELAY_FAIL": "繼電器板無回應，請重新插拔控制器。",
    "OPEN_CIRCUIT": "偵測到開路，請檢查電池夾具是否夾好。",
}
