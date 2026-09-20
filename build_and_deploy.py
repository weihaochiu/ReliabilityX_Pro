"""
ReliabilityX Pro build and deployment helper.

功能：
1. 使用目前 Python 環境先執行 compile_ui.py。
2. 建置前檢查關鍵依賴是否已安裝。
3. 清除舊的 build / dist 目錄。
4. 讓使用者選擇 console / noconsole 模式。
5. 呼叫 PyInstaller 產生 onedir 輸出。
6. 讓使用者選擇儲存位置後，建立 ZIP 部署包。
7. ZIP 成功後自動清理暫存建置目錄。

v2 補充：
- 新增 `reportlab` 依賴檢查，避免 PDF 通知功能導入後，
  在建置機或部署環境中因套件缺失而於執行期失敗。
- 明確將 `compile_ui.py` 視為根目錄建置工具鏈的一部分。

2026-09-20: verify the complete runtime dependency registry before packaging
the channel outcome and live pause/resume GUI changes.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Iterable, List, Tuple
from dependency_bootstrap import RUNTIME_DEPENDENCIES

APP_NAME = "ReliabilityX Pro"
MAIN_SCRIPT = "main.py"
ASSETS_TO_INCLUDE = ["assets", "config", "help", "gui"]
BUILD_DIRS = ["dist", "build"]
DEPLOY_EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", "logs"}
DEPLOY_EXCLUDE_FILE_NAMES = {
    "user_settings.json",
    "notification_settings.json",
    "runtime_schedule_state.json",
    "CHANGESET_MANIFEST.md",
}
DEPLOY_EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}
REQUIRED_PACKAGES: List[Tuple[str, str]] = [
    (dependency.module, dependency.package) for dependency in RUNTIME_DEPENDENCIES
] + [
    ("PyInstaller", "pyinstaller"),
]


def run_command(command: str, description: str) -> bool:
    """執行系統指令並讓進度直接顯示在終端機。"""
    print(f"--- 開始執行: {description} ---")
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"--- 完成: {description} ---\n")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ {description} 失敗! returncode={exc.returncode}")
        return False
    except Exception as exc:
        print(f"❌ {description} 發生未預期的錯誤: {exc}")
        return False


def _show_error(title: str, message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showerror(title, message)
    root.destroy()


def _show_warning(title: str, message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showwarning(title, message)
    root.destroy()


def _show_info(title: str, message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showinfo(title, message)
    root.destroy()


def check_required_packages(packages: Iterable[Tuple[str, str]]) -> bool:
    """檢查建置流程所需套件是否存在。"""
    missing: List[Tuple[str, str]] = []

    print("--- 開始檢查建置依賴 ---")
    for import_name, install_name in packages:
        try:
            importlib.import_module(import_name)
            print(f"[OK] 已找到套件: {import_name}")
        except Exception:
            print(f"[MISSING] 缺少套件: {import_name}")
            missing.append((import_name, install_name))

    if not missing:
        print("--- 建置依賴檢查完成：全部已安裝 ---\n")
        return True

    lines = [
        "建置流程已中止，因為目前 Python 環境缺少下列套件：",
        "",
    ]
    for import_name, install_name in missing:
        lines.append(f"- {import_name}    安裝指令：python -m pip install {install_name}")

    lines.extend(
        [
            "",
            "請先在與本建置腳本相同的 Python 環境中完成安裝，再重新執行 build_and_deploy.py。",
        ]
    )
    message = "\n".join(lines)
    print(message)
    _show_error("缺少建置依賴", message)
    return False



def compile_ui() -> bool:
    """使用目前 Python 環境執行根目錄 compile_ui.py。"""
    py_executable = sys.executable
    return run_command(f'"{py_executable}" -u compile_ui.py', "編譯 Qt UI 檔案")



def clean_build_dirs() -> None:
    for folder in BUILD_DIRS:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"已清理舊的 {folder} 資料夾")



def ask_console_mode() -> bool:
    """回傳 True 表示隱藏 console，False 表示顯示 console。"""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    hide_console = messagebox.askyesno(
        "建置選項",
        "是否要隱藏命令提示字元視窗 (無黑窗)？\n\n"
        "- 「是 (Yes)」：最終發佈版，無黑色視窗。\n"
        "- 「否 (No)」：偵錯版，會顯示黑色視窗以查看輸出訊息。",
        icon="question",
    )
    root.destroy()
    return hide_console



def build_with_pyinstaller(hide_console: bool) -> bool:
    console_option = "--noconsole" if hide_console else "--console"
    print(f"使用者選擇: {'無控制台 (noconsole)' if hide_console else '顯示控制台 (console)'}")

    add_data_args = " ".join(
        [f'--add-data "{folder}{os.pathsep}{folder}"' for folder in ASSETS_TO_INCLUDE]
    )

    pyinstaller_cmd = (
        f'pyinstaller --onedir {console_option} '
        f'--splash "assets/splash.png" '
        f'--name "{APP_NAME}" '
        f'{add_data_args} '
        f'"{MAIN_SCRIPT}"'
    )
    return run_command(pyinstaller_cmd, "PyInstaller 打包")





def sanitize_build_output(build_output_dir: str) -> None:
    """Remove local/runtime-only files from the onedir folder before zipping."""
    root = Path(build_output_dir)
    if not root.exists():
        return

    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if path.is_dir() and path.name in DEPLOY_EXCLUDE_DIR_NAMES:
                shutil.rmtree(path, ignore_errors=True)
                print(f"[CLEAN] Removed runtime/cache directory: {path}")
            elif path.is_file() and (
                path.name in DEPLOY_EXCLUDE_FILE_NAMES or path.suffix.lower() in DEPLOY_EXCLUDE_SUFFIXES
            ):
                path.unlink(missing_ok=True)
                print(f"[CLEAN] Removed local/runtime file: {path}")
        except Exception as exc:
            print(f"[WARN] Could not remove release-excluded path {path}: {exc}")

    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    user_example = config_dir / "user_settings.example.json"
    if not user_example.exists():
        user_example.write_text(
            '{\n    "data_dir": "",\n    "log_dir": "",\n    "log_level": "INFO"\n}\n',
            encoding="utf-8",
        )

def create_zip_archive() -> None:
    """將 onedir 的建置結果打包成單一 ZIP。"""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    save_path = filedialog.asksaveasfilename(
        title=f"選擇儲存 {APP_NAME} 部署包的位置",
        defaultextension=".zip",
        filetypes=[("ZIP archives", "*.zip")],
        initialfile=f"{APP_NAME}_{datetime.now().strftime('%Y%m%d')}.zip",
    )
    root.destroy()

    if not save_path:
        print("操作取消：未選擇儲存位置。")
        return

    build_output_dir = os.path.join("dist", APP_NAME)
    archive_base_name = save_path.rsplit(".", 1)[0]

    try:
        sanitize_build_output(build_output_dir)
        data_dir_path = os.path.join(build_output_dir, "data")
        os.makedirs(data_dir_path, exist_ok=True)
        print("已在打包目錄中建立空的 'data' 資料夾")

        print(f"正在建立 ZIP 檔案: {save_path}")
        archive_path = shutil.make_archive(
            base_name=archive_base_name,
            format="zip",
            root_dir="dist",
            base_dir=APP_NAME,
        )

        success_msg = (
            f"🎉 部署包建立成功！\n"
            f"位置: {archive_path}\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print(success_msg)
        _show_info("完成", success_msg)

        print("\n正在清理暫存建置檔案...")
        clean_build_dirs()

    except Exception as exc:
        error_msg = f"❌ 建立部署包失敗: {exc}"
        print(error_msg)
        _show_error("錯誤", error_msg)



def build_process() -> None:
    if not check_required_packages(REQUIRED_PACKAGES):
        return

    if not compile_ui():
        print("UI 編譯失敗，建置流程已中止。")
        _show_error("建置失敗", "編譯 UI 檔案時發生錯誤，請檢查終端機輸出。")
        return

    clean_build_dirs()

    hide_console = ask_console_mode()
    if not build_with_pyinstaller(hide_console):
        _show_error("建置失敗", "PyInstaller 打包時發生錯誤，請檢查終端機輸出。")
        return

    create_zip_archive()


if __name__ == "__main__":
    if not Path("assets/splash.png").exists():
        _show_warning(
            "缺少檔案",
            "找不到 'assets/splash.png'！\n\n請先準備啟動畫面圖片，否則打包會失敗。",
        )
    else:
        build_process()
