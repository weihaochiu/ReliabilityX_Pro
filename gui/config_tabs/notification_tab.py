import threading
from typing import Callable, Dict, List, Optional, Union

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSpinBox,
)

import config
from core.notification_manager import send_telegram_message
from core.trend_spec import (
    get_trend_direction_options,
    get_trend_metric_options,
    get_trend_path_options,
    get_trend_x_axis_options,
    normalize_metric_labels,
)


class GuardedComboBox(QComboBox):
    """在不符合條件時，攔截下拉操作並彈出提示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._guard_check: Optional[Callable[[], bool]] = None
        self._guard_title = "提示"
        self._guard_message: Union[str, Callable[[], str]] = ""

    def set_guard(self, guard_check: Callable[[], bool], title: str, message: Union[str, Callable[[], str]]):
        """Configure guard callback and prompt text."""
        self._guard_check = guard_check
        self._guard_title = title
        self._guard_message = message

    def _allow_interaction(self) -> bool:
        if self._guard_check is None:
            return True
        try:
            allowed = bool(self._guard_check())
        except Exception:
            allowed = False

        if allowed:
            return True

        message = self._guard_message() if callable(self._guard_message) else self._guard_message
        QMessageBox.information(self.window() or self, self._guard_title, message)
        return False

    def showPopup(self):
        if self._allow_interaction():
            super().showPopup()

    def wheelEvent(self, event: QWheelEvent):
        if self._allow_interaction():
            super().wheelEvent(event)
        else:
            event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        guarded_keys = {
            Qt.Key.Key_Space,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Down,
            Qt.Key.Key_Up,
            Qt.Key.Key_PageDown,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
            Qt.Key.Key_F4,
        }
        if event.key() in guarded_keys and not self._allow_interaction():
            event.accept()
            return
        super().keyPressEvent(event)


class MaskedLineEdit(QLineEdit):
    """
    可切換完整顯示 / 部分遮罩顯示的輸入框。
    平常顯示遮罩文字，但焦點進入時會自動切回完整值供編輯。
    """

    def __init__(self, parent=None, mask_char: str = "*", keep_tail: int = 4):
        super().__init__(parent)
        self._real_text = ""
        self._mask_enabled = True
        self._mask_char = mask_char
        self._keep_tail = max(0, int(keep_tail))
        self._syncing = False
        self.textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, text: str):
        if self._syncing:
            return
        self._real_text = text

    def _masked_text(self) -> str:
        text = self._real_text or ""
        if not text:
            return ""
        if not self._mask_enabled:
            return text
        if len(text) <= self._keep_tail:
            return self._mask_char * len(text)
        return f"{self._mask_char * (len(text) - self._keep_tail)}{text[-self._keep_tail:]}"

    def set_mask_enabled(self, enabled: bool):
        enabled = bool(enabled)
        if self._mask_enabled == enabled:
            return
        self._mask_enabled = enabled
        self._refresh_display()

    def is_mask_enabled(self) -> bool:
        return self._mask_enabled

    def set_real_text(self, text: str):
        self._real_text = "" if text is None else str(text)
        self._refresh_display()

    def _refresh_display(self):
        self._syncing = True
        try:
            super().setText(self._masked_text())
            self.setCursorPosition(len(self.text()))
        finally:
            self._syncing = False

    def focusInEvent(self, event):
        if self._mask_enabled:
            self._syncing = True
            try:
                super().setText(self._real_text)
                self.setCursorPosition(len(self._real_text))
            finally:
                self._syncing = False
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._real_text = super().text()
        if self._mask_enabled:
            self._refresh_display()
        super().focusOutEvent(event)

    def value(self) -> str:
        return self._real_text if self._mask_enabled else self.text()


class NotificationTab(QWidget):
    """Notification settings tab for Telegram summary and trend delivery."""

    test_result_signal = pyqtSignal(bool, str)

    TREND_GROUP_MODE_ITEMS = [
        ("整體", "overall"),
        ("依使用者+專案", "user_project"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._time_combos: List[GuardedComboBox] = []
        self._metric_checks: Dict[str, QCheckBox] = {}
        self._building_time_rows = False
        self.test_result_signal.connect(self._handle_test_result)
        self.init_ui()
        self._connect_preview_signals()
        self._apply_enabled_state()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        root_layout.addWidget(self.scroll_area)

        self.content_widget = QWidget()
        self.scroll_area.setWidget(self.content_widget)

        main_layout = QVBoxLayout(self.content_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        telegram_group = QGroupBox("Telegram 通知")
        telegram_form = QFormLayout(telegram_group)
        telegram_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.chk_tg_enabled = QCheckBox("啟用 Telegram 通知")
        telegram_form.addRow(self.chk_tg_enabled)

        self.lbl_enable_hint = QLabel("目前尚未啟用 Telegram 通知；排程、趨勢圖與測試功能不會生效。")
        self.lbl_enable_hint.setWordWrap(True)
        telegram_form.addRow(self.lbl_enable_hint)

        token_row = QHBoxLayout()
        token_row.setContentsMargins(0, 0, 0, 0)
        token_row.setSpacing(8)
        self.edit_bot_token = QLineEdit()
        self.edit_bot_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_bot_token.setPlaceholderText("輸入 Telegram Bot Token")
        self.btn_toggle_token = QToolButton()
        self.btn_toggle_token.setText("顯示")
        self.btn_toggle_token.clicked.connect(self._toggle_token_visibility)
        token_row.addWidget(self.edit_bot_token, 1)
        token_row.addWidget(self.btn_toggle_token)
        telegram_form.addRow("Bot Token:", token_row)

        chat_row = QHBoxLayout()
        chat_row.setContentsMargins(0, 0, 0, 0)
        chat_row.setSpacing(8)
        self.edit_chat_id = MaskedLineEdit(keep_tail=4)
        self.edit_chat_id.setPlaceholderText("輸入 Telegram Chat ID")
        self.btn_toggle_chat_id = QToolButton()
        self.btn_toggle_chat_id.setText("顯示")
        self.btn_toggle_chat_id.clicked.connect(self._toggle_chat_id_visibility)
        chat_row.addWidget(self.edit_chat_id, 1)
        chat_row.addWidget(self.btn_toggle_chat_id)
        telegram_form.addRow("Chat ID:", chat_row)

        self.edit_bot_token_file = QLineEdit()
        self.edit_bot_token_file.setPlaceholderText(r"例如 C:\\ReliabilityX_Secrets\\telegram_bot_token.txt（建議每行只放一個 token）")
        telegram_form.addRow("Bot Token TXT 路徑:", self.edit_bot_token_file)

        self.edit_chat_id_file = QLineEdit()
        self.edit_chat_id_file.setPlaceholderText(r"例如 C:\\ReliabilityX_Secrets\\telegram_chat_id.txt（建議每行只放一個 chat id）")
        telegram_form.addRow("Chat ID TXT 路徑:", self.edit_chat_id_file)

        self.lbl_secret_file_hint = QLabel(
            "建議正式使用時只保存 TXT 路徑，不把真實 Bot Token / Chat ID 寫入 notification_settings.json；"
            "若同時填寫直接欄位與 TXT 路徑，發送時會優先讀取 TXT 檔案。"
        )
        self.lbl_secret_file_hint.setWordWrap(True)
        telegram_form.addRow(self.lbl_secret_file_hint)

        event_group = QGroupBox("通知事件")
        event_layout = QVBoxLayout(event_group)
        event_layout.setContentsMargins(12, 12, 12, 12)
        event_layout.setSpacing(8)
        self.chk_notify_error = QCheckBox("重大錯誤時發送通知")
        self.chk_notify_start = QCheckBox("開始量測時發送通知")
        self.chk_notify_summary = QCheckBox("每日 IV 摘要通知")
        event_layout.addWidget(self.chk_notify_error)
        event_layout.addWidget(self.chk_notify_start)
        event_layout.addWidget(self.chk_notify_summary)

        schedule_group = QGroupBox("每日摘要排程")
        schedule_layout = QVBoxLayout(schedule_group)
        schedule_layout.setContentsMargins(12, 12, 12, 12)
        schedule_layout.setSpacing(8)

        count_row = QHBoxLayout()
        count_row.setContentsMargins(0, 0, 0, 0)
        count_row.setSpacing(8)
        count_row.addWidget(QLabel("每日回報次數:"))
        self.combo_report_count = GuardedComboBox()
        self.combo_report_count.addItems([str(i) for i in range(0, 7)])
        self.combo_report_count.currentIndexChanged.connect(self._rebuild_time_rows)
        self.combo_report_count.set_guard(self._can_edit_schedule, "尚未啟用 Telegram 通知", self._build_schedule_guard_message)
        count_row.addWidget(self.combo_report_count)
        count_row.addStretch()
        schedule_layout.addLayout(count_row)

        self.report_times_container = QWidget()
        self.report_times_layout = QFormLayout(self.report_times_container)
        self.report_times_layout.setContentsMargins(0, 0, 0, 0)
        self.report_times_layout.setHorizontalSpacing(12)
        self.report_times_layout.setVerticalSpacing(8)
        schedule_layout.addWidget(self.report_times_container)

        schedule_hint = QLabel("時間選項限制為整點，系統會自動去除重複時間並排序儲存。")
        schedule_hint.setWordWrap(True)
        schedule_layout.addWidget(schedule_hint)

        trend_group = QGroupBox("定時趨勢圖")
        trend_layout = QVBoxLayout(trend_group)
        trend_layout.setContentsMargins(12, 12, 12, 12)
        trend_layout.setSpacing(8)

        self.chk_trend_images_enabled = QCheckBox("每日摘要同時附上趨勢報告")
        trend_layout.addWidget(self.chk_trend_images_enabled)

        metric_group = QGroupBox("要推播的圖表")
        metric_layout = QVBoxLayout(metric_group)
        metric_layout.setContentsMargins(8, 8, 8, 8)
        metric_layout.setSpacing(6)

        metric_scroll = QScrollArea()
        metric_scroll.setWidgetResizable(True)
        metric_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        metric_scroll.setMinimumHeight(150)
        metric_scroll.setMaximumHeight(210)

        metric_container = QWidget()
        metric_container_layout = QVBoxLayout(metric_container)
        metric_container_layout.setContentsMargins(4, 4, 4, 4)
        metric_container_layout.setSpacing(4)
        for metric in get_trend_metric_options():
            chk = QCheckBox(metric)
            self._metric_checks[metric] = chk
            metric_container_layout.addWidget(chk)
        metric_container_layout.addStretch()
        metric_scroll.setWidget(metric_container)
        metric_layout.addWidget(metric_scroll)
        trend_layout.addWidget(metric_group)

        trend_form = QFormLayout()
        trend_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.combo_trend_direction = GuardedComboBox()
        self.combo_trend_direction.addItems(get_trend_direction_options())
        self.combo_trend_direction.set_guard(self._can_edit_trend_options, "尚未啟用 Telegram 通知", self._build_trend_guard_message)

        self.combo_trend_path = GuardedComboBox()
        self.combo_trend_path.addItems(get_trend_path_options())
        self.combo_trend_path.set_guard(self._can_edit_trend_options, "尚未啟用 Telegram 通知", self._build_trend_guard_message)

        self.combo_trend_x_axis = GuardedComboBox()
        self.combo_trend_x_axis.addItems(get_trend_x_axis_options())
        self.combo_trend_x_axis.set_guard(self._can_edit_trend_options, "尚未啟用 Telegram 通知", self._build_trend_guard_message)

        self.combo_trend_group_mode = GuardedComboBox()
        for text, value in self.TREND_GROUP_MODE_ITEMS:
            self.combo_trend_group_mode.addItem(text, value)
        self.combo_trend_group_mode.set_guard(self._can_edit_trend_options, "尚未啟用 Telegram 通知", self._build_trend_guard_message)

        trend_form.addRow("掃描方向:", self.combo_trend_direction)
        trend_form.addRow("數據路徑:", self.combo_trend_path)
        trend_form.addRow("X 軸模式:", self.combo_trend_x_axis)
        trend_form.addRow("寄送分組:", self.combo_trend_group_mode)
        trend_layout.addLayout(trend_form)

        self.chk_trend_normalize = QCheckBox("標準化至初始值 (%)")
        self.chk_trend_smoothing = QCheckBox("數據平滑 (Moving Avg)")
        self.chk_trend_pdf_enabled = QCheckBox("以 PDF 報告推送（每頁一張圖）")
        trend_layout.addWidget(self.chk_trend_normalize)
        trend_layout.addWidget(self.chk_trend_smoothing)
        trend_layout.addWidget(self.chk_trend_pdf_enabled)

        self.lbl_env_rule = QLabel("環境子圖規則：PDF 模式下，若該群組有 Temp/Hum 資料，則每一頁主圖下方都會自動附加環境子圖；若無環境資料則不顯示。")
        self.lbl_env_rule.setWordWrap(True)
        trend_layout.addWidget(self.lbl_env_rule)

        trend_hint = QLabel("整體模式會送出目前所有量測中電池的一份整體 PDF；依使用者+專案模式則只針對目前正在執行中的 active scope 分組送出文字與 PDF。")
        trend_hint.setWordWrap(True)
        trend_layout.addWidget(trend_hint)

        advanced_group = QGroupBox("進階設定")
        advanced_form = QFormLayout(advanced_group)
        advanced_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.spin_cooldown = QSpinBox()
        self.spin_cooldown.setRange(0, 24 * 60 * 60)
        self.spin_cooldown.setSuffix(" 秒")
        self.spin_max_len = QSpinBox()
        self.spin_max_len.setRange(100, 4096)
        self.spin_max_len.setValue(3500)
        advanced_form.addRow("錯誤通知冷卻時間:", self.spin_cooldown)
        advanced_form.addRow("訊息最大長度:", self.spin_max_len)

        test_group = QGroupBox("測試")
        test_layout = QVBoxLayout(test_group)
        test_layout.setContentsMargins(12, 12, 12, 12)
        test_layout.setSpacing(8)
        test_btn_row = QHBoxLayout()
        test_btn_row.setContentsMargins(0, 0, 0, 0)
        test_btn_row.setSpacing(8)
        self.btn_test_message = QPushButton("發送 Telegram 測試訊息")
        self.btn_test_message.clicked.connect(self._on_test_message_clicked)
        test_btn_row.addWidget(self.btn_test_message)
        test_btn_row.addStretch()
        test_layout.addLayout(test_btn_row)
        self.test_status_label = QLabel("尚未測試。")
        self.test_status_label.setWordWrap(True)
        test_layout.addWidget(self.test_status_label)
        self.test_preview = QTextEdit()
        self.test_preview.setReadOnly(True)
        self.test_preview.setFixedHeight(140)
        self.test_preview.setPlaceholderText("這裡會顯示測試訊息預覽。")
        test_layout.addWidget(self.test_preview)

        main_layout.addWidget(telegram_group)
        main_layout.addWidget(event_group)
        main_layout.addWidget(schedule_group)
        main_layout.addWidget(trend_group)
        main_layout.addWidget(advanced_group)
        main_layout.addWidget(test_group)
        main_layout.addStretch()

        self._rebuild_time_rows()
        self._refresh_preview()

    def _connect_preview_signals(self):
        self.chk_tg_enabled.toggled.connect(self._apply_enabled_state)
        self.chk_tg_enabled.toggled.connect(self._refresh_preview)
        self.edit_bot_token.textChanged.connect(self._refresh_preview)
        self.edit_chat_id.textChanged.connect(self._refresh_preview)
        self.edit_bot_token_file.textChanged.connect(self._refresh_preview)
        self.edit_chat_id_file.textChanged.connect(self._refresh_preview)
        self.chk_notify_error.toggled.connect(self._refresh_preview)
        self.chk_notify_start.toggled.connect(self._refresh_preview)
        self.chk_notify_summary.toggled.connect(self._apply_enabled_state)
        self.chk_notify_summary.toggled.connect(self._refresh_preview)
        self.chk_trend_images_enabled.toggled.connect(self._refresh_preview)
        self.combo_trend_direction.currentTextChanged.connect(self._refresh_preview)
        self.combo_trend_path.currentTextChanged.connect(self._refresh_preview)
        self.combo_trend_x_axis.currentTextChanged.connect(self._refresh_preview)
        self.combo_trend_group_mode.currentIndexChanged.connect(self._refresh_preview)
        self.chk_trend_normalize.toggled.connect(self._refresh_preview)
        self.chk_trend_smoothing.toggled.connect(self._refresh_preview)
        self.chk_trend_pdf_enabled.toggled.connect(self._refresh_preview)
        self.spin_cooldown.valueChanged.connect(self._refresh_preview)
        self.spin_max_len.valueChanged.connect(self._refresh_preview)
        for chk in self._metric_checks.values():
            chk.toggled.connect(self._refresh_preview)

    def _apply_enabled_state(self):
        self.lbl_enable_hint.setVisible(not self.chk_tg_enabled.isChecked())

    def _can_edit_schedule(self) -> bool:
        return self.chk_tg_enabled.isChecked() and self.chk_notify_summary.isChecked()

    def _can_edit_trend_options(self) -> bool:
        return self.chk_tg_enabled.isChecked() and self.chk_notify_summary.isChecked() and self.chk_trend_images_enabled.isChecked()

    def _toggle_token_visibility(self):
        if self.edit_bot_token.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_bot_token.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_token.setText("隱藏")
        else:
            self.edit_bot_token.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_token.setText("顯示")

    def _toggle_chat_id_visibility(self):
        if self.edit_chat_id.is_mask_enabled():
            self.edit_chat_id.set_mask_enabled(False)
            self.btn_toggle_chat_id.setText("隱藏")
        else:
            self.edit_chat_id.set_mask_enabled(True)
            self.btn_toggle_chat_id.setText("顯示")

    def _hour_options(self) -> List[str]:
        return [f"{hour:02d}:00" for hour in range(24)]

    def _build_schedule_guard_message(self) -> str:
        if not self.chk_tg_enabled.isChecked() and not self.chk_notify_summary.isChecked():
            return "尚未啟用 Telegram 通知，且「每日 IV 摘要通知」尚未勾選；請先完成啟用後再設定每日回報排程。"
        if not self.chk_tg_enabled.isChecked():
            return "尚未啟用 Telegram 通知，請先勾選「啟用 Telegram 通知」後再設定每日回報排程。"
        if not self.chk_notify_summary.isChecked():
            return "尚未啟用「每日 IV 摘要通知」，請先勾選後再設定每日回報排程。"
        return ""

    def _build_trend_guard_message(self) -> str:
        if not self.chk_tg_enabled.isChecked():
            return "尚未啟用 Telegram 通知，請先勾選「啟用 Telegram 通知」後再設定趨勢圖推播。"
        if not self.chk_notify_summary.isChecked():
            return "尚未啟用「每日 IV 摘要通知」，請先勾選後再設定趨勢圖推播。"
        if not self.chk_trend_images_enabled.isChecked():
            return "尚未勾選「每日摘要同時附上趨勢圖」，請先啟用後再設定趨勢圖選項。"
        return ""

    def _rebuild_time_rows(self):
        if self._building_time_rows:
            return

        self._building_time_rows = True
        try:
            old_values = [combo.currentText() for combo in self._time_combos]
            while self.report_times_layout.rowCount() > 0:
                self.report_times_layout.removeRow(0)
            self._time_combos.clear()

            count = int(self.combo_report_count.currentText())
            hour_options = self._hour_options()
            for index in range(count):
                combo = GuardedComboBox()
                combo.addItems(hour_options)
                combo.set_guard(self._can_edit_schedule, "尚未啟用 Telegram 通知", self._build_schedule_guard_message)
                if index < len(old_values) and old_values[index] in hour_options:
                    combo.setCurrentText(old_values[index])
                else:
                    default_hour = (9 + index * 3) % 24
                    combo.setCurrentText(f"{default_hour:02d}:00")
                combo.currentTextChanged.connect(self._refresh_preview)
                self._time_combos.append(combo)
                self.report_times_layout.addRow(f"回報時間 {index + 1}:", combo)
        finally:
            self._building_time_rows = False

        self._apply_enabled_state()
        self._refresh_preview()

    def load_settings(self, settings: Dict):
        settings = settings or {}
        telegram_cfg = dict(settings.get("TELEGRAM", {}))

        self.chk_tg_enabled.setChecked(bool(telegram_cfg.get("enabled", False)))
        self.edit_bot_token.setText(str(telegram_cfg.get("bot_token", "") or ""))
        self.edit_chat_id.set_real_text(str(telegram_cfg.get("chat_id", "") or ""))
        self.edit_bot_token_file.setText(str(telegram_cfg.get("bot_token_file", "") or ""))
        self.edit_chat_id_file.setText(str(telegram_cfg.get("chat_id_file", "") or ""))
        self.chk_notify_error.setChecked(bool(telegram_cfg.get("notify_on_critical_error", True)))
        self.chk_notify_start.setChecked(bool(telegram_cfg.get("notify_on_measurement_start", True)))
        self.chk_notify_summary.setChecked(bool(telegram_cfg.get("notify_on_daily_summary", True)))
        self.spin_cooldown.setValue(int(telegram_cfg.get("cooldown_seconds", 300) or 300))
        self.spin_max_len.setValue(int(telegram_cfg.get("max_message_length", 3500) or 3500))

        hours = []
        for value in telegram_cfg.get("daily_report_hours", []):
            try:
                hour = int(value)
            except Exception:
                continue
            if 0 <= hour <= 23 and hour not in hours:
                hours.append(hour)
        hours.sort()
        self.combo_report_count.setCurrentText(str(len(hours)))
        self._rebuild_time_rows()
        for combo, hour in zip(self._time_combos, hours):
            combo.setCurrentText(f"{hour:02d}:00")

        self.chk_trend_images_enabled.setChecked(bool(telegram_cfg.get("trend_images_enabled", False)))
        selected_metrics = normalize_metric_labels(telegram_cfg.get("trend_metrics", []))
        for metric, chk in self._metric_checks.items():
            chk.setChecked(metric in selected_metrics)
        self.combo_trend_direction.setCurrentText(str(telegram_cfg.get("trend_direction", get_trend_direction_options()[0])))
        self.combo_trend_path.setCurrentText(str(telegram_cfg.get("trend_path", get_trend_path_options()[0])))
        self.combo_trend_x_axis.setCurrentText(str(telegram_cfg.get("trend_x_axis_mode", get_trend_x_axis_options()[1])))
        group_mode = str(telegram_cfg.get("trend_group_mode", "overall") or "overall").strip().lower()
        idx = self.combo_trend_group_mode.findData(group_mode)
        self.combo_trend_group_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.chk_trend_normalize.setChecked(bool(telegram_cfg.get("trend_normalize", False)))
        self.chk_trend_smoothing.setChecked(bool(telegram_cfg.get("trend_smoothing", False)))
        self.chk_trend_pdf_enabled.setChecked(bool(telegram_cfg.get("trend_pdf_enabled", False)))

        self.test_status_label.setText("尚未測試。")
        self.edit_chat_id.set_mask_enabled(True)
        self.btn_toggle_chat_id.setText("顯示")
        self._apply_enabled_state()
        self._refresh_preview()

    def get_settings(self) -> Dict:
        hours = []
        for combo in self._time_combos:
            text = combo.currentText().strip()
            if not text:
                continue
            try:
                hour = int(text.split(":", 1)[0])
            except Exception:
                continue
            if 0 <= hour <= 23 and hour not in hours:
                hours.append(hour)
        hours.sort()

        selected_metrics = [metric for metric, chk in self._metric_checks.items() if chk.isChecked()]

        return {
            "GENERAL": {
                "timezone": "Asia/Taipei",
            },
            "TELEGRAM": {
                "enabled": self.chk_tg_enabled.isChecked(),
                "bot_token": self.edit_bot_token.text().strip(),
                "chat_id": self.edit_chat_id.value().strip(),
                "bot_token_file": self.edit_bot_token_file.text().strip(),
                "chat_id_file": self.edit_chat_id_file.text().strip(),
                "notify_on_critical_error": self.chk_notify_error.isChecked(),
                "notify_on_measurement_start": self.chk_notify_start.isChecked(),
                "notify_on_daily_summary": self.chk_notify_summary.isChecked(),
                "daily_report_count": len(hours),
                "daily_report_hours": hours,
                "cooldown_seconds": self.spin_cooldown.value(),
                "max_message_length": self.spin_max_len.value(),
                "trend_images_enabled": self.chk_trend_images_enabled.isChecked(),
                "trend_metrics": selected_metrics,
                "trend_direction": self.combo_trend_direction.currentText(),
                "trend_path": self.combo_trend_path.currentText(),
                "trend_x_axis_mode": self.combo_trend_x_axis.currentText(),
                "trend_group_mode": self.combo_trend_group_mode.currentData() or "overall",
                "trend_normalize": self.chk_trend_normalize.isChecked(),
                "trend_show_env": False,
                "trend_smoothing": self.chk_trend_smoothing.isChecked(),
                "trend_send_as_document": False,
                "trend_pdf_enabled": self.chk_trend_pdf_enabled.isChecked(),
                "trend_pdf_include_env_when_available": True,
                "trend_image_width": 2400,
                "trend_image_height": 1400,
            },
            "EMAIL": {"enabled": False},
            "LINE": {"enabled": False},
        }

    def _selected_metric_labels(self) -> List[str]:
        return [metric for metric, chk in self._metric_checks.items() if chk.isChecked()]

    def _masked_chat_id_preview(self) -> str:
        chat_id = self.edit_chat_id.value().strip()
        if not chat_id:
            return "未輸入"
        if len(chat_id) <= 4:
            return "*" * len(chat_id)
        return f"{'*' * (len(chat_id) - 4)}{chat_id[-4:]}"

    def _trend_group_mode_text(self) -> str:
        idx = self.combo_trend_group_mode.currentIndex()
        return self.combo_trend_group_mode.itemText(idx) if idx >= 0 else "整體"

    def _build_test_preview(self) -> str:
        hours = [combo.currentText() for combo in self._time_combos]
        joined_hours = ", ".join(hours) if hours else "未設定"
        metrics = self._selected_metric_labels()
        metrics_text = ", ".join(metrics) if metrics else "未勾選"
        return (
            "ReliabilityX Telegram 測試訊息\n"
            f"啟用狀態: {'是' if self.chk_tg_enabled.isChecked() else '否'}\n"
            f"Chat ID: {self._masked_chat_id_preview()}\n"
            f"Secret TXT: {'已設定' if (self.edit_bot_token_file.text().strip() or self.edit_chat_id_file.text().strip()) else '未設定'}\n"
            f"重大錯誤通知: {'是' if self.chk_notify_error.isChecked() else '否'}\n"
            f"開始量測通知: {'是' if self.chk_notify_start.isChecked() else '否'}\n"
            f"每日摘要通知: {'是' if self.chk_notify_summary.isChecked() else '否'}\n"
            f"每日摘要整點: {joined_hours}\n"
            f"趨勢報告推播: {'是' if self.chk_trend_images_enabled.isChecked() else '否'}\n"
            f"趨勢報告格式: {'PDF（每頁一張圖）' if self.chk_trend_pdf_enabled.isChecked() else '單張 PNG'}\n"
            f"趨勢圖指標: {metrics_text}\n"
            f"趨勢圖方向/路徑: {self.combo_trend_direction.currentText()} / {self.combo_trend_path.currentText()}\n"
            f"趨勢圖X軸: {self.combo_trend_x_axis.currentText()}\n"
            f"趨勢圖分組: {self._trend_group_mode_text()}\n"
            "環境子圖：PDF 模式下若有環境資料，會自動加在每頁主圖下方。\n"
            "若你收到這則訊息，代表 Bot Token 與 Chat ID 已可正常通訊。"
        )

    def _refresh_preview(self):
        self.test_preview.setPlainText(self._build_test_preview())
        self._apply_enabled_state()

    def _on_test_message_clicked(self):
        if not self.chk_tg_enabled.isChecked():
            QMessageBox.information(
                self,
                "尚未啟用 Telegram 通知",
                "尚未啟用 Telegram 通知，請先勾選「啟用 Telegram 通知」後再發送測試訊息。",
            )
            return

        token = self.edit_bot_token.text().strip()
        chat_id = self.edit_chat_id.value().strip()
        token_file = self.edit_bot_token_file.text().strip()
        chat_file = self.edit_chat_id_file.text().strip()
        resolved = config.resolve_telegram_secret_fields({
            "bot_token": token,
            "chat_id": chat_id,
            "bot_token_file": token_file,
            "chat_id_file": chat_file,
        })
        token = str(resolved.get("bot_token", "") or "").strip()
        chat_id = str(resolved.get("chat_id", "") or "").strip()
        preview = self._build_test_preview()
        self.test_preview.setPlainText(preview)

        if not token:
            QMessageBox.warning(self, "欄位不足", "請先輸入 Bot Token。")
            return
        if not chat_id:
            QMessageBox.warning(self, "欄位不足", "請先輸入 Chat ID。")
            return

        self.btn_test_message.setEnabled(False)
        self.test_status_label.setText("測試訊息發送中...")
        thread = threading.Thread(
            target=self._send_test_message_worker,
            args=(token, chat_id, preview),
            daemon=True,
        )
        thread.start()

    def _send_test_message_worker(self, token: str, chat_id: str, preview: str):
        ok, message = send_telegram_message(token, chat_id, preview)
        self.test_result_signal.emit(ok, message)

    def _handle_test_result(self, ok: bool, message: str):
        self.btn_test_message.setEnabled(True)
        if ok:
            self.test_status_label.setText("測試成功：Telegram 已成功接收訊息。")
        else:
            self.test_status_label.setText(f"測試失敗：{message}")

    def cleanup(self):
        """Placeholder cleanup hook for dialog close."""
        pass
