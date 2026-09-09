@echo off
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py"
if not defined PY_CMD where python >nul 2>nul && set "PY_CMD=python"

if not defined PY_CMD (
    echo Python 3.11 or newer is required.
    echo Download it from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local virtual environment...
    %PY_CMD% -m venv .venv
)

echo Installing application dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Installation failed. Check the network connection and retry.
    pause
    exit /b 1
)

echo Setup completed. Double-click run.bat to launch Dong v1.3.
pause
endlocal
