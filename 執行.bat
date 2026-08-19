@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo [ReliabilityX Pro] Project folder: %CD%
echo [ReliabilityX Pro] Starting application...

if exist ".venv\Scripts\python.exe" (
    echo [ReliabilityX Pro] Using project virtual environment: .venv
    ".venv\Scripts\python.exe" main.py
) else (
    echo [ReliabilityX Pro] No .venv found. Using Python launcher: py -3.11
    py -3.11 main.py
)

if errorlevel 1 (
    echo.
    echo [ReliabilityX Pro] Application exited with an error.
    echo Please copy the messages above or check logs\dependency_bootstrap.log.
    pause
)
