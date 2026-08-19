"""gui/config_tabs/environment_tab/climate_chamber_tab.py

Stage 2.6.4 bugfix update:
- Persist relay assignment and default recipe through EnvironmentManager.
- Expose shortcut signal to the shared Environment Recipe editor.
"""

from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)

from .climate_chamber_widgets.chamber_connection_widget import ChamberConnectionWidget
from .climate_chamber_widgets.chamber_status_widget import ChamberStatusWidget
from .climate_chamber_widgets.chamber_control_widget import ChamberControlWidget
from .climate_chamber_widgets.chamber_debug_widget import ChamberDebugWidget
from .environment_common_widgets.relay_assignment_widget import RelayAssignmentWidget
from .environment_common_widgets.environment_recipe_widget import EnvironmentRecipeWidget


class ClimateChamberTab(QWidget):
    """Climate chamber tab with scrollable layout and decomposed widgets."""

    environment_type = "climate"
    open_environment_recipe_requested = pyqtSignal(str)

    def __init__(self, environment_manager, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.environment_manager = environment_manager
        self.engine = engine

        self.lbl_instance = QLabel("-")
        self.relay_widget = RelayAssignmentWidget()
        self.recipe_widget = EnvironmentRecipeWidget()
        self.connection_widget = ChamberConnectionWidget()
        self.status_widget = ChamberStatusWidget()
        self.control_widget = ChamberControlWidget()
        self.debug_widget = ChamberDebugWidget()

        self.chamber_update_timer = QTimer(self)
        self.chamber_update_timer.setInterval(2000)
        self.chamber_update_timer.timeout.connect(self._update_chamber_status)
        self._manual_input_pause_timer = QTimer(self)
        self._manual_input_pause_timer.setSingleShot(True)
        self._manual_input_pause_timer.setInterval(1200)
        self._manual_input_pause_timer.timeout.connect(self._resume_polling_after_manual_input)
        self._polling_visible = False
        self._poll_in_progress = False

        self._build_ui()
        self._connect_signals()
        self.load_from_manager()

    def _build_ui(self) -> None:
        """Build the climate tab UI inside a scroll area."""
        root = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        gb_instance = QGroupBox("Environment Instance")
        form_instance = QFormLayout(gb_instance)
        form_instance.addRow("Instance ID", self.lbl_instance)
        content_layout.addWidget(gb_instance)

        content_layout.addWidget(self.relay_widget)
        content_layout.addWidget(self.recipe_widget)

        top_row = QHBoxLayout()
        top_row.addWidget(self.connection_widget, 1)
        top_row.addWidget(self.status_widget, 1)
        content_layout.addLayout(top_row)

        content_layout.addWidget(self.control_widget)
        content_layout.addWidget(self.debug_widget)
        content_layout.addStretch()

        scroll.setWidget(content)

    def _connect_signals(self) -> None:
        """Connect child-widget signals to controller handlers."""
        self.connection_widget.scan_ports_requested.connect(self._scan_chamber_ports)
        self.connection_widget.test_connection_requested.connect(self._test_chamber_connection)
        self.control_widget.send_setpoints_requested.connect(self._send_chamber_setpoints)
        self.control_widget.manual_input_changed.connect(self._pause_polling_for_manual_input)
        self.debug_widget.manual_command_requested.connect(self._send_manual_command)
        self.recipe_widget.recipe_changed.connect(self._on_recipe_changed)

    def get_default_instance_id(self) -> str:
        """Return the first climate instance id."""
        ids = self.environment_manager.list_instances(self.environment_type)
        return ids[0] if ids else ""

    def load_from_manager(self) -> None:
        """Load climate instance relay and recipe settings from manager."""
        self.environment_manager.reload_all()
        instance_id = self.get_default_instance_id()
        self.lbl_instance.setText(instance_id or "-")

        item = self.environment_manager.get_instance(instance_id) if instance_id else None
        if item is not None:
            self.relay_widget.set_ranges(
                plus_start=item.smu_plus_start,
                plus_end=item.smu_plus_end,
                minus_start=item.smu_minus_start,
                minus_end=item.smu_minus_end,
            )

        self.recipe_widget.set_recipe_options(
            self.environment_manager.get_environment_recipe_ids(self.environment_type)
        )
        if item is not None and item.default_env_recipe:
            self.recipe_widget.set_current_recipe(item.default_env_recipe)
        self._on_recipe_changed(self.recipe_widget.get_current_recipe())

    def save_current_instance(self) -> None:
        """Persist climate instance relay assignment and recipe settings."""
        instance_id = self.get_default_instance_id()
        item = self.environment_manager.get_instance(instance_id)
        if item is None:
            return

        payload = {
            "type": item.env_type,
            "title": item.title,
            "smu_plus_start": self.relay_widget.get_plus_start(),
            "smu_plus_end": self.relay_widget.get_plus_end(),
            "smu_minus_start": self.relay_widget.get_minus_start(),
            "smu_minus_end": self.relay_widget.get_minus_end(),
            "default_env_recipe": self.recipe_widget.get_current_recipe().strip(),
        }
        self.environment_manager.update_instance(instance_id, payload)

    def load_settings(self, settings=None) -> None:
        """Compatibility entry for SystemConfigDialog."""
        self.load_from_manager()
        settings = settings or {}
        chamber_conf = settings.get("CHAMBER_CONFIG", {})
        self._scan_chamber_ports()
        self.connection_widget.set_connection_values(
            port=chamber_conf.get("PORT", ""),
            station_id=chamber_conf.get("ID", 1),
            baudrate=chamber_conf.get("BAUDRATE", 9600),
        )

    def set_visibility(self, visible: bool) -> None:
        """Start polling only while visible, connected, and not editing inputs."""
        self._polling_visible = bool(visible)
        if self._polling_visible and self.engine and getattr(self.engine, "chamber_driver", None):
            driver = self.engine.chamber_driver
            if driver and driver.is_connected() and not self._manual_input_pause_timer.isActive():
                self.chamber_update_timer.start()
                return
        self.chamber_update_timer.stop()

    def cleanup(self) -> None:
        """Stop timer during dialog close."""
        self.chamber_update_timer.stop()
        self._manual_input_pause_timer.stop()

    def _pause_polling_for_manual_input(self) -> None:
        """Pause synchronous chamber polling while the operator edits setpoints."""
        self.chamber_update_timer.stop()
        self._manual_input_pause_timer.start()

    def _resume_polling_after_manual_input(self) -> None:
        """Resume chamber polling after manual input changes settle."""
        if self._polling_visible and self.engine and getattr(self.engine, "chamber_driver", None):
            driver = self.engine.chamber_driver
            if driver and driver.is_connected():
                self.chamber_update_timer.start()

    def _on_recipe_changed(self, recipe_id: str) -> None:
        """Refresh recipe description text."""
        self.recipe_widget.set_description(
            self.environment_manager.get_recipe_description(recipe_id) or "-"
        )

    def _scan_chamber_ports(self) -> None:
        """Refresh available serial ports."""
        self.connection_widget.scan_ports()

    def _test_chamber_connection(self) -> None:
        """Test chamber serial connection and require readable telemetry."""
        if not self.engine or not getattr(self.engine, "chamber_driver", None):
            self.connection_widget.show_connection_result(
                ok=False,
                message="engine.chamber_driver 不存在。",
            )
            return

        ok, message = self.connection_widget.test_connection_with_driver(
            driver=self.engine.chamber_driver
        )
        self.connection_widget.show_connection_result(ok=ok, message=message)

        if ok:
            self._update_chamber_status()
            self.chamber_update_timer.start()
        else:
            self.status_widget.show_error()
            self.chamber_update_timer.stop()

    def _update_chamber_status(self) -> None:
        """Update chamber status widget from the driver without reentrant polling."""
        if self._poll_in_progress or self._manual_input_pause_timer.isActive():
            return
        if not self.engine or not getattr(self.engine, "chamber_driver", None):
            return
        driver = self.engine.chamber_driver
        if not driver or not driver.is_connected():
            return

        self._poll_in_progress = True
        try:
            status = driver.read_status()
            if not status:
                self.status_widget.show_error()
                return

            self.status_widget.update_status(
                temp_pv=status.get("temp_pv"),
                temp_sv=status.get("temp_sv"),
                hum_pv=status.get("hum_pv"),
                hum_sv=status.get("hum_sv"),
            )
        finally:
            self._poll_in_progress = False
        # Do not copy readback SV into manual command spin boxes here.
        # The spin boxes are user-owned target inputs and must remain stable
        # while telemetry polling updates PV/SV labels.

    def _send_chamber_setpoints(self) -> None:
        """Write chamber setpoints."""
        if not self.engine or not getattr(self.engine, "chamber_driver", None):
            self.control_widget.show_send_result(ok=False, message="溫濕度箱未連接！")
            return

        driver = self.engine.chamber_driver
        if not driver or not driver.is_connected():
            self.control_widget.show_send_result(ok=False, message="溫濕度箱未連接！")
            return

        current_status = driver.read_status()
        old_t, old_h = ("N/A", "N/A")
        if current_status:
            old_t = current_status.get("temp_sv", "N/A")
            old_h = current_status.get("hum_sv", "N/A")

        new_t, new_h = self.control_widget.get_setpoints()
        ok = driver.write_setpoints(new_t, new_h)
        if ok:
            if getattr(self.engine, "log_mgr", None):
                self.engine.log_mgr.log_config_change(
                    "[ENV] Chamber SV",
                    f"{old_t}/{old_h}",
                    f"{new_t}/{new_h}",
                    "使用者手動設定",
                )
            self.control_widget.show_send_result(ok=True, message="設定值已傳送。")
            QTimer.singleShot(500, self._update_chamber_status)
        else:
            self.control_widget.show_send_result(ok=False, message="傳送設定值失敗！")

    def _send_manual_command(self) -> None:
        """Send manual command and display full TX/RX diagnostics."""
        if not self.engine or not getattr(self.engine, "chamber_driver", None):
            self.debug_widget.append_log("[錯誤] engine.chamber_driver 不存在。")
            return

        driver = self.engine.chamber_driver
        if not driver or not driver.is_connected():
            self.debug_widget.append_log("[錯誤] 溫濕度箱 serial port 尚未開啟。請先測試連線。")
            return

        cmd_id = self.debug_widget.get_command_id()
        if not cmd_id:
            self.debug_widget.append_log("[錯誤] Signal ID 不可為空。")
            return

        if hasattr(driver, "send_manual_command_detailed"):
            self.debug_widget.append_log(driver.send_manual_command_detailed(cmd_id))
        else:
            raw_response = driver.send_manual_command(cmd_id)
            self.debug_widget.append_log(f"[回傳] {raw_response}")
