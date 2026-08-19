"""gui/config_tabs/relay_tab.py

Relay / Channel Mapping tab for ReliabilityX Pro.

This pure-Python tab replaces the legacy .ui-loaded relay page with an
environment-aware mapping view:
- relay ranges are editable per environment;
- occupancy is summarized as a 3 x 2 SMU+/SMU- matrix;
- active channel mappings are shown by environment;
- the relay matrix is filtered by environment so unused environments do not
  create false blocking errors;
- safe-mode help explains the relay behavior in scientific/operator language.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import config
from core.channel_identity import build_relay_occupancy
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    import serial.tools.list_ports
except Exception:  # pragma: no cover - serial may be absent on CI/dev machines
    serial = None


class RelayTab(QWidget):
    """Environment-aware relay mapping, occupancy, and diagnostics tab."""

    def __init__(self, engine, parent: Optional[QWidget] = None) -> None:
        """Initialize RelayTab.

        Args:
            engine: Runtime measurement engine; may be None in config-only mode.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.engine = engine
        self.relay_driver = getattr(engine, "relay", None) if engine is not None else None
        self.hw_map_editor: Dict[str, Dict[str, int]] = {}
        self.environment_profiles_editor: Dict[str, Any] = {}
        self._env_range_widgets: Dict[str, Dict[str, QSpinBox]] = {}
        self.relay_buttons: Dict[int, QPushButton] = {}
        self._is_loading = False
        self.init_ui()
        self.init_signals()

    def init_ui(self) -> None:
        """Build all relay mapping widgets without uic.loadUi."""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        hint = QLabel(
            "Relay / Channel Mapping 只處理 relay 分區、通道對照與佔用狀態。\n"
            "Dashboard readiness 只會檢查目前 active channel 實際使用的 relay pair 與環境。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555555;")
        root.addWidget(hint)

        top_row = QHBoxLayout()
        top_row.addWidget(self._build_connection_group(), 1)
        top_row.addWidget(self._build_summary_group(), 2)
        root.addLayout(top_row)

        range_row = QHBoxLayout()
        range_row.addWidget(self._build_environment_range_group(), 2)
        range_row.addWidget(self._build_active_mapping_group(), 3)
        root.addLayout(range_row, 2)

        root.addWidget(self._build_matrix_group(), 3)

    def _build_connection_group(self) -> QGroupBox:
        """Build low-level relay connection controls retained for traceability."""
        group = QGroupBox("Relay Connection / Safe Mode")
        form = QFormLayout(group)
        self.relay_interface_combo = QComboBox()
        self.relay_interface_combo.addItems(["Serial COM", "USB", "LAN"])
        self.relay_port_combo = QComboBox()
        self.combo_relay_baud = QComboBox()
        self.combo_relay_baud.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.safe_mode_chk = QCheckBox("啟用安全模式")
        self.safe_mode_chk.setChecked(True)
        self.safe_mode_help_btn = QPushButton("說明")
        self.default_map_btn = QPushButton("重建預設 CH1-CH32 mapping")
        self.reset_relays_btn = QPushButton("Reset all relays")
        self.scan_ports_btn = QPushButton("掃描 COM")
        safe_row = QHBoxLayout()
        safe_row.addWidget(self.safe_mode_chk)
        safe_row.addWidget(self.safe_mode_help_btn)
        safe_row.addStretch(1)
        port_row = QHBoxLayout()
        port_row.addWidget(self.relay_port_combo, 1)
        port_row.addWidget(self.scan_ports_btn)
        form.addRow("Interface", self.relay_interface_combo)
        form.addRow("Port", port_row)
        form.addRow("Baudrate", self.combo_relay_baud)
        form.addRow("Safe Mode", safe_row)
        form.addRow(self.default_map_btn)
        form.addRow(self.reset_relays_btn)
        return group

    def _build_summary_group(self) -> QGroupBox:
        """Build the environment x polarity relay summary table."""
        group = QGroupBox("3×2 Relay Occupancy Summary")
        layout = QVBoxLayout(group)
        self.summary_table = QTableWidget(0, 6)
        self.summary_table.setHorizontalHeaderLabels([
            "Environment", "SMU+ Used/Total", "SMU+ Free", "SMU− Used/Total", "SMU− Free", "Pair Left"
        ])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.summary_table)
        return group

    def _build_environment_range_group(self) -> QGroupBox:
        """Build editable environment relay range table."""
        group = QGroupBox("Environment Relay Range Editor")
        layout = QVBoxLayout(group)
        self.range_table = QTableWidget(0, 7)
        self.range_table.setHorizontalHeaderLabels([
            "Environment", "Title", "Type", "SMU+ Start", "SMU+ End", "SMU− Start", "SMU− End"
        ])
        self.range_table.verticalHeader().setVisible(False)
        self.range_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.range_table)
        return group

    def _build_active_mapping_group(self) -> QGroupBox:
        """Build active channel relay mapping table."""
        group = QGroupBox("Active Channel Mapping")
        layout = QVBoxLayout(group)
        self.active_mapping_table = QTableWidget(0, 8)
        self.active_mapping_table.setHorizontalHeaderLabels([
            "Channel", "Environment", "User", "Project", "Device", "SMU+", "SMU−", "R-line"
        ])
        self.active_mapping_table.verticalHeader().setVisible(False)
        self.active_mapping_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.active_mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.active_mapping_table)
        return group

    def _build_matrix_group(self) -> QGroupBox:
        """Build environment-filtered relay matrix."""
        group = QGroupBox("Relay Matrix by Environment")
        layout = QVBoxLayout(group)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Environment:"))
        self.combo_matrix_environment = QComboBox()
        filter_row.addWidget(self.combo_matrix_environment)
        self.btn_refresh = QPushButton("Refresh")
        filter_row.addWidget(self.btn_refresh)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)
        legend = QLabel("淺色底搭配深色字；黃色 = active channel 佔用；藍色系 = SMU+；灰色系 = SMU−。")
        legend.setWordWrap(True)
        legend.setStyleSheet("color: #555555;")
        layout.addWidget(legend)
        self.matrix_widget = QWidget()
        self.matrix_layout = QGridLayout(self.matrix_widget)
        self.matrix_layout.setHorizontalSpacing(6)
        self.matrix_layout.setVerticalSpacing(6)
        layout.addWidget(self.matrix_widget)
        return group

    def init_signals(self) -> None:
        """Connect widget signals to slots."""
        self.scan_ports_btn.clicked.connect(self._scan_com_ports)
        self.default_map_btn.clicked.connect(self._set_default_mapping)
        self.reset_relays_btn.clicked.connect(self._reset_all_relays)
        self.safe_mode_help_btn.clicked.connect(self._show_safe_mode_help)
        self.combo_matrix_environment.currentTextChanged.connect(lambda _text: self._populate_matrix())
        self.btn_refresh.clicked.connect(self._refresh_all)

    def load_settings(self, settings: dict) -> None:
        """Load settings and populate UI fields."""
        self._is_loading = True
        try:
            relay_conf = settings.get("RELAY_CONFIG", {}) if isinstance(settings, dict) else {}
            self.relay_interface_combo.setCurrentText(relay_conf.get("INTERFACE_TYPE", "Serial COM"))
            self.combo_relay_baud.setCurrentText(str(relay_conf.get("BAUDRATE", 19200)))
            self.safe_mode_chk.setChecked(bool(relay_conf.get("SAFE_MODE", True)))
            current_port = relay_conf.get("PORT", "")
            self._scan_com_ports(show_errors=False)
            if current_port:
                if self.relay_port_combo.findText(str(current_port)) < 0:
                    self.relay_port_combo.addItem(str(current_port))
                self.relay_port_combo.setCurrentText(str(current_port))

            self.hw_map_editor = json.loads(json.dumps(settings.get("HARDWARE_MAP", {})))
            self.environment_profiles_editor = config.load_environment_profiles()
            self._populate_environment_ranges()
            self._populate_environment_filter()
            self._refresh_all()
        finally:
            self._is_loading = False

    def get_settings(self) -> dict:
        """Read UI fields and return mapping, relay config, and env profiles."""
        self._collect_environment_ranges_from_table()
        self._validate_environment_ranges()
        relay_conf = {
            "INTERFACE_TYPE": self.relay_interface_combo.currentText(),
            "PORT": self.relay_port_combo.currentText(),
            "BAUDRATE": int(self.combo_relay_baud.currentText()),
            "SAFE_MODE": self.safe_mode_chk.isChecked(),
        }
        return {
            "HARDWARE_MAP": self.hw_map_editor,
            "RELAY_CONFIG": relay_conf,
            "ENVIRONMENT_PROFILES": self.environment_profiles_editor,
        }

    def cleanup(self) -> None:
        """Placeholder for compatibility with SystemConfigDialog cleanup."""
        return

    def _scan_com_ports(self, show_errors: bool = True) -> None:
        """Scan available COM ports for relay connection settings."""
        current = self.relay_port_combo.currentText()
        self.relay_port_combo.clear()
        ports: List[str] = []
        try:
            if serial is not None:
                ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception as exc:
            if show_errors:
                QMessageBox.critical(self, "掃描失敗", f"掃描 COM Port 時發生錯誤: {exc}")
        self.relay_port_combo.addItems(ports)
        if current:
            if self.relay_port_combo.findText(current) < 0:
                self.relay_port_combo.addItem(current)
            self.relay_port_combo.setCurrentText(current)

    def _show_safe_mode_help(self) -> None:
        """Explain relay safe mode to scientists/operators."""
        QMessageBox.information(
            self,
            "啟用安全模式說明",
            "啟用安全模式時，系統在手動打開任何 relay 前，會先關閉其他 relay，避免多個不相容通道同時導通。\n\n"
            "這是為了避免 SMU 正負端被錯誤短接、避免不同電池互相並聯、避免繼電器接點在帶電狀態下切換造成電弧。\n\n"
            "正式量測時仍應由量測引擎控制 relay；手動切換只建議用於接線診斷，而且應確認 SMU output 已關閉。",
        )

    def _set_default_mapping(self) -> None:
        """Rebuild legacy CH1-CH32 default mapping from the current ranges."""
        self.hw_map_editor = {f"CH{i + 1}": {"pos": i, "neg": i + 32} for i in range(32)}
        self._refresh_all()

    def _reset_all_relays(self) -> None:
        """Reset all relay outputs if hardware is connected."""
        if not self.relay_driver or not getattr(self.relay_driver, "is_connected", False):
            QMessageBox.warning(self, "錯誤", "Relay 板未連線。")
            return
        self.relay_driver.reset_all()
        for btn in self.relay_buttons.values():
            btn.setChecked(False)
        QMessageBox.information(self, "操作成功", "所有繼電器均已重置為關閉狀態。")

    def _refresh_all(self) -> None:
        """Refresh all dynamic relay tables and matrices."""
        self._collect_environment_ranges_from_table(silent=True)
        self._populate_summary_table()
        self._populate_active_mapping_table()
        self._populate_matrix()

    def _populate_environment_ranges(self) -> None:
        """Render environment profiles into editable range rows."""
        instances = self.environment_profiles_editor.get("instances", {}) if isinstance(self.environment_profiles_editor, dict) else {}
        self.range_table.setRowCount(0)
        self._env_range_widgets.clear()
        for row, (env_id, item) in enumerate(instances.items()):
            self.range_table.insertRow(row)
            for col, text in enumerate([env_id, item.get("title", env_id), item.get("type", "")]):
                table_item = QTableWidgetItem(str(text))
                table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.range_table.setItem(row, col, table_item)
            widgets = {}
            for col, key in enumerate(["smu_plus_start", "smu_plus_end", "smu_minus_start", "smu_minus_end"], start=3):
                spin = QSpinBox()
                spin.setRange(0, 63)
                spin.setValue(int(item.get(key, 0)))
                spin.valueChanged.connect(lambda _value, env=env_id: self._on_range_changed(env))
                self.range_table.setCellWidget(row, col, spin)
                widgets[key] = spin
            self._env_range_widgets[env_id] = widgets

    def _populate_environment_filter(self) -> None:
        """Populate matrix environment filter."""
        current = self.combo_matrix_environment.currentText()
        self.combo_matrix_environment.blockSignals(True)
        self.combo_matrix_environment.clear()
        for env_id, item in (self.environment_profiles_editor.get("instances", {}) or {}).items():
            title = item.get("title", env_id)
            self.combo_matrix_environment.addItem(f"{title} ({env_id})", env_id)
        if current:
            index = self.combo_matrix_environment.findText(current)
            if index >= 0:
                self.combo_matrix_environment.setCurrentIndex(index)
        self.combo_matrix_environment.blockSignals(False)

    def _on_range_changed(self, _env_id: str) -> None:
        """Persist edited ranges to memory and refresh summaries."""
        if self._is_loading:
            return
        self._refresh_all()

    def _collect_environment_ranges_from_table(self, silent: bool = False) -> None:
        """Copy range spin-box values into the in-memory profile payload."""
        instances = self.environment_profiles_editor.setdefault("instances", {})
        for row in range(self.range_table.rowCount()):
            env_item = self.range_table.item(row, 0)
            if env_item is None:
                continue
            env_id = env_item.text()
            item = instances.setdefault(env_id, {})
            widgets = self._env_range_widgets.get(env_id, {})
            for key, spin in widgets.items():
                item[key] = int(spin.value())

    def _validate_environment_ranges(self) -> None:
        """Ensure environment relay ranges do not overlap within each polarity."""
        instances = self.environment_profiles_editor.get("instances", {}) if isinstance(self.environment_profiles_editor, dict) else {}
        plus_owners: Dict[int, str] = {}
        minus_owners: Dict[int, str] = {}
        for env_id, item in instances.items():
            ps, pe = int(item.get("smu_plus_start", 0)), int(item.get("smu_plus_end", 0))
            ns, ne = int(item.get("smu_minus_start", 32)), int(item.get("smu_minus_end", 32))
            if ps > pe or ns > ne:
                raise ValueError(f"{env_id} relay range start 不可大於 end。")
            for pin in range(ps, pe + 1):
                if pin in plus_owners:
                    raise ValueError(f"SMU+ relay {pin} 同時被 {plus_owners[pin]} 與 {env_id} 使用。")
                plus_owners[pin] = env_id
            for pin in range(ns, ne + 1):
                if pin in minus_owners:
                    raise ValueError(f"SMU− relay {pin} 同時被 {minus_owners[pin]} 與 {env_id} 使用。")
                minus_owners[pin] = env_id

    def _active_payload(self) -> Dict[str, Any]:
        """Load channel settings payload for active mapping views."""
        try:
            return config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        except Exception:
            return {}

    def _populate_summary_table(self) -> None:
        """Render environment relay summary counts."""
        summary = config.build_environment_relay_summary(
            self._active_payload(), self.environment_profiles_editor, enabled_only=True
        )
        self.summary_table.setRowCount(len(summary))
        for row, item in enumerate(summary):
            values = [
                f"{item['title']} ({item['environment_id']})",
                f"{item['plus_used']} / {item['plus_total']}",
                str(item["plus_free"]),
                f"{item['minus_used']} / {item['minus_total']}",
                str(item["minus_free"]),
                str(item["pair_capacity_left"]),
            ]
            for col, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                if col > 0:
                    table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.summary_table.setItem(row, col, table_item)

    def _rline_text(self, pos: Any, neg: Any) -> str:
        """Return short R-line status text for active mapping table."""
        if pos in (None, "") or neg in (None, ""):
            return "Missing relay"
        status = config.evaluate_rline_calibration(pos, neg)
        if not status.get("exists"):
            return "Missing"
        value = status.get("value")
        if value is None:
            return "Invalid"
        suffix = " expired" if status.get("expired") else ""
        return f"{value:.4f} Ω{suffix}"

    def _populate_active_mapping_table(self) -> None:
        """Render active channel relay mappings."""
        records = config.get_active_channel_records(self._active_payload())
        self.active_mapping_table.setRowCount(len(records))
        for row, record in enumerate(records):
            pos = record.get("relay_pos")
            neg = record.get("relay_neg")
            env = record.get("environment_instance") or config.infer_environment_for_relay_pair(pos, neg, self.environment_profiles_editor)
            values = [
                record.get("channel_label") or f"CH{record.get('internal_ch_id', '')}",
                env,
                record.get("user", ""),
                record.get("project", ""),
                record.get("device_name", ""),
                "" if pos is None else str(pos),
                "" if neg is None else str(neg),
                self._rline_text(pos, neg),
            ]
            for col, value in enumerate(values):
                self.active_mapping_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _clear_matrix_layout(self) -> None:
        """Remove old matrix widgets."""
        while self.matrix_layout.count():
            item = self.matrix_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.relay_buttons.clear()

    def _selected_environment_id(self) -> str:
        """Return selected environment id from combo data."""
        data = self.combo_matrix_environment.currentData()
        return str(data or "")

    def _pin_owner_text(self, pin: int, occupancy: Dict[int, List[Dict[str, Any]]]) -> str:
        """Return concise owner text for one relay pin."""
        owners = occupancy.get(pin, [])
        if not owners:
            return "Free"
        return "; ".join(f"{item.get('channel_label')}/{item.get('device_name') or '-'}" for item in owners)

    def _populate_matrix(self) -> None:
        """Render relay buttons for selected environment only."""
        self._clear_matrix_layout()
        env_id = self._selected_environment_id()
        instances = self.environment_profiles_editor.get("instances", {}) if isinstance(self.environment_profiles_editor, dict) else {}
        item = instances.get(env_id, {}) if env_id else {}
        if not item:
            return
        try:
            plus_pins = list(range(int(item.get("smu_plus_start")), int(item.get("smu_plus_end")) + 1))
            minus_pins = list(range(int(item.get("smu_minus_start")), int(item.get("smu_minus_end")) + 1))
        except (TypeError, ValueError):
            return
        try:
            occupancy = build_relay_occupancy(self._active_payload())
        except Exception:
            occupancy = {}
        self.matrix_layout.addWidget(QLabel("SMU+"), 0, 0)
        for col, pin in enumerate(plus_pins, start=1):
            self._add_matrix_button(pin, 0, col, occupancy, True)
        self.matrix_layout.addWidget(QLabel("SMU−"), 1, 0)
        for col, pin in enumerate(minus_pins, start=1):
            self._add_matrix_button(pin, 1, col, occupancy, False)

    def _add_matrix_button(self, pin: int, row: int, col: int, occupancy: Dict[int, List[Dict[str, Any]]], is_plus: bool) -> None:
        """Add one relay matrix button."""
        btn = QPushButton(str(pin))
        btn.setCheckable(True)
        btn.setMinimumWidth(44)
        occupied = pin in occupancy
        btn.setToolTip(self._pin_owner_text(pin, occupancy))
        if occupied:
            btn.setStyleSheet("background: #FFE08A; color: #1F1F1F; font-weight: 700;")
        elif is_plus:
            btn.setStyleSheet("background: #D8E9FF; color: #102033;")
        else:
            btn.setStyleSheet("background: #E8EAED; color: #1F1F1F;")
        btn.clicked.connect(lambda checked, n=pin: self._toggle_relay(n, checked))
        self.relay_buttons[pin] = btn
        self.matrix_layout.addWidget(btn, row, col)

    def _toggle_relay(self, relay_num: int, state: bool) -> None:
        """Manual relay toggle with safe-mode reset."""
        if not self.relay_driver or not getattr(self.relay_driver, "is_connected", False):
            QMessageBox.warning(self, "錯誤", "Relay 板未連線。請先確認 Relay Connection。")
            if relay_num in self.relay_buttons:
                self.relay_buttons[relay_num].setChecked(False)
            return
        if self.safe_mode_chk.isChecked() and state:
            self.relay_driver.reset_all()
            for pin, btn in self.relay_buttons.items():
                if pin != relay_num and btn.isChecked():
                    btn.setChecked(False)
            time.sleep(0.05)
        if state:
            self.relay_driver.switch_on(relay_num)
        else:
            self.relay_driver.switch_off(relay_num)
