"""Runtime dependency bootstrap for ReliabilityX Pro.

This module is intentionally limited to Python standard library imports so it can
run before PyQt6 and instrument packages are available.  It is called as the
first step of ``main.py`` and attempts to install missing runtime packages by
invoking pip through the currently running Python interpreter.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class RuntimeDependency:
    """Describe one Python import and the pip package that provides it.

    Attributes:
        module: Import name used by Python, e.g. ``serial``.
        package: Package spec passed to pip, e.g. ``pyserial``.
        purpose: Human-readable reason shown in logs.
    """

    module: str
    package: str
    purpose: str


RUNTIME_DEPENDENCIES: Sequence[RuntimeDependency] = (
    RuntimeDependency("PyQt6", "PyQt6", "Qt GUI runtime"),
    RuntimeDependency("pyqtgraph", "pyqtgraph", "real-time plotting"),
    RuntimeDependency("numpy", "numpy", "numeric arrays and IV calculations"),
    RuntimeDependency("scipy", "scipy", "curve fitting and scientific utilities"),
    RuntimeDependency("matplotlib", "matplotlib", "report/snapshot plotting"),
    RuntimeDependency("serial", "pyserial", "serial communication for relay/chamber devices"),
    RuntimeDependency("pyvisa", "pyvisa", "SMU VISA communication frontend"),
    RuntimeDependency("pyvisa_py", "pyvisa-py", "pure Python VISA backend fallback"),
    RuntimeDependency("reportlab", "reportlab", "PDF/report export"),
    RuntimeDependency("pandas", "pandas", "CSV/table analysis compatibility"),
)


class DependencyBootstrapError(RuntimeError):
    """Raised when required dependencies cannot be installed or imported."""


def _application_root() -> Path:
    """Return the source/runtime directory used for bootstrap logs.

    Returns:
        Directory that contains the running source file, or the frozen executable
        directory when packaged with PyInstaller.
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _log_path() -> Path:
    """Return the dependency bootstrap log path and ensure its folder exists."""

    log_dir = _application_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "dependency_bootstrap.log"


def _log(message: str) -> None:
    """Write a timestamped bootstrap message to console and log file.

    Args:
        message: Text to be printed and persisted.
    """

    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    try:
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        # Last-resort startup path; console output is still available.
        pass


def _show_startup_error(message: str) -> None:
    """Show an error dialog without depending on PyQt6.

    Args:
        message: Error text to display.
    """

    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("ReliabilityX Pro dependency bootstrap failed", message)
        root.destroy()
    except Exception:
        # Some minimal Windows/Python installs may not have Tk. Console/log remain.
        pass


def _missing_dependencies(dependencies: Iterable[RuntimeDependency]) -> List[RuntimeDependency]:
    """Return dependencies whose import modules are not currently importable.

    Args:
        dependencies: Dependency definitions to check.

    Returns:
        List of missing dependency definitions.
    """

    missing: List[RuntimeDependency] = []
    importlib.invalidate_caches()
    for dep in dependencies:
        try:
            importlib.import_module(dep.module)
        except Exception as exc:  # ImportError plus binary-load errors.
            _log(f"Missing or unusable dependency: {dep.module} ({dep.package}) - {exc}")
            missing.append(dep)
    return missing


def _run_command(command: Sequence[str]) -> None:
    """Run a subprocess command and stream output to the bootstrap log.

    Args:
        command: Command list for ``subprocess.run``.

    Raises:
        DependencyBootstrapError: If the command returns a non-zero code.
    """

    _log("Running: " + " ".join(command))
    proc = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(_application_root()),
    )
    if proc.stdout:
        for line in proc.stdout.splitlines():
            _log("pip> " + line)
    if proc.returncode != 0:
        raise DependencyBootstrapError(
            f"Command failed with exit code {proc.returncode}: {' '.join(command)}"
        )


def _ensure_pip_available() -> None:
    """Ensure pip is available for the current Python interpreter.

    Raises:
        DependencyBootstrapError: If pip cannot be invoked after ensurepip.
    """

    try:
        _run_command([sys.executable, "-m", "pip", "--version"])
        return
    except DependencyBootstrapError:
        _log("pip is not available; trying ensurepip --upgrade")

    _run_command([sys.executable, "-m", "ensurepip", "--upgrade"])
    _run_command([sys.executable, "-m", "pip", "--version"])


def _install_packages(missing: Sequence[RuntimeDependency]) -> None:
    """Install missing pip packages into the active Python environment.

    Args:
        missing: Missing dependency definitions.
    """

    packages = []
    seen = set()
    for dep in missing:
        if dep.package not in seen:
            packages.append(dep.package)
            seen.add(dep.package)
    if not packages:
        return

    _ensure_pip_available()
    _run_command(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--upgrade",
            *packages,
        ]
    )


def ensure_runtime_dependencies(auto_install: bool = True) -> None:
    """Verify and optionally install ReliabilityX Pro runtime dependencies.

    This function should be called before importing PyQt6 or hardware packages.
    It is skipped in PyInstaller-frozen mode because the dependencies should be
    bundled into the executable.

    Args:
        auto_install: Whether missing packages should be installed via pip.

    Raises:
        SystemExit: Exits with code 1 if dependencies remain unavailable.
    """

    if getattr(sys, "frozen", False):
        return

    if os.environ.get("RXPRO_SKIP_AUTO_INSTALL", "").strip() in {"1", "true", "TRUE", "yes"}:
        auto_install = False

    missing = _missing_dependencies(RUNTIME_DEPENDENCIES)
    if not missing:
        _log("All runtime dependencies are available.")
        return

    if not auto_install:
        packages = " ".join(dep.package for dep in missing)
        message = (
            "ReliabilityX Pro 缺少必要 Python 套件，且目前已停用自動安裝。\n\n"
            f"請手動執行：\n{sys.executable} -m pip install {packages}\n\n"
            f"詳細紀錄：{_log_path()}"
        )
        _log(message)
        _show_startup_error(message)
        raise SystemExit(1)

    try:
        _install_packages(missing)
    except Exception as exc:
        packages = " ".join(dep.package for dep in missing)
        message = (
            "ReliabilityX Pro 嘗試自動安裝 Python 套件失敗。\n\n"
            "可能原因：此電腦無網路、pip 被防火牆擋住、或 Python 安裝權限不足。\n\n"
            f"請在專案資料夾手動執行：\n{sys.executable} -m pip install {packages}\n\n"
            f"錯誤：{exc}\n\n"
            f"詳細紀錄：{_log_path()}"
        )
        _log(message)
        _show_startup_error(message)
        raise SystemExit(1)

    still_missing = _missing_dependencies(RUNTIME_DEPENDENCIES)
    if still_missing:
        packages = " ".join(dep.package for dep in still_missing)
        message = (
            "ReliabilityX Pro 已執行 pip 安裝，但仍無法載入部分套件。\n\n"
            f"仍缺少：{packages}\n\n"
            "請關閉視窗、重新開啟 CMD 後再執行，或手動安裝上述套件。\n"
            f"詳細紀錄：{_log_path()}"
        )
        _log(message)
        _show_startup_error(message)
        raise SystemExit(1)

    _log("Runtime dependencies were installed and verified successfully.")
