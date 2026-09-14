@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "APP_ROOT=%~dp0"
set "PYTHONNOUSERSITE=1"
set "LOG_DIR=%APP_ROOT%output"
set "LOG_FILE=%LOG_DIR%\startup.log"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

>"%LOG_FILE%" echo [Dong v1.7] Startup started at %date% %time%
>>"%LOG_FILE%" echo Working directory: %APP_ROOT%

rem Prefer the portable EXE so the released folder works without Python.
if exist "%APP_ROOT%dist\DongMicrogridEMS\DongMicrogridEMS.exe" (
    echo Starting the portable Dong v1.7 application...
    >>"%LOG_FILE%" echo Launch mode: portable EXE
    "%APP_ROOT%dist\DongMicrogridEMS\DongMicrogridEMS.exe"
    set "EXIT_CODE=%ERRORLEVEL%"
    if not "%EXIT_CODE%"=="0" (
        echo.
        echo Dong v1.7 failed to start. Exit code: %EXIT_CODE%
        echo Diagnostic log: "%LOG_FILE%"
        if exist "%LOG_FILE%" type "%LOG_FILE%"
        pause
    )
    exit /b %EXIT_CODE%
)

rem Fall back to the project virtual environment for source-code use.
if exist "%APP_ROOT%.venv\Scripts\python.exe" (
    echo Starting Dong v1.7 from the local Python environment...
    >>"%LOG_FILE%" echo Launch mode: .venv Python
    "%APP_ROOT%.venv\Scripts\python.exe" "%APP_ROOT%main.py" >>"%LOG_FILE%" 2>&1
    set "EXIT_CODE=%ERRORLEVEL%"
    if not "%EXIT_CODE%"=="0" (
        echo.
        echo Dong v1.7 exited with code %EXIT_CODE%.
        echo Run setup.bat if dependencies are missing.
        echo Diagnostic log: "%LOG_FILE%"
        type "%LOG_FILE%"
        pause
    )
    exit /b %EXIT_CODE%
)

rem Last fallback: a system Python launcher, if one is installed.
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    echo Starting Dong v1.7 with Python launcher...
    >>"%LOG_FILE%" echo Launch mode: py -3
    py -3 "%APP_ROOT%main.py" >>"%LOG_FILE%" 2>&1
    set "EXIT_CODE=%ERRORLEVEL%"
    if not "%EXIT_CODE%"=="0" (
        echo.
        echo Dong v1.7 exited with code %EXIT_CODE%.
        echo Run setup.bat if dependencies are missing.
        echo Diagnostic log: "%LOG_FILE%"
        type "%LOG_FILE%"
        pause
    )
    exit /b %EXIT_CODE%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    echo Starting Dong v1.7 with system Python...
    >>"%LOG_FILE%" echo Launch mode: python
    python "%APP_ROOT%main.py" >>"%LOG_FILE%" 2>&1
    set "EXIT_CODE=%ERRORLEVEL%"
    if not "%EXIT_CODE%"=="0" (
        echo.
        echo Dong v1.7 exited with code %EXIT_CODE%.
        echo Run setup.bat if dependencies are missing.
        echo Diagnostic log: "%LOG_FILE%"
        type "%LOG_FILE%"
        pause
    )
    exit /b %EXIT_CODE%
)

echo No portable EXE or Python environment was found.
echo Please verify that the dist\DongMicrogridEMS folder is present,
echo or install Python and run setup.bat before trying again.
>>"%LOG_FILE%" echo ERROR: no portable EXE or Python environment found.
echo Diagnostic log: "%LOG_FILE%"
pause
exit /b 1
