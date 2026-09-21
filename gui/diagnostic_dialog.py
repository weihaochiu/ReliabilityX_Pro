"""OI-057: reusable plain-language diagnostics with expandable/copyable evidence."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QAbstractButton


def create_diagnostic_dialog(parent, report):
    """Create a report dialog without performing hardware or filesystem IO.

    Args:
        parent: Parent QWidget.
        report: Framework-free diagnostic report.

    Returns:
        QMessageBox ready to show, with a copy button and expandable details.
    """
    dialog = QMessageBox(parent)
    dialog.setWindowTitle("操作未完成 — 原因與處理方式")
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(report["title"])
    dialog.setInformativeText(report["summary"])
    dialog.setDetailedText(report["details"])
    dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
    dialog.button(QMessageBox.StandardButton.Ok).setText("關閉")
    for button in dialog.findChildren(QAbstractButton):
        if button.text().replace("&", "") == "Show Details...":
            button.setText("顯示技術詳細資料")
            def update_details_label(checked=False, target=button):
                """Keep Qt's native details toggle labelled in Traditional Chinese."""
                expanded = not bool(target.property("report_expanded"))
                target.setProperty("report_expanded", expanded)
                target.setText("收合技術詳細資料" if expanded else "顯示技術詳細資料")
            button.clicked.connect(update_details_label)
    copy_button = dialog.addButton("複製診斷資料", QMessageBox.ButtonRole.ActionRole)
    copy_button.clicked.connect(lambda: QApplication.clipboard().setText(
        report["title"] + "\n" + report["summary"] + "\n\n" + report["details"]))
    return dialog


def show_diagnostic_dialog(parent, report):
    """Log and show an actionable report on the GUI thread.

    Args:
        parent: Parent QWidget.
        report: Structured diagnostic report.
    """
    logging.getLogger(__name__).error("[OPERATOR DIAGNOSTIC] %s\n%s", report["title"], report["details"])
    create_diagnostic_dialog(parent, report).exec()
