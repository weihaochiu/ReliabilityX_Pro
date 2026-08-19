# compile_ui.py
"""
[Docstring by Gemini on 2026-03-24]
This script compiles all Qt Designer UI files (.ui) into their corresponding
Python modules (.py), making them ready for static import by the application.

This is a mandatory step for developers after cloning the repository or
modifying any .ui file. It ensures that the application can be run directly
from source without `ModuleNotFoundError`.

This script is the single source of truth for the UI compilation map and is
also called by the main `build_and_deploy.py` script.
"""
import os
import subprocess
import sys

# A dictionary mapping source .ui files to their destination .py files
UI_FILES = {
    "gui/ui/main_window.ui": "gui/ui/main_window_ui.py",
    "gui/ui/system_config.ui": "gui/ui/system_config_ui.py",
    "gui/ui/personnel_tab.ui": "gui/ui/personnel_tab_ui.py",
    "gui/ui/measurement_tab.ui": "gui/ui/measurement_tab_ui.py",
    "gui/ui/environment_tab.ui": "gui/ui/environment_tab_ui.py",
    "gui/ui/relay_tab.ui": "gui/ui/relay_tab_ui.py",
}

def run_command(command, description):
    """Executes a shell command and prints its status."""
    print(f"--- Running: {description} ---")
    try:
        # Ensure utf-8 encoding is used for cross-platform compatibility
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, encoding='utf-8')
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            # Don't treat all stderr as an error, pyuic6 can print warnings here
            print("Output (stderr):")
            print(result.stderr)
        print(f"--- Success: {description} ---\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"--- [FAIL] {description} ---")
        print(f"Error executing command: {e.cmd}")
        print(f"Return code: {e.returncode}")
        if e.stdout:
            print("Output (stdout):")
            print(e.stdout)
        if e.stderr:
            print("Error Output (stderr):")
            print(e.stderr)
        return False
    except Exception as e:
        print(f"--- [FAIL] An unexpected error occurred: {description} ---")
        print(str(e))
        return False

def compile_all_ui():
    """
    Compiles all .ui files specified in the UI_FILES dictionary into .py files.
    """
    print("Starting UI compilation process...")
    print(f"Found {len(UI_FILES)} UI files to compile.")
    
    success_count = 0
    fail_count = 0
    
    for ui_src, py_dest in UI_FILES.items():
        if os.path.exists(ui_src):
            command = f"pyuic6 -o {py_dest} {ui_src}"
            if run_command(command, f"Compiling {ui_src} -> {py_dest}"):
                success_count += 1
            else:
                fail_count += 1
        else:
            print(f"[WARN] Source UI file not found, skipping: {ui_src}")
            fail_count += 1
    
    print("-" * 30)
    if fail_count == 0:
        print(f"[OK] All {success_count} UI files compiled successfully.")
        return True
    else:
        print(f"[FAIL] Finished with {fail_count} errors and {success_count} successes.")
        return False

if __name__ == "__main__":
    if not compile_all_ui():
        # Exit with a non-zero code to indicate failure, useful for CI/CD
        sys.exit(1)
