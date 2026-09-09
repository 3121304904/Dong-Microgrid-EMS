@echo off
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"

set "BUILD_PYTHON="
for %%P in (".venv\Scripts\python.exe" ".build_venv\Scripts\python.exe") do (
    if not defined BUILD_PYTHON if exist "%%~fP" (
        "%%~fP" -c "import PyInstaller, PySide6" >nul 2>&1
        if not errorlevel 1 set "BUILD_PYTHON=%%~fP"
    )
)
if not defined BUILD_PYTHON (
    echo Run setup.bat before building the executable.
    pause
    exit /b 1
)

"%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean --windowed --name DongMicrogridEMS --runtime-hook packaging\pyi_runtime_hook.py main.py
if errorlevel 1 (
    echo EXE build failed.
    pause
    exit /b 1
)

rem ICU copied from numeric packages conflicts with the Windows Qt dependency chain.
rem Windows 10/11 provides the compatible system ICU libraries used by PySide6.
del /Q "dist\DongMicrogridEMS\_internal\icuuc.dll" 2>nul
del /Q "dist\DongMicrogridEMS\_internal\icudt78.dll" 2>nul

copy /Y "README.md" "dist\DongMicrogridEMS\README.md" >nul
copy /Y "USER_MANUAL.md" "dist\DongMicrogridEMS\USER_MANUAL.md" >nul
copy /Y "CHANGELOG.md" "dist\DongMicrogridEMS\CHANGELOG.md" >nul
xcopy /E /I /Y "sample_data" "dist\DongMicrogridEMS\sample_data" >nul
xcopy /E /I /Y "docs" "dist\DongMicrogridEMS\docs" >nul
if not exist "dist\DongMicrogridEMS\output" mkdir "dist\DongMicrogridEMS\output"

echo [Dong v1.4] Build completed: dist\DongMicrogridEMS\DongMicrogridEMS.exe
pause
endlocal
