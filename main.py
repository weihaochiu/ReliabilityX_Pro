"""ReliabilityX Pro application entry point.

This entry point first runs the runtime dependency bootstrap before importing
PyQt6 or hardware communication packages.  The bootstrap prevents the common
new-PC failure mode where double-clicking ``main.py`` flashes and exits because
PyQt6/pyvisa/pyserial are not installed yet.
"""

from dependency_bootstrap import ensure_runtime_dependencies

ensure_runtime_dependencies()

import sys
from PyQt6.QtWidgets import QApplication, QMessageBox

import config
from core.measure_engine import MeasureEngine

from core.log_manager import LogManager

from driver.smu_driver import SMUDriver, VisaBackendUnavailableError
from driver.relay_driver import RelayDriver
from driver.chamber_driver import ChamberDriver

from gui.main_window import MainWindow
from gui.log_window import LogWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ReliabilityX Pro")

    try:
        qss_path = config.get_resource_path("assets/style.qss")
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
        print(f"Global stylesheet loaded successfully: {qss_path}")
    except FileNotFoundError:
        print("Warning: assets/style.qss not found. Using default styles.")
    except Exception as e:
        print(f"Error loading stylesheet: {e}")

    log_window = LogWindow()
    log_mgr = LogManager()
    log_mgr.log_signal.connect(log_window.append_log)
    log_mgr.log_info("系統啟動中...")

    try:
        smu_driver = SMUDriver(log_manager=log_mgr)
    except VisaBackendUnavailableError as exc:
        msg = (
            "SMU VISA backend 初始化失敗。\n\n"
            "請確認已安裝 NI-VISA 或 pyvisa-py，並重新啟動 ReliabilityX Pro。\n\n"
            f"詳細錯誤: {exc}"
        )
        log_mgr.log_error(msg)
        QMessageBox.critical(None, "VISA 後端初始化失敗", msg)
        sys.exit(1)

    relay_driver = RelayDriver(log_manager=log_mgr)
    chamber_driver = ChamberDriver(log_manager=log_mgr)

    measure_engine = MeasureEngine(
        smu_driver=smu_driver,
        relay_driver=relay_driver,
        chamber_driver=chamber_driver,
        log_manager=log_mgr,
    )

    main_window = MainWindow(measure_engine, log_window)
    main_window.show()
    log_window.show()

    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
