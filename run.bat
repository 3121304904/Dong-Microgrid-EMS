@echo off
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
    goto :end
)

echo [Dong v1.4] No Python environment was found.
echo Please run setup.bat first, then start run.bat again.
pause

:end
endlocal
