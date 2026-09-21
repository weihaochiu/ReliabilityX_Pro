"""gui/system_config_dialog.py

OI-045 implementation:
- OI-055: catch page validation errors before any persistent settings writes.
- Replace the old top-level QTabWidget page stack with a left-navigation shell.
- Add a Dashboard landing page for status summary and quick jumps.
- Separate Measurement Recipe and Station Recipe into independent pages.
- Add an Advanced Settings page with collapsed-by-default panels.
- Keep existing config tab widgets embedded in the new shell to minimize
  regression risk for the first shell refactor phase.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import config

from .config_tabs.chamber_tab import ChamberTab
from .config_tabs.environment_recipe_tab import EnvironmentRecipeTab
from .config_tabs.environment_tab.environment_tab_main import EnvironmentTab
from .config_tabs.measurement_tab import MeasurementTab
from .config_tabs.notification_tab import NotificationTab
from .config_tabs.personnel_tab import PersonnelTab
from .config_tabs.recipe_tab import RecipeTab
from .config_tabs.relay_tab import RelayTab
from .config_tabs.smu_tab import SMUTab
from .config_tabs.station_recipe_tab import StationRecipeTab
from .config_tabs.rline_diagnostics_tab import RLineDiagnosticsTab


class CollapsibleSection(QWidget):
    """Small collapsible panel used by the Advanced Settings page."""

    def __init__(self, title: str, content: QWidget, parent: Optional[QWidget] = None) -> None:
        """Create a collapsed section.

        Args:
            title: Section title shown on the toggle button.
            content: Widget to show when expanded.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setStyleSheet("font-weight: 600; text-align: left;")

        self.content = content
        self.content.setVisible(False)
        self.toggle.toggled.connect(self._on_toggled)

        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

    def _on_toggled(self, checked: bool) -> None:
        """Show or hide the body widget."""
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.content.setVisible(checked)


class DashboardPage(QWidget):
    """Task-oriented dashboard for SystemConfigDialog.

    The dashboard intentionally checks only resources required by currently
    enabled channel cards.  Offline unused environments are shown as ignored,
    not as blocking errors.
    """

    def __init__(self, dialog: "SystemConfigDialog") -> None:
        """Initialize the dashboard page."""
        super().__init__(dialog)
        self.dialog = dialog
        self.status_labels: Dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        """Build task-readiness cards and tables."""
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(14)

        intro = QLabel(
            "Dashboard 只檢查目前 active channel cards 實際會用到的 relay pair、R-line、environment 與硬體。"
            "\n未使用的 chamber / vacuum / hotplate 離線時不會被列為 blocking error。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #555555;")
        root.addWidget(intro)

        status_group = QGroupBox("本次任務 Readiness / Active Task Readiness")
        grid = QGridLayout(status_group)
        cards = [
            ("ready", "Ready to Start", "整合 active channel、relay、R-line 與必要環境。"),
            ("active_channels", "Active Channels", "目前勾選開始循環量測的 channel cards。"),
            ("required_env", "Required Environments", "只列入 active channel 實際使用的環境。"),
            ("rline", "R-line", "只檢查 active relay pair 的校正狀態。"),
            ("relay", "Relay Capacity", "依環境拆成 SMU+ / SMU− 使用量。"),
            ("ignored", "Ignored Offline", "未使用設備不阻擋量測。"),
        ]
        for idx, (key, title, hint) in enumerate(cards):
            grid.addWidget(self._build_status_card(key, title, hint), idx // 3, idx % 3)
        root.addWidget(status_group)

        relay_group = QGroupBox("Relay Occupancy 3×2 Summary")
        relay_layout = QVBoxLayout(relay_group)
        self.relay_summary_table = QTableWidget(0, 6)
        self.relay_summary_table.setHorizontalHeaderLabels([
            "Environment", "SMU+ Used/Total", "SMU+ Free", "SMU− Used/Total", "SMU− Free", "Pair Left"
        ])
        self.relay_summary_table.verticalHeader().setVisible(False)
        self.relay_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        relay_layout.addWidget(self.relay_summary_table)
        root.addWidget(relay_group)

        detail_row = QHBoxLayout()
        env_group = QGroupBox("Required Environment Status")
        env_layout = QVBoxLayout(env_group)
        self.env_table = QTableWidget(0, 4)
        self.env_table.setHorizontalHeaderLabels(["Environment", "Used by", "Status", "Blocking"])
        self.env_table.verticalHeader().setVisible(False)
        self.env_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        env_layout.addWidget(self.env_table)
        detail_row.addWidget(env_group, 3)

        rline_group = QGroupBox("Active R-line Status")
        rline_layout = QVBoxLayout(rline_group)
        self.rline_table = QTableWidget(0, 6)
        self.rline_table.setHorizontalHeaderLabels(["Channel", "Env", "SMU+", "SMU−", "R-line Ω", "Status"])
        self.rline_table.verticalHeader().setVisible(False)
        self.rline_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rline_layout.addWidget(self.rline_table)
        detail_row.addWidget(rline_group, 4)
        root.addLayout(detail_row, 2)

        jump_group = QGroupBox("快速前往 / Quick Jump")
        jump_grid = QGridLayout(jump_group)
        jumps = [
            ("使用者與專案", "users"),
            ("Channel Overview", "channel_overview"),
            ("量測 Recipe", "measurement_recipes"),
            ("Environment / Station Recipe", "station_recipes"),
            ("Relay / Channel 對照", "relay_mapping"),
            ("R-line Diagnostics", "rline_diagnostics"),
            ("硬體連線", "hardware"),
            ("通知與報告", "notifications"),
            ("進階設定", "advanced"),
        ]
        for idx, (label, page_key) in enumerate(jumps):
            btn = QPushButton(label)
            btn.setMinimumHeight(34)
            btn.clicked.connect(lambda _checked=False, key=page_key: self.dialog.select_page(key))
            jump_grid.addWidget(btn, idx // 3, idx % 3)
        root.addWidget(jump_group)

    def _build_status_card(self, key: str, title: str, hint: str) -> QFrame:
        """Build one dashboard status card."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame { border: 1px solid #D8DDE6; border-radius: 8px; background: #FAFBFC; }"
            "QLabel { border: none; background: transparent; color: #1F1F1F; }"
        )
        layout = QVBoxLayout(frame)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #1F1F1F;")
        lbl_status = QLabel("--")
        lbl_status.setStyleSheet("font-size: 14px; font-weight: 600; color: #555555;")
        lbl_hint = QLabel(hint)
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("font-size: 11px; color: #555555;")
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_status)
        layout.addWidget(lbl_hint)
        self.status_labels[key] = lbl_status
        return frame

    def refresh(self) -> None:
        """Refresh readiness from active channel settings."""
        payload = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        active_records = config.get_active_channel_records(payload)
        rline_rows = config.evaluate_active_rline_readiness(payload)
        relay_summary = config.build_environment_relay_summary(payload, config.load_environment_profiles(), enabled_only=True)
        required_envs = self._required_environment_map(active_records)

        missing_rline = sum(1 for row in rline_rows if row.get("status") == "Missing")
        expired_rline = sum(1 for row in rline_rows if row.get("status") == "Expired")
        incomplete_relay = sum(1 for rec in active_records if rec.get("relay_pos") in (None, "") or rec.get("relay_neg") in (None, ""))
        blocking = missing_rline + incomplete_relay
        ready_text = "Yes" if active_records and blocking == 0 else "No"
        self._set_status("ready", f"{ready_text} | Blocking={blocking}, Warnings={expired_rline}")
        self._set_status("active_channels", str(len(active_records)))
        self._set_status("required_env", ", ".join(required_envs.keys()) if required_envs else "None")
        self._set_status("rline", f"Valid={len(rline_rows)-missing_rline-expired_rline}, Missing={missing_rline}, Expired={expired_rline}")
        self._set_status("relay", f"{sum(item['pair_capacity_left'] for item in relay_summary)} pair slots left")
        ignored = self._ignored_environment_count(required_envs)
        self._set_status("ignored", f"{ignored} unused environment(s) ignored")

        self._populate_relay_summary(relay_summary)
        self._populate_environment_table(required_envs)
        self._populate_rline_table(rline_rows)

    def _required_environment_map(self, active_records: List[Dict[str, object]]) -> Dict[str, List[str]]:
        """Return env_id -> channels for active records."""
        mapping: Dict[str, List[str]] = {}
        for record in active_records:
            env = str(record.get("environment_instance") or "")
            if not env:
                env = config.infer_environment_for_relay_pair(record.get("relay_pos"), record.get("relay_neg"))
            label = str(record.get("channel_label") or f"CH{record.get('internal_ch_id', '')}")
            mapping.setdefault(env or "Unassigned", []).append(label)
        return mapping

    def _ignored_environment_count(self, required_envs: Dict[str, List[str]]) -> int:
        """Count configured environments unused by active channels."""
        profiles = config.load_environment_profiles()
        configured = set((profiles.get("instances", {}) or {}).keys())
        return max(0, len(configured - set(required_envs.keys())))

    def _populate_relay_summary(self, summary: List[Dict[str, object]]) -> None:
        """Populate relay summary table."""
        self.relay_summary_table.setRowCount(len(summary))
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
                cell = QTableWidgetItem(str(value))
                if col > 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.relay_summary_table.setItem(row, col, cell)

    def _populate_environment_table(self, required_envs: Dict[str, List[str]]) -> None:
        """Populate required environment status table."""
        self.env_table.setRowCount(len(required_envs))
        for row, (env, channels) in enumerate(required_envs.items()):
            # Hardware availability is intentionally conservative and only
            # blocking for selected environment types that require a driver.
            status = "Required"
            blocking = "No"
            if env == "Unassigned":
                status = "Missing environment"
                blocking = "Yes"
            elif "CLIMATE" in env.upper():
                chamber = getattr(getattr(self.dialog, "engine", None), "chamber_driver", None)
                checker = getattr(chamber, "is_connected", None) if chamber is not None else None
                connected = bool(checker()) if callable(checker) else bool(getattr(chamber, "connected", False))
                status = "Connected" if connected else "Not connected"
                blocking = "Yes" if not connected else "No"
            values = [env, ", ".join(channels), status, blocking]
            for col, value in enumerate(values):
                self.env_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _populate_rline_table(self, rows: List[Dict[str, object]]) -> None:
        """Populate active R-line table."""
        self.rline_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = [
                item.get("channel_label", ""),
                item.get("environment_instance", ""),
                item.get("pos_pin", ""),
                item.get("neg_pin", ""),
                "" if item.get("value") is None else f"{float(item.get('value')):.4f}",
                item.get("status", ""),
            ]
            for col, value in enumerate(values):
                self.rline_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _set_status(self, key: str, text: str) -> None:
        """Update one status label if it exists."""
        label = self.status_labels.get(key)
        if label is not None:
            label.setText(text)


class ChannelOverviewPage(QWidget):
    """Read-only overview of current channel setting cards."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the channel overview page."""
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        """Build table and controls."""
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        hint = QLabel("此頁用 active channel card 的角度彙整 user/project/device、recipe、environment、relay 與 R-line 狀態。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555555;")
        root.addWidget(hint)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        root.addWidget(self.btn_refresh, alignment=Qt.AlignmentFlag.AlignRight)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Enabled", "Channel", "User", "Project", "Device", "Environment", "Measurement Recipe", "Station Recipe", "Relay", "R-line"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

    def refresh(self) -> None:
        """Refresh channel overview table."""
        payload = config.load_json_file(config.CHANNEL_SETTINGS_FILE)
        records = []
        for key, item in (payload or {}).items():
            if str(key).isdigit() and isinstance(item, dict):
                record = dict(item)
                record.setdefault("internal_ch_id", key)
                records.append(record)
        records.sort(key=lambda rec: str(rec.get("channel_label") or rec.get("internal_ch_id")))
        self.table.setRowCount(len(records))
        for row, rec in enumerate(records):
            relay_text = f"{rec.get('relay_pos', '')} / {rec.get('relay_neg', '')}"
            status = config.evaluate_rline_calibration(rec.get("relay_pos"), rec.get("relay_neg"))
            rline_text = "Missing" if not status.get("exists") else ("Expired" if status.get("expired") else f"{status.get('value'):.4f} Ω")
            values = [
                "Yes" if rec.get("is_enabled") else "No",
                rec.get("channel_label") or f"CH{rec.get('internal_ch_id', '')}",
                rec.get("user", ""),
                rec.get("project", ""),
                rec.get("device_name", ""),
                rec.get("environment_instance", ""),
                rec.get("measurement_recipe", ""),
                rec.get("environment_recipe", ""),
                relay_text,
                rline_text,
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))


class AdvancedSettingsPage(QWidget):
    """Collapsed-by-default advanced settings overview page."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the advanced settings page."""
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build collapsed panels for advanced/debug-only information."""
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)

        warning = QLabel(
            "這一頁只放低頻率、高風險或開發者用途設定。預設收合，避免一般實驗操作者誤改。"
            "\nAdvanced settings are collapsed by default to prevent accidental edits."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #7A4A00; font-weight: 600;")
        root.addWidget(warning)

        root.addWidget(CollapsibleSection("路徑與設定檔 / Paths and Config Files", self._build_paths_panel()))
        root.addWidget(CollapsibleSection("JSON 狀態摘要 / JSON State Summary", self._build_json_summary_panel()))
        root.addWidget(CollapsibleSection("開發者備註 / Developer Notes", self._build_notes_panel()))
        root.addStretch(1)

    def _build_paths_panel(self) -> QWidget:
        """Create the paths panel."""
        panel = QWidget()
        layout = QGridLayout(panel)
        rows = [
            ("BASE_DIR", str(config.BASE_DIR)),
            ("BASE_DATA_DIR", str(config.BASE_DATA_DIR)),
            ("BASE_LOG_DIR", str(config.BASE_LOG_DIR)),
            ("BASE_CONFIG_DIR", str(config.BASE_CONFIG_DIR)),
            ("CONFIG_SETTINGS_FILE", str(config.CONFIG_SETTINGS_FILE)),
            ("STATION_RECIPES_FILE", str(config.STATION_RECIPES_FILE)),
        ]
        for row, (name, value) in enumerate(rows):
            layout.addWidget(QLabel(name), row, 0)
            label = QLabel(value)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(label, row, 1)
        return panel

    def _build_json_summary_panel(self) -> QWidget:
        """Create a read-only JSON summary panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setMaximumHeight(220)
        summary = {
            "config_settings_keys": sorted(config.load_config_settings().keys()),
            "personnel_users": sorted(config.load_personnel_settings().get("USER_PROJECT_MAP", {}).keys()),
            "measurement_recipe_count": len(config.load_measurement_recipes().get("recipes", [])),
            "station_recipe_count": len(config.load_station_recipes().get("recipes", [])),
            "hardware_map_count": len(config.load_hardware_map()),
        }
        text.setPlainText(json.dumps(summary, indent=2, ensure_ascii=False))
        layout.addWidget(text)
        return panel

    def _build_notes_panel(self) -> QWidget:
        """Create developer notes for future refactor phases."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        notes = QLabel(
            "Phase 1 shell refactor keeps legacy config tab widgets embedded. "
            "Future phases may split Relay connection vs Relay mapping, migrate all tabs away from uic.loadUi(), "
            "and add role-based permissions before exposing reset/raw JSON actions."
        )
        notes.setWordWrap(True)
        layout.addWidget(notes)
        return panel


class SystemConfigDialog(QDialog):
    """System configuration shell dialog.

    The dialog is now a controller-style shell: left navigation selects pages in
    a right-side QStackedWidget.  Existing config tab widgets are embedded to
    keep behavior stable while making the information architecture clearer.
    """

    def __init__(self, parent=None) -> None:
        """Initialize dialog and load current settings.

        Args:
            parent: Parent widget, expected to expose ``engine``.
        """
        super().__init__(parent)
        self.engine = getattr(parent, "engine", None)
        self._page_keys: List[str] = []
        self._page_widgets: Dict[str, List[QWidget]] = {}

        self.original_main_settings = config.load_config_settings()
        self.original_personnel_settings = config.load_personnel_settings()
        self.original_user_settings = config.load_user_settings()
        self.original_hw_map = config.load_hardware_map()
        self.original_notification_settings = config.load_notification_settings()
        self.original_recipe_settings = config.load_measurement_recipes()
        self.original_station_recipe_settings = config.load_station_recipes()

        self.init_ui()
        self.load_data_to_tabs()

    def init_ui(self) -> None:
        """Build the shell UI and instantiate embedded config pages."""
        self.setWindowTitle("全域設定 / System Configuration")
        self.setMinimumSize(1120, 760)
        self.resize(1260, 820)

        self.tab_personnel = PersonnelTab(self)
        self.tab_smu = SMUTab(self.engine, self)
        self.tab_relay = RelayTab(self.engine, self)
        self.tab_chamber = ChamberTab(self.engine, self)
        self.tab_measurement = MeasurementTab(self)
        self.tab_recipe = RecipeTab(self)
        self.tab_station_recipe = StationRecipeTab(self)
        self.channel_overview_page = ChannelOverviewPage(self)
        self.rline_diagnostics_tab = RLineDiagnosticsTab(self)
        self.tab_env = EnvironmentTab(parent=self, engine=self.engine)
        self.tab_notification = NotificationTab(self)

        self.tab_env.open_environment_recipe_requested.connect(self.open_environment_recipe_tab)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("全域設定 / System Configuration")
        header.setStyleSheet("font-size: 20px; font-weight: 700;")
        root.addWidget(header)

        subtitle = QLabel("左側選擇設定區塊，右側編輯內容。Dashboard 以 active channel cards 做任務導向 readiness 檢查，未使用環境不列為錯誤。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666666;")
        root.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.nav_list = QListWidget()
        self.nav_list.setMinimumWidth(250)
        self.nav_list.setMaximumWidth(330)
        self.nav_list.setSpacing(3)
        self.nav_list.currentRowChanged.connect(self._on_page_changed)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self.nav_list)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._build_pages()

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setText("儲存並套用 / Save && Apply")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消 / Cancel")
        self.button_box.accepted.connect(self.save_all_settings)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

        self.nav_list.setCurrentRow(0)

    def _build_pages(self) -> None:
        """Create shell pages and add them to the navigation stack."""
        self.dashboard_page = DashboardPage(self)
        self._add_page(
            "dashboard",
            "首頁總覽 / Dashboard",
            "首頁總覽 / Dashboard",
            "先確認硬體、校正、通知與 recipe library 狀態。",
            self.dashboard_page,
        )
        self._add_page(
            "users",
            "使用者與專案 / Users & Projects",
            "使用者與專案 / Users & Projects",
            "維護使用者清單與 project ownership；Email 報告與主管 CC 會在 OI-047 後續擴充。",
            self.tab_personnel,
            [self.tab_personnel],
        )
        self._add_page(
            "channel_overview",
            "Channel Overview",
            "Channel Settings Overview",
            "從 active/inactive channel card 角度彙整 user/project/device、recipe、environment、relay 與 R-line 狀態。",
            self.channel_overview_page,
        )
        self._add_page(
            "measurement_recipes",
            "量測 Recipe / Measurement Recipes",
            "量測 Recipe / Measurement Recipes",
            "管理 IV 掃描條件：電壓範圍、step、delay、interval、compliance、area。",
            self.tab_recipe,
            [self.tab_recipe],
        )
        self._add_page(
            "station_recipes",
            "Environment / Station Recipes",
            "Environment / Station Recipes",
            "合併原本 Station Recipe 與 Environment Recipe：管理光源、hotplate、chamber/vacuum setpoint 與 timeline。",
            self.tab_station_recipe,
            [self.tab_station_recipe],
        )
        self._add_page(
            "measurement_safety",
            "量測安全 / Measurement Safety",
            "量測安全 / Measurement Safety",
            "集中管理全域 V/I limit、relay/SMU settling、R-line 校正有效期與 scheduler policy。",
            self.tab_measurement,
            [self.tab_measurement],
        )

        self.hardware_tabs = QTabWidget()
        self.hardware_tabs.setStyleSheet(
            "QTabBar::tab { background: #3A3A3A; color: #F2F2F2; padding: 8px 16px; "
            "min-height: 30px; font-weight: 700; border: 1px solid #666666; }"
            "QTabBar::tab:selected { background: #0B73D9; color: white; border: 2px solid #9FD0FF; }"
            "QTabBar::tab:disabled { color: #A0A0A0; background: #2C2C2C; }"
            "QTabBar::tab:!selected { margin-top: 3px; }"
        )
        self.hardware_tabs.addTab(self.tab_smu, "SMU")
        self.hardware_tabs.addTab(self.tab_chamber, "Chamber")
        relay_hint = QLabel(
            "Relay COM 與 64-channel mapping 會在『Relay / Channel 對照』頁面管理，避免硬體連線與大型 mapping matrix 混在一起。"
            "\nRelay connection and mapping are managed in Relay / Channel Mapping."
        )
        relay_hint.setWordWrap(True)
        relay_hint.setAlignment(Qt.AlignmentFlag.AlignTop)
        relay_hint.setStyleSheet("color: #666666; padding: 16px;")
        self.hardware_tabs.addTab(relay_hint, "Relay note")
        self.hardware_tabs.currentChanged.connect(lambda _idx: self._sync_page_visibility())
        self._add_page(
            "hardware",
            "硬體連線 / Hardware Connection",
            "硬體連線 / Hardware Connection",
            "SMU 與 chamber 的低層連線、狀態測試與手動診斷。",
            self.hardware_tabs,
            [self.tab_smu, self.tab_chamber],
        )
        self._add_page(
            "relay_mapping",
            "Relay / Channel 對照",
            "Relay / Channel Mapping",
            "集中管理 relay pin mapping、active occupancy matrix 與 reset/safe-mode 診斷。",
            self.tab_relay,
            [self.tab_relay],
        )

        self._add_page(
            "environment",
            "環境 Instance / Environment Instances",
            "環境 Instance / Environment Instances",
            "管理 channel 與 environment instance 的基礎綁定；relay range 由 Relay / Channel Mapping 管理，recipe 由 Environment / Station Recipes 管理。",
            self.tab_env,
            [self.tab_env],
        )
        self._add_page(
            "rline_diagnostics",
            "R-line Diagnostics",
            "Calibration & R-line Diagnostics",
            "只檢查 active channel pairs，並用環境切分 3D R-line map 找出異常 relay 組合。",
            self.rline_diagnostics_tab,
        )
        self._add_page(
            "notifications",
            "通知與報告 / Notifications & Reports",
            "通知與報告 / Notifications & Reports",
            "Telegram、趨勢圖、報告與通知相關設定。Email report service 會在 OI-047 後續接入。",
            self.tab_notification,
            [self.tab_notification],
        )
        self.advanced_page = AdvancedSettingsPage(self)
        self._add_page(
            "advanced",
            "進階設定 / Advanced",
            "進階設定 / Advanced Settings",
            "低頻率、高風險與開發者用途設定預設收合。",
            self.advanced_page,
        )

    def _add_page(
        self,
        key: str,
        nav_title: str,
        page_title: str,
        description: str,
        content: QWidget,
        visibility_widgets: Optional[Iterable[QWidget]] = None,
    ) -> None:
        """Add a navigation entry and corresponding stacked page.

        Args:
            key: Stable page key used for quick navigation.
            nav_title: Text shown on the left navigation list.
            page_title: Title shown above the content area.
            description: Help text shown below the title.
            content: Main page widget.
            visibility_widgets: Child widgets with optional ``set_visibility``
                hooks that should be synchronized with active page state.
        """
        item = QListWidgetItem(nav_title)
        item.setData(Qt.ItemDataRole.UserRole, key)
        self.nav_list.addItem(item)
        self._page_keys.append(key)
        self._page_widgets[key] = list(visibility_widgets or [])

        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        title_label = QLabel(page_title)
        title_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666666;")
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addWidget(self._as_scroll_area(content), 1)
        self.stack.addWidget(wrapper)

    def _as_scroll_area(self, content: QWidget) -> QScrollArea:
        """Wrap content in a widget-resizable scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def load_data_to_tabs(self) -> None:
        """Pass relevant settings to each embedded tab."""
        self.tab_personnel.load_settings(self.original_personnel_settings)
        self.tab_smu.load_settings(self.original_main_settings)
        self.tab_relay.load_settings({**self.original_main_settings, **{"HARDWARE_MAP": self.original_hw_map}})
        self.tab_chamber.load_settings(self.original_main_settings)
        self.tab_measurement.load_settings(self.original_main_settings)
        self.tab_recipe.load_settings(self.original_recipe_settings)
        self.tab_station_recipe.load_settings(self.original_station_recipe_settings)
        self.tab_env.load_settings(self.original_user_settings)
        self.tab_notification.load_settings(self.original_notification_settings)
        self.channel_overview_page.refresh()
        self.rline_diagnostics_tab.refresh()
        self.dashboard_page.refresh()

    def select_page(self, key: str) -> None:
        """Select a page by stable key.

        Args:
            key: Page key registered by ``_add_page``.
        """
        if key not in self._page_keys:
            return
        self.nav_list.setCurrentRow(self._page_keys.index(key))

    def open_environment_recipe_tab(self, environment_type: str = "all") -> None:
        """Switch to the unified Environment / Station Recipe page.

        Args:
            environment_type: Legacy argument kept for signal compatibility.
        """
        _ = environment_type
        self.select_page("station_recipes")

    def save_all_settings(self) -> None:
        """Validate every page before writing; keep invalid settings editable."""
        try:
            new_personnel_settings = self.tab_personnel.get_settings()
            new_smu_settings = self.tab_smu.get_settings()
            new_relay_settings = self.tab_relay.get_settings()
            new_chamber_settings = self.tab_chamber.get_settings()
            new_measurement_settings = self.tab_measurement.get_settings()
            new_recipe_settings = self.tab_recipe.get_settings()
            new_station_recipe_settings = self.tab_station_recipe.get_settings()
            _ = self.tab_env.get_settings()
            new_notification_settings = self.tab_notification.get_settings()
        except Exception as exc:
            logging.getLogger(__name__).exception("System settings validation failed; no settings written")
            QMessageBox.warning(self, "設定未儲存", f"請修正以下設定後重試：\n{exc}")
            return

        new_main_settings = {
            "SMU_CONFIG": new_smu_settings,
            "RELAY_CONFIG": new_relay_settings.get("RELAY_CONFIG", {}),
            "CHAMBER_CONFIG": new_chamber_settings,
            **new_measurement_settings,
        }
        new_hw_map = new_relay_settings.get("HARDWARE_MAP", {})
        new_user_settings = self.original_user_settings

        try:
            config.save_personnel_settings(new_personnel_settings)
            config.save_config_settings(new_main_settings)
            config.save_user_settings(new_user_settings)
            config.save_hardware_map(new_hw_map)
            if new_relay_settings.get("ENVIRONMENT_PROFILES"):
                config.save_environment_profiles(new_relay_settings.get("ENVIRONMENT_PROFILES"))
            config.save_measurement_recipes(new_recipe_settings)
            config.save_station_recipes(new_station_recipe_settings)
            config.save_notification_settings(new_notification_settings)
            config.HARDWARE_MAP = new_hw_map
            self.channel_overview_page.refresh()
            self.rline_diagnostics_tab.refresh()
            self.dashboard_page.refresh()
            QMessageBox.information(self, "成功", "設定已儲存並即時生效。")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "錯誤", f"無法寫入設定檔:\n{exc}")
            self.reject()

    def _on_page_changed(self, index: int) -> None:
        """Handle primary navigation changes."""
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
        if 0 <= index < len(self._page_keys):
            active_key = self._page_keys[index]
            if active_key == "dashboard":
                self.dashboard_page.refresh()
            elif active_key == "channel_overview":
                self.channel_overview_page.refresh()
            elif active_key == "rline_diagnostics":
                self.rline_diagnostics_tab.refresh()
        self._sync_page_visibility()

    def _sync_page_visibility(self) -> None:
        """Call set_visibility hooks for the currently visible page only."""
        active_key = None
        current_item = self.nav_list.currentItem()
        if current_item is not None:
            active_key = current_item.data(Qt.ItemDataRole.UserRole)

        all_widgets = {widget for widgets in self._page_widgets.values() for widget in widgets}
        for widget in all_widgets:
            if hasattr(widget, "set_visibility"):
                widget.set_visibility(False)

        active_widgets = self._page_widgets.get(active_key, []) if active_key else []
        if active_key == "hardware":
            active_widgets = [self.hardware_tabs.currentWidget()]

        for widget in active_widgets:
            if hasattr(widget, "set_visibility"):
                widget.set_visibility(True)

    def closeEvent(self, event) -> None:
        """Ensure embedded tabs perform necessary cleanup.

        Args:
            event: Qt close event.
        """
        self.tab_relay.cleanup()
        self.tab_chamber.cleanup()
        self.tab_smu.cleanup()
        if hasattr(self.tab_notification, "cleanup"):
            self.tab_notification.cleanup()
        super().closeEvent(event)

    def reject(self) -> None:
        """Ensure cleanup is also called on rejection."""
        self.close()
        super().reject()
