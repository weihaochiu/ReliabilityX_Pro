import os
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QLabel, QSpinBox, QGroupBox, QFormLayout, QComboBox

class MeasurementTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Load the UI file
        ui_file = os.path.join(os.path.dirname(__file__), '..', 'ui', 'measurement_tab.ui')
        uic.loadUi(ui_file, self)
        self._add_calibration_group()
        self._add_scheduler_policy_group()

    def _add_calibration_group(self):
        """Add global calibration traceability settings not present in legacy .ui."""
        self.calibration_group = QGroupBox("校正追蹤與防呆")
        self.calibration_layout = QFormLayout(self.calibration_group)
        self.spin_rline_max_age = QSpinBox()
        self.spin_rline_max_age.setRange(1, 3650)
        self.spin_rline_max_age.setSingleStep(30)
        self.spin_rline_max_age.setSuffix(" 天")
        self.spin_rline_max_age.setToolTip(
            "R-line 線路阻抗校正超過此天數時，Channel 設定頁會以紅色提醒並在存檔前要求確認。"
        )
        self.calibration_layout.addRow(QLabel("R-line 校正提醒天數:"), self.spin_rline_max_age)
        self.verticalLayout.insertWidget(2, self.calibration_group)


    def _add_scheduler_policy_group(self):
        """Add scheduler catch-up / strict-skip settings not present in legacy .ui."""
        self.scheduler_group = QGroupBox("排程延遲策略")
        self.scheduler_layout = QFormLayout(self.scheduler_group)

        self.combo_scheduler_mode = QComboBox()
        self.combo_scheduler_mode.addItem("Flexible catch-up：延遲仍量測並記錄", "flexible_catch_up")
        self.combo_scheduler_mode.addItem("Strict skip：超過容忍延遲則跳過該輪", "strict_skip")
        self.combo_scheduler_mode.setToolTip(
            "Flexible catch-up 會保存完整資料但可能持續落後；Strict skip 會在 delay 超過門檻時略過該輪，維持固定 cadence。"
        )

        self.spin_scheduler_max_delay = QSpinBox()
        self.spin_scheduler_max_delay.setRange(0, 604800)
        self.spin_scheduler_max_delay.setSingleStep(60)
        self.spin_scheduler_max_delay.setSuffix(" 秒")
        self.spin_scheduler_max_delay.setToolTip("Strict skip 模式下，量測延遲超過此秒數就跳過該 channel 的本輪 scheduled occurrence。")

        self.scheduler_layout.addRow(QLabel("排程模式:"), self.combo_scheduler_mode)
        self.scheduler_layout.addRow(QLabel("最大允許延遲:"), self.spin_scheduler_max_delay)
        self.verticalLayout.insertWidget(3, self.scheduler_group)

    def load_settings(self, settings):
        """Load measurement and safety settings."""
        self.spin_relay_delay.setValue(settings.get("RELAY_SETTLING_MS", 50))
        self.spin_smu_settle.setValue(settings.get("SMU_SETTLING_MS", 20))
        
        safety_conf = settings.get("GLOBAL_SAFETY", {})
        self.spin_v_max.setValue(safety_conf.get("V_MAX", 20.0))
        self.spin_i_max.setValue(safety_conf.get("I_MAX", 0.5))

        calibration_conf = settings.get("CALIBRATION_SETTINGS", {}) if isinstance(settings, dict) else {}
        scheduler_conf = settings.get("SCHEDULER_POLICY", {}) if isinstance(settings, dict) else {}
        self._trend_chart_settings = dict(settings.get("TREND_CHART", {})) if isinstance(settings, dict) else {}
        if not self._trend_chart_settings:
            self._trend_chart_settings = {"MAX_IN_MEMORY_POINTS": 50000, "RENDER_THROTTLE_MS": 1000}
        self.spin_rline_max_age.setValue(
            int(calibration_conf.get("RLINE_MAX_AGE_DAYS", settings.get("RLINE_CALIBRATION_MAX_AGE_DAYS", 30)))
        )
        mode = str(scheduler_conf.get("MODE", "flexible_catch_up"))
        idx = self.combo_scheduler_mode.findData(mode)
        self.combo_scheduler_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.spin_scheduler_max_delay.setValue(int(scheduler_conf.get("MAX_ALLOWED_DELAY_SEC", 300)))

    def get_settings(self):
        """Return measurement and safety settings."""
        return {
            "RELAY_SETTLING_MS": self.spin_relay_delay.value(),
            "SMU_SETTLING_MS": self.spin_smu_settle.value(),
            "GLOBAL_SAFETY": {
                "V_MAX": self.spin_v_max.value(),
                "I_MAX": self.spin_i_max.value(),
            },
            "CALIBRATION_SETTINGS": {
                "RLINE_MAX_AGE_DAYS": self.spin_rline_max_age.value(),
            },
            "TREND_CHART": dict(getattr(self, "_trend_chart_settings", {"MAX_IN_MEMORY_POINTS": 50000, "RENDER_THROTTLE_MS": 1000})),
            "SCHEDULER_POLICY": {
                "MODE": self.combo_scheduler_mode.currentData() or "flexible_catch_up",
                "MAX_ALLOWED_DELAY_SEC": self.spin_scheduler_max_delay.value(),
            },
        }
