@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import ds_simulator.app" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m ds_simulator.app
if errorlevel 1 goto failed
exit /b 0
:failed
echo Please install Python 3.12. Internet is required for the first installation.
echo See README.md for the manual PowerShell commands.
pause
exit /b 1
