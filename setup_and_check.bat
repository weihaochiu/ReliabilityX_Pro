@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"
echo [ReliabilityX Pro] Prepare environment and run mock-only checks.
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements_test.txt
if errorlevel 1 goto :failed
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto :failed
echo.
echo [PASS] Offline tests passed. Run 執行.bat separately for the real application.
echo These tests do not validate physical wiring or operate laboratory instruments.
pause
exit /b 0

:failed
echo.
echo [FAIL] Setup or tests failed. Review the messages above before machine testing.
echo If Python 3.11 is missing, install it with the Python launcher enabled.
pause
exit /b 1
