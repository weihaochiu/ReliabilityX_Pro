"""gui/channel_setting_dialog.py

Dynamic logical channel update:
- Keep the user's simple relay-selection workflow.
- Restrict SMU+ / SMU- relay dropdowns to the selected environment instance.
- Automatically show whether a relay is independent or shared with another
  device using the same polarity.
- Block unsafe relay selections where one relay would be used as both SMU+ and
  SMU- across channels.
- Generate stable logical labels such as CH_C01, CH_I01, and CH_V01 while
  retaining the numeric channel id for backward compatibility.
- Infer a legacy channel's environment from its stored logical label or relay
  range so the detail dialog and main card use the same canonical source.
- Generate logical labels with duplicate prevention even when legacy channels
  only have relay settings and no saved `channel_label`.
"""

from datetime import datetime
import csv
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt

import config
from core.environment_manager import EnvironmentManager
from core.channel_identity import normalize_channel_record
from .widgets.channel_action_widget import ChannelActionWidget
from .widgets.channel_environment_widget import ChannelEnvironmentWidget
from .widgets.channel_info_widget import ChannelInfoWidget
from .widgets.channel_param_widget import ChannelParamWidget


class ChannelSettingDialog(QDialog):
    """Widget-based channel settings dialog with environment-limited relay logic."""

    request_line_resistance = pyqtSignal(int, int, int)
    request_spot_check = pyqtSignal(int, int, int, int)

    ENV_PREFIX_MAP = {
        "climate": "C",
        "indoor": "I",
        "glovebox": "V",
        "vacuum": "V",
        "vacuum_glovebox": "V",
    }

    def __init__(self, ch_id, engine, log_manager=None, parent=None):
        super().__init__(parent)
        self.ch_id = int(ch_id)
        self.engine = engine
        self.log_mgr = log_manager
        self.environment_manager = EnvironmentManager()
        self.measurement_recipes = self._load_measurement_recipes()
        self._loaded_channel_label = ""
        self._diag_request_seq = 0
        self._pending_rline_request_id = None
        self._pending_spot_request_id = None

        self.setWindowTitle(f"通道 {self.ch_id:02d} 詳細設定")
        self.setMinimumWidth(620)

        self.init_ui()
        self.connect_signals()
        self.load_settings()

    def init_ui(self):
        """Create child widgets and dialog buttons."""
        layout = QVBoxLayout(self)

        self.info_widget = ChannelInfoWidget()
        self.param_widget = ChannelParamWidget()
        self.environment_widget = ChannelEnvironmentWidget()
        self.action_widget = ChannelActionWidget()

        self.param_widget.set_measurement_recipes(
            [
                item.get("name", "")
                for item in self.measurement_recipes
                if isinstance(item, dict)
            ]
        )
        self.environment_widget.set_environment_options(
            self.environment_manager.list_instances()
        )

        layout.addWidget(self.info_widget)
        layout.addWidget(self.param_widget)
        layout.addWidget(self.environment_widget)
        layout.addWidget(self.action_widget)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("儲存設定")
        self.btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def connect_signals(self):
        """Wire dialog signals."""
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel.clicked.connect(self.reject)
        self.action_widget.measure_rline_clicked.connect(self.run_rline_measurement)
        self.action_widget.spot_check_clicked.connect(self.run_connection_test)

        self.action_widget.combo_relay_pos.currentTextChanged.connect(
            self._on_relay_selection_changed
        )
        self.action_widget.combo_relay_neg.currentTextChanged.connect(
            self._on_relay_selection_changed
        )
        self.environment_widget.combo_environment.currentTextChanged.connect(
            self._on_environment_changed
        )
        self.param_widget.combo_measurement_recipe.currentTextChanged.connect(
            self._apply_measurement_recipe
        )

        if self.engine is not None:
            if hasattr(self.engine, "request_line_resistance_measurement"):
                self.request_line_resistance.connect(
                    self.engine.request_line_resistance_measurement,
                    Qt.ConnectionType.QueuedConnection,
                )
            if hasattr(self.engine, "request_spot_check"):
                self.request_spot_check.connect(
                    self.engine.request_spot_check,
                    Qt.ConnectionType.QueuedConnection,
                )
            if hasattr(self.engine, "line_resistance_result"):
                self.engine.line_resistance_result.connect(self._on_rline_measurement_result)
            if hasattr(self.engine, "spot_check_result"):
                self.engine.spot_check_result.connect(self._on_spot_check_result)

    def _load_measurement_recipes(self):
        """Load measurement recipes from the config layer."""
        try:
            payload = config.load_measurement_recipes()
            return payload.get("recipes", []) if isinstance(payload, dict) else []
        except Exception:
            return []

    def _apply_measurement_recipe(self, recipe_name: str):
        """Apply a selected measurement recipe into numeric fields."""
        if not recipe_name or recipe_name == "-- 選擇 Recipe --":
            return

        recipe = next(
            (
                item
                for item in self.measurement_recipes
                if isinstance(item, dict)
                and str(item.get("name", "")) == recipe_name
            ),
            None,
        )
        if not recipe:
            return

        self.param_widget.set_data(
            {
                "measurement_recipe": recipe_name,
                "v_start": recipe.get("v_start"),
                "v_stop": recipe.get("v_stop"),
                "v_step": recipe.get("v_step"),
                "delay_time": recipe.get("delay_time_ms", recipe.get("delay_time")),
                "interval_min": recipe.get(
                    "measurement_interval_min", recipe.get("interval_min")
                ),
                "area": recipe.get("area_cm2", recipe.get("area")),
                "i_limit": recipe.get("current_limit_a", recipe.get("i_limit")),
            }
        )

    def _load_line_resistance_map(self):
        """Load the calibration line-resistance map."""
        try:
            cal_data = config.load_json_file(config.CALIBRATION_SETTINGS_FILE)
            if not isinstance(cal_data, dict):
                return {}
            line_map = cal_data.get("line_resistance_map", {})
            return line_map if isinstance(line_map, dict) else {}
        except Exception as e:
            if self.log_mgr:
                self.log_mgr.log_error(f"Failed to load line resistance map: {e}")
            return {}

    def _rline_max_age_days(self) -> int:
        try:
            return config.get_rline_calibration_max_age_days()
        except Exception:
            return 30

    def _selected_rline_status(self, relay_pos=None, relay_neg=None):
        """Return normalized R-line calibration status for the selected relay pair."""
        if relay_pos is None or relay_neg is None:
            pos_pin, neg_pin = self._selected_relay_ints()
        else:
            pos_pin, neg_pin = relay_pos, relay_neg
        if pos_pin is None or neg_pin is None:
            return {"exists": False, "record": None, "expired": False, "age_days": None, "max_age_days": self._rline_max_age_days()}
        cal_data = config.load_json_file(config.CALIBRATION_SETTINGS_FILE)
        if not isinstance(cal_data, dict):
            cal_data = {}
        return config.evaluate_rline_calibration(
            pos_pin,
            neg_pin,
            calibration_data=cal_data,
            max_age_days=self._rline_max_age_days(),
        )

    def _append_rline_history_csv(self, row_data):
        """Append one R-line diagnostic row to data/rline_history.csv."""
        history_path = config.get_safe_data_dir() / "rline_history.csv"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "timestamp",
            "operator",
            "user",
            "project",
            "device_name",
            "channel_label",
            "environment_instance",
            "pos_pin",
            "neg_pin",
            "source_current_A",
            "measured_voltage_V",
            "measured_current_A",
            "line_resistance_ohm",
            "request_id",
            "status",
            "note",
        ]
        exists = history_path.exists() and history_path.stat().st_size > 0
        with open(history_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow({key: row_data.get(key, "") for key in fieldnames})

    def _on_environment_changed(self, environment_instance: str):
        """Refresh environment metadata and relay dropdown ranges."""
        instance = self.environment_manager.get_instance(environment_instance)
        if instance is None:
            self.environment_widget.set_environment_meta("-")
            self.environment_widget.set_environment_recipe_options([])
            self.action_widget.set_relay_options([], [])
            self._on_relay_selection_changed()
            return

        relay_range = self.environment_manager.get_relay_range(environment_instance)
        pos_options = [
            str(i)
            for i in range(
                relay_range["smu_plus"][0], relay_range["smu_plus"][1] + 1
            )
        ]
        neg_options = [
            str(i)
            for i in range(
                relay_range["smu_minus"][0], relay_range["smu_minus"][1] + 1
            )
        ]
        self.action_widget.set_relay_options(pos_options, neg_options)

        self.environment_widget.set_environment_meta(instance.env_type)
        env_recipe_ids = self.environment_manager.get_environment_recipe_ids(
            instance.env_type
        )
        self.environment_widget.set_environment_recipe_options(env_recipe_ids)

        if instance.default_env_recipe:
            if (
                self.environment_widget.combo_environment_recipe.findText(
                    instance.default_env_recipe
                )
                >= 0
            ):
                self.environment_widget.combo_environment_recipe.setCurrentText(
                    instance.default_env_recipe
                )

        self._on_relay_selection_changed()

    def _environment_instance_for_prefix(self, prefix: str) -> str:
        """Return the first configured environment instance matching a label prefix."""
        type_groups = {
            "C": {"climate"},
            "I": {"indoor"},
            "V": {"glovebox", "vacuum", "vacuum_glovebox"},
        }
        wanted = type_groups.get(str(prefix or "").upper(), set())
        for instance_id in self.environment_manager.list_instances():
            instance = self.environment_manager.get_instance(instance_id)
            env_type = str(getattr(instance, "env_type", "") or "").strip().lower()
            if env_type in wanted:
                return instance_id
        return ""

    def _infer_environment_instance_from_settings(self, settings: dict) -> str:
        """Infer the canonical environment instance for legacy channel settings.

        Args:
            settings: Saved channel settings from `channel_settings.json`.

        Returns:
            Environment instance id. The method first trusts an existing valid
            `environment_instance`, then falls back to the CH_C / CH_I / CH_V
            label prefix, and finally to the configured relay ranges. This keeps
            the detail dialog, main card grouping, and generated channel name
            aligned.
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

        return saved or self.environment_widget.combo_environment.currentText()

    def load_settings(self):
        """Load saved channel settings into the dialog."""
        all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        ch_settings_key = str(self.ch_id)
        s = all_settings.get(ch_settings_key, {})
        self._loaded_channel_label = str(s.get("channel_label", "") or "")

        title_label = self._loaded_channel_label or f"CH{self.ch_id:02d}"
        self.setWindowTitle(f"{title_label} 詳細設定")

        self.info_widget.set_data(
            {
                "enabled": s.get("is_enabled", False),
                "user": s.get("user"),
                "project": s.get("project"),
                "device_name": s.get("device_name"),
            }
        )

        self.param_widget.set_data(
            {
                "measurement_recipe": s.get("measurement_recipe"),
                "v_start": s.get("v_start"),
                "v_stop": s.get("v_stop"),
                "v_step": s.get("v_step"),
                "delay_time": s.get("delay_time"),
                "interval_min": s.get("interval_min"),
                "area": s.get("area"),
                "i_limit": s.get("i_limit"),
            }
        )

        env_instance = self._infer_environment_instance_from_settings(s)
        self.environment_widget.set_data(
            {
                "environment_instance": env_instance,
                "environment_recipe": s.get("environment_recipe"),
            }
        )
        if (
            env_instance
            and self.environment_widget.combo_environment.findText(str(env_instance))
            >= 0
        ):
            self.environment_widget.combo_environment.setCurrentText(str(env_instance))
        self._on_environment_changed(
            self.environment_widget.combo_environment.currentText()
        )

        saved_env_recipe = s.get("environment_recipe")
        if (
            saved_env_recipe
            and self.environment_widget.combo_environment_recipe.findText(
                str(saved_env_recipe)
            )
            >= 0
        ):
            self.environment_widget.combo_environment_recipe.setCurrentText(
                str(saved_env_recipe)
            )

        ch_hw_key = f"CH{self.ch_id}"
        mapping = config.HARDWARE_MAP.get(ch_hw_key)

        pos_pin, neg_pin = None, None
        if "relay_pos" in s:
            pos_pin = s.get("relay_pos")
        elif mapping and "pos" in mapping:
            pos_pin = mapping.get("pos")

        if "relay_neg" in s:
            neg_pin = s.get("relay_neg")
        elif mapping and "neg" in mapping:
            neg_pin = mapping.get("neg")

        calibration_data = self._load_line_resistance_map()
        self.action_widget.set_data(
            {
                "relay_pos": pos_pin,
                "relay_neg": neg_pin,
            },
            calibration_data,
        )

        self._on_relay_selection_changed()

    def _environment_prefix(self, environment_instance: str) -> str:
        """Return the logical-channel prefix letter for an environment."""
        instance = self.environment_manager.get_instance(environment_instance)
        env_type = str(getattr(instance, "env_type", "") or "").strip().lower()
        return self.ENV_PREFIX_MAP.get(env_type, "X")

    def _device_label(self, settings: dict, fallback_ch_id: str | int = "") -> str:
        """Return a readable device/channel label for confirmation messages."""
        device = str((settings or {}).get("device_name") or "").strip()
        label = str((settings or {}).get("channel_label") or "").strip()
        if device and label:
            return f"{label} / {device}"
        if device:
            return device
        if label:
            return label
        return f"CH{int(fallback_ch_id):02d}" if str(fallback_ch_id).isdigit() else "未知元件"

    def _has_complete_relay_path(self, settings: dict) -> bool:
        """Return whether a settings entry represents a real logical channel."""
        if not isinstance(settings, dict):
            return False
        try:
            int(settings.get("relay_pos"))
            int(settings.get("relay_neg"))
            return True
        except (TypeError, ValueError):
            return False

    def _label_number(self, label: str, prefix: str) -> int | None:
        """Extract numeric suffix from `CH_<prefix>##` labels."""
        label = str(label or "").strip()
        token = f"CH_{prefix}"
        if not label.startswith(token):
            return None
        try:
            return int(label.replace(token, "", 1))
        except ValueError:
            return None

    def _prefix_from_saved_settings(self, settings: dict) -> str:
        """Infer channel prefix from saved environment, label, or relay range."""
        settings = settings or {}
        env_instance = self._infer_environment_instance_from_settings(settings)
        prefix = self._environment_prefix(env_instance)
        if prefix != "X":
            return prefix

        label = str(settings.get("channel_label") or "").strip()
        for candidate in ("C", "I", "V"):
            if label.startswith(f"CH_{candidate}"):
                return candidate
        return "X"

    def _next_channel_label(self, all_settings: dict, environment_instance: str) -> str:
        """Generate the next stable logical channel label for an environment.

        Explicit labels are reserved first. Valid legacy channels that have a
        relay path but no saved label are assigned derived numbers in internal-id
        order so a new channel cannot duplicate a visible CH_I01 / CH_C01 / CH_V01.
        """
        prefix = self._environment_prefix(environment_instance)
        current_number = self._label_number(self._loaded_channel_label, prefix)
        if current_number is not None:
            return f"CH_{prefix}{current_number:02d}"

        used_numbers = set()
        unlabeled_same_prefix_ids = []
        for key, item in (all_settings or {}).items():
            if str(key) == str(self.ch_id) or not str(key).isdigit() or not self._has_complete_relay_path(item):
                continue
            item_prefix = self._prefix_from_saved_settings(item)
            if item_prefix != prefix:
                continue
            item_number = self._label_number((item or {}).get("channel_label"), prefix)
            if item_number is not None:
                used_numbers.add(item_number)
            else:
                unlabeled_same_prefix_ids.append(int(key))

        unlabeled_same_prefix_ids.sort()
        next_number = 1
        for _item_id in unlabeled_same_prefix_ids:
            while next_number in used_numbers:
                next_number += 1
            used_numbers.add(next_number)
            next_number += 1

        next_number = 1
        while next_number in used_numbers:
            next_number += 1
        return f"CH_{prefix}{next_number:02d}"

    def _selected_relay_ints(self):
        """Return selected relay ids as integers when possible."""
        action_data = self.action_widget.get_data()
        pos_text = str(action_data.get("relay_pos", "") or "").strip()
        neg_text = str(action_data.get("relay_neg", "") or "").strip()
        try:
            pos_pin = int(pos_text) if pos_text != "" else None
        except ValueError:
            pos_pin = None
        try:
            neg_pin = int(neg_text) if neg_text != "" else None
        except ValueError:
            neg_pin = None
        return pos_pin, neg_pin

    def _relay_usage_info(self, relay_pin: int | None, polarity: str, all_settings=None):
        """Analyze whether one relay is independent, shared, or conflicted.

        Args:
            relay_pin: Relay id selected by the user.
            polarity: `pos` for SMU+ or `neg` for SMU-.
            all_settings: Optional preloaded channel settings.

        Returns:
            dict: Contains `hint`, `level`, `conflicts`, and `shared` entries.
        """
        if relay_pin is None:
            label = "SMU+" if polarity == "pos" else "SMU−"
            return {
                "hint": f"{label} Relay: 請先選擇 relay。",
                "level": "idle",
                "conflicts": [],
                "shared": [],
            }

        all_settings = all_settings if all_settings is not None else config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        same_polarity = []
        opposite_polarity = []
        same_key = "relay_pos" if polarity == "pos" else "relay_neg"
        opposite_key = "relay_neg" if polarity == "pos" else "relay_pos"
        polarity_text = "正極" if polarity == "pos" else "負極"
        opposite_text = "負極" if polarity == "pos" else "正極"
        selector_text = "SMU+" if polarity == "pos" else "SMU−"

        for key, item in (all_settings or {}).items():
            if str(key) == str(self.ch_id) or not isinstance(item, dict):
                continue
            try:
                if item.get(same_key) is not None and int(item.get(same_key)) == relay_pin:
                    same_polarity.append(self._device_label(item, key))
                if item.get(opposite_key) is not None and int(item.get(opposite_key)) == relay_pin:
                    opposite_polarity.append(self._device_label(item, key))
            except (TypeError, ValueError):
                continue

        if opposite_polarity:
            names = "、".join(opposite_polarity)
            return {
                "hint": f"錯誤：Relay {relay_pin} 已被 {names} 用作{opposite_text}，不可同時作為{polarity_text}使用。",
                "level": "error",
                "conflicts": opposite_polarity,
                "shared": same_polarity,
            }

        if same_polarity:
            names = "、".join(same_polarity)
            return {
                "hint": f"提示：Relay {relay_pin} 將與 {names} 共用{polarity_text}。",
                "level": "shared",
                "conflicts": [],
                "shared": same_polarity,
            }

        return {
            "hint": f"提示：Relay {relay_pin} 為獨立 relay。",
            "level": "independent",
            "conflicts": [],
            "shared": [],
        }

    def _relay_in_environment_range(self, pos_pin, neg_pin, environment_instance: str) -> tuple[bool, str]:
        """Validate that relay selections remain within the selected environment."""
        if pos_pin is None or neg_pin is None:
            return True, ""
        relay_range = self.environment_manager.get_relay_range(environment_instance)
        pos_range = relay_range.get("smu_plus", (None, None))
        neg_range = relay_range.get("smu_minus", (None, None))
        if not (pos_range[0] <= pos_pin <= pos_range[1]):
            return False, (
                f"SMU+ Relay {pos_pin} 不在目前環境允許範圍 "
                f"{pos_range[0]}–{pos_range[1]} 內，不可跨區域選取。"
            )
        if not (neg_range[0] <= neg_pin <= neg_range[1]):
            return False, (
                f"SMU− Relay {neg_pin} 不在目前環境允許範圍 "
                f"{neg_range[0]}–{neg_range[1]} 內，不可跨區域選取。"
            )
        return True, ""

    def _on_relay_selection_changed(self):
        """Refresh R-line and relay-sharing hint labels after relay changes."""
        self.update_rline_from_selected_relays()
        pos_pin, neg_pin = self._selected_relay_ints()
        all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        pos_info = self._relay_usage_info(pos_pin, "pos", all_settings)
        neg_info = self._relay_usage_info(neg_pin, "neg", all_settings)

        if pos_pin is not None and neg_pin is not None and pos_pin == neg_pin:
            pos_info = {
                **pos_info,
                "hint": f"錯誤：Relay {pos_pin} 不可同時作為 SMU+ 與 SMU−。",
                "level": "error",
                "conflicts": ["same_channel"],
            }
            neg_info = {
                **neg_info,
                "hint": f"錯誤：Relay {neg_pin} 不可同時作為 SMU+ 與 SMU−。",
                "level": "error",
                "conflicts": ["same_channel"],
            }

        self.action_widget.set_relay_usage_hints(
            pos_info.get("hint"),
            neg_info.get("hint"),
            pos_info.get("level", "idle"),
            neg_info.get("level", "idle"),
        )

    def _confirm_shared_relays_if_needed(self, pos_info, neg_info) -> bool:
        """Ask user to confirm same-polarity relay sharing before saving."""
        shared_lines = []
        if pos_info.get("shared"):
            shared_lines.append(pos_info.get("hint", ""))
        if neg_info.get("shared"):
            shared_lines.append(neg_info.get("hint", ""))
        if not shared_lines:
            return True

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("確認共用 Relay")
        msg.setText("目前設定會與既有元件共用相同極性的 relay。")
        msg.setInformativeText(
            "\n".join(shared_lines)
            + "\n\n請確認這是您的實驗接線設計。"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        return msg.exec() == QMessageBox.StandardButton.Yes

    def save_settings(self):
        """Validate and persist one logical channel setting."""
        info_data = self.info_widget.get_data()
        param_data = self.param_widget.get_data()
        env_data = self.environment_widget.get_data()
        action_data = self.action_widget.get_data()
        environment_instance = env_data.get("environment_instance")

        if info_data["enabled"]:
            if not all(
                [info_data["user"], info_data["project"], info_data["device_name"]]
            ):
                QMessageBox.warning(
                    self,
                    "輸入不完整",
                    "開始循環量測時，使用者、專案與元件名稱不可為空。",
                )
                return
            if not action_data.get("relay_pos") or not action_data.get("relay_neg"):
                QMessageBox.warning(
                    self,
                    "輸入不完整",
                    "開始循環量測時，必須指定 SMU+ Relay 和 SMU− Relay。",
                )
                return

        try:
            relay_pos_val = action_data.get("relay_pos")
            relay_neg_val = action_data.get("relay_neg")
            relay_pos = int(relay_pos_val) if relay_pos_val else None
            relay_neg = int(relay_neg_val) if relay_neg_val else None

            if relay_pos is not None and relay_neg is not None and relay_pos == relay_neg:
                QMessageBox.critical(
                    self,
                    "Relay 設定錯誤",
                    f"Relay {relay_pos} 不可同時作為 SMU+ 與 SMU−，這會造成短路風險。",
                )
                return

            in_range, range_message = self._relay_in_environment_range(
                relay_pos, relay_neg, environment_instance
            )
            if not in_range:
                QMessageBox.critical(self, "Relay 跨區域錯誤", range_message)
                return

            if relay_pos is not None and relay_neg is not None:
                rline_status = self._selected_rline_status(relay_pos, relay_neg)
                if not rline_status.get("exists") or rline_status.get("value") is None:
                    QMessageBox.warning(
                        self,
                        "尚未完成線阻量測",
                        (
                            f"目前選擇的 SMU+ Relay {relay_pos} / SMU− Relay {relay_neg} 尚未做過 R-line 線路阻抗量測。\n\n"
                            "為避免使用錯誤線阻補償，請先按下「量測線路阻抗」完成此組合校正後，再儲存 Channel 設定。"
                        ),
                    )
                    return
                if rline_status.get("expired"):
                    age_days = rline_status.get("age_days")
                    max_age_days = rline_status.get("max_age_days")
                    reply = QMessageBox.warning(
                        self,
                        "R-line 校正已超過提醒期限",
                        (
                            f"目前選擇的 SMU+ Relay {relay_pos} / SMU− Relay {relay_neg} 已有 R-line 紀錄，"
                            f"但距離上次量測約 {age_days:.0f} 天，超過全域設定的 {max_age_days} 天提醒門檻。\n\n"
                            "建議重新量測線阻以維持電壓補償追蹤性。是否仍要儲存設定？"
                        ),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return

            all_settings = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
            pos_info = self._relay_usage_info(relay_pos, "pos", all_settings)
            neg_info = self._relay_usage_info(relay_neg, "neg", all_settings)
            if pos_info.get("conflicts") or neg_info.get("conflicts"):
                QMessageBox.critical(
                    self,
                    "Relay 極性衝突",
                    "\n".join(
                        [
                            item.get("hint", "")
                            for item in [pos_info, neg_info]
                            if item.get("conflicts")
                        ]
                    ),
                )
                return

            if not self._confirm_shared_relays_if_needed(pos_info, neg_info):
                return

            channel_label = self._next_channel_label(all_settings, environment_instance)
            new_data = {
                "channel_label": channel_label,
                "is_enabled": info_data["enabled"],
                "user": info_data["user"],
                "project": info_data["project"],
                "device_name": info_data["device_name"],
                "environment_instance": environment_instance,
                "environment_recipe": env_data.get("environment_recipe"),
                **param_data,
                "relay_pos": relay_pos,
                "relay_neg": relay_neg,
            }
            new_data = normalize_channel_record(new_data, self.ch_id, assign_experiment_uid=True)

            all_settings[str(self.ch_id)] = new_data
            config.save_json_file(config.CHANNEL_SETTINGS_FILE, all_settings)

            if self.log_mgr:
                self.log_mgr.log_info(
                    f"Channel {self.ch_id} active relay assignment saved in channel_settings.json: +R{relay_pos} / -R{relay_neg}; hardware_map.json kept as template only."
                )

            self._loaded_channel_label = channel_label
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "儲存失敗", f"發生未預期的錯誤: {e}")
            if self.log_mgr:
                self.log_mgr.log_error(
                    f"Channel {self.ch_id} settings save failed: {e}"
                )

    def update_rline_from_selected_relays(self):
        """Update R-line readout for the selected relay path."""
        try:
            pos_text = self.action_widget.combo_relay_pos.currentText().strip()
            neg_text = self.action_widget.combo_relay_neg.currentText().strip()
            line_map = self._load_line_resistance_map()
            self.action_widget.update_rline_display(pos_text, neg_text, line_map, self._rline_max_age_days())
        except Exception as e:
            self.action_widget.show_rline_error("讀取失敗")
            if self.log_mgr:
                self.log_mgr.log_error(
                    f"Failed to update R-line from selected relays: {e}"
                )

    def _next_diag_request_id(self):
        self._diag_request_seq += 1
        return (int(self.ch_id) * 100000) + self._diag_request_seq

    @pyqtSlot()
    def run_rline_measurement(self):
        """Request line-resistance measurement through a queued engine signal."""
        action_data = self.action_widget.get_data()
        pos_pin_str = action_data.get("relay_pos", "").strip()
        neg_pin_str = action_data.get("relay_neg", "").strip()

        if not pos_pin_str or not neg_pin_str:
            QMessageBox.warning(self, "輸入不完整", "請先選擇 SMU+ Relay 與 SMU− Relay。")
            return

        reply = QMessageBox.question(
            self,
            "確認操作",
            (
                f"即將量測實體繼電器 (Pins) '{pos_pin_str}' 與 '{neg_pin_str}' 間的線路電阻。\n"
                "請確認對應的探針/夾具已『確實短路』。"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        try:
            pos_pin = int(pos_pin_str)
            neg_pin = int(neg_pin_str)
        except Exception:
            QMessageBox.warning(self, "輸入錯誤", "Relay pin 必須是數字。")
            return

        request_id = self._next_diag_request_id()
        self._pending_rline_request_id = request_id
        self.action_widget.btn_measure_rline.setEnabled(False)
        self.action_widget.btn_measure_rline.setText("量測中...")
        self.request_line_resistance.emit(request_id, pos_pin, neg_pin)

    @pyqtSlot(dict)
    def _on_rline_measurement_result(self, result):
        if not isinstance(result, dict) or result.get("request_id") != self._pending_rline_request_id:
            return
        self._pending_rline_request_id = None
        self.action_widget.btn_measure_rline.setEnabled(True)
        self.action_widget.btn_measure_rline.setText("量測線路阻抗")

        if not result.get("ok"):
            QMessageBox.critical(self, "量測失敗", str(result.get("error") or "無法量測線路電阻，請檢查日誌。"))
            return

        try:
            pos_pin = int(result.get("pos_pin"))
            neg_pin = int(result.get("neg_pin"))
            resistance = float(result.get("resistance"))
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cal_data = config.load_json_file(config.CALIBRATION_SETTINGS_FILE)
            if not isinstance(cal_data, dict):
                cal_data = {}

            info_data = self.info_widget.get_data()
            env_data = self.environment_widget.get_data()
            cal_key = f"{pos_pin}_{neg_pin}"
            record = {
                "value": round(resistance, 4),
                "time": now_str,
                "operator": info_data.get("user", ""),
                "user": info_data.get("user", ""),
                "project": info_data.get("project", ""),
                "device_name": info_data.get("device_name", ""),
                "channel_label": self._loaded_channel_label or f"CH{self.ch_id:02d}",
                "environment_instance": env_data.get("environment_instance", ""),
                "source_current_A": result.get("source_current_A", ""),
                "measured_voltage_V": result.get("measured_voltage_V", ""),
                "measured_current_A": result.get("measured_current_A", ""),
                "request_id": result.get("request_id", ""),
            }
            cal_data.setdefault("line_resistance_map", {})[cal_key] = record
            config.save_json_file(config.CALIBRATION_SETTINGS_FILE, cal_data)
            self._append_rline_history_csv({
                "timestamp": now_str,
                "operator": record["operator"],
                "user": record["user"],
                "project": record["project"],
                "device_name": record["device_name"],
                "channel_label": record["channel_label"],
                "environment_instance": record["environment_instance"],
                "pos_pin": pos_pin,
                "neg_pin": neg_pin,
                "source_current_A": record["source_current_A"],
                "measured_voltage_V": record["measured_voltage_V"],
                "measured_current_A": record["measured_current_A"],
                "line_resistance_ohm": round(resistance, 6),
                "request_id": record["request_id"],
                "status": "ok",
                "note": "Measured from ChannelSettingDialog queued diagnostics",
            })
            self.update_rline_from_selected_relays()
            QMessageBox.information(self, "量測成功", f"線路電阻量測完畢: {resistance:.4f} Ω")
        except Exception as e:
            QMessageBox.critical(self, "量測失敗", f"儲存線路阻抗結果時發生錯誤: {e}")
            if self.log_mgr:
                self.log_mgr.log_error(f"Channel {self.ch_id} R-line measurement result handling failed: {e}")

    @pyqtSlot()
    def run_connection_test(self):
        """Request Isc-based connection/polarity diagnostic through queued signal."""
        action_data = self.action_widget.get_data()
        pos_pin_str = action_data.get("relay_pos", "").strip()
        neg_pin_str = action_data.get("relay_neg", "").strip()

        if not pos_pin_str or not neg_pin_str:
            QMessageBox.warning(self, "輸入不完整", "請先選擇 SMU+ Relay 與 SMU− Relay。")
            return

        try:
            pos_pin = int(pos_pin_str)
            neg_pin = int(neg_pin_str)
        except Exception:
            QMessageBox.warning(self, "輸入錯誤", "Relay pin 必須是數字。")
            return

        request_id = self._next_diag_request_id()
        self._pending_spot_request_id = request_id
        self.action_widget.btn_spot_check.setText("診斷中...")
        self.action_widget.btn_spot_check.setEnabled(False)
        self.request_spot_check.emit(request_id, self.ch_id, pos_pin, neg_pin)

    @pyqtSlot(dict)
    def _on_spot_check_result(self, result):
        if not isinstance(result, dict) or result.get("request_id") != self._pending_spot_request_id:
            return
        self._pending_spot_request_id = None
        self.action_widget.btn_spot_check.setEnabled(True)
        self.action_widget.btn_spot_check.setText("即時連線測試")

        if not result.get("ok"):
            QMessageBox.critical(self, "診斷失敗", str(result.get("error") or "執行硬體診斷時發生錯誤，請檢查日誌。"))
            return

        try:
            i_msd = float(result["i_msd"])
            if i_msd > 10e-6:
                status_text = "⚠️ 可能正負極夾反"
                color = "red"
                msg = f"偵測到正向電流 ({i_msd:.2e} A)，可能為正負極反接，請檢查接線。"
            elif i_msd < -10e-6:
                status_text = "✅ 連線正常 (Isc 已偵測)"
                color = "green"
                msg = f"偵測到負向短路電流 ({i_msd:.2e} A)，連線狀態正常。"
            else:
                status_text = "❌ 斷路或無光照"
                color = "orange"
                msg = (
                    f"近零電流 ({i_msd:.2e} A)，可能為開路、接觸不良或無光照，"
                    "請檢查電池與光源。"
                )

            self.action_widget.update_isc_status(i_msd, status_text, color)
            QMessageBox.information(self, "硬體診斷結果", msg)
        except Exception as e:
            QMessageBox.critical(self, "診斷失敗", f"處理即時連線測試結果時發生錯誤: {e}")
            if self.log_mgr:
                self.log_mgr.log_error(f"Channel {self.ch_id} connection test result handling failed: {e}")
