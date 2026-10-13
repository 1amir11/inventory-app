@echo off
rem ============================================================
rem start_demo.bat - run the app on FAKE demo data (training only).
rem Creates data_demo\ with 14 days of fake history ON THIS PC, then
rem starts the app on that folder with a visible DEMO badge.
rem Real data in data\ is never touched. No database ships in the zip.
rem ============================================================
setlocal
chcp 65001 >nul

set "APPDIR=%~dp0"

set "PYTHON=%APPDIR%runtime\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] Portable Python not found: runtime\python.exe
    pause
    exit /b 1
)

if exist "%APPDIR%data_demo" (
    echo.
    echo data_demo already exists. Running the seed again would DELETE it
    echo and rebuild 14 days of fake history from scratch.
    echo.
    set /p "ANSWER=Rebuild the demo data? Type YES to confirm: "
    if /i not "%ANSWER%"=="YES" (
        echo Cancelled. Starting the app on the existing data_demo...
        goto :start
    )
    rmdir /s /q "%APPDIR%data_demo"
    if errorlevel 1 (
        echo [ERROR] Could not remove data_demo. Close the app first.
        pause
        exit /b 1
    )
)

echo Creating fake demo history in data_demo\ ...
"%PYTHON%" "%APPDIR%seed_demo.py" "%APPDIR%data_demo"
if errorlevel 1 (
    echo [ERROR] seed_demo.py failed.
    pause
    exit /b 1
)

:start
rem --- Find pythonw.exe for the hidden launch (same order as start.bat).
set "PYW=%APPDIR%runtime\pythonw.exe"
if not exist "%PYW%" set "PYW=%APPDIR%runtime\python.exe"

rem --- Launch on the demo folder (visible DEMO badge in the app).
set "KITCHEN_DATA_DIR=data_demo"
start "" "%PYW%" "%APPDIR%launcher.py"

ping -n 6 127.0.0.1 >nul
netstat -ano | findstr LISTENING | findstr :8001 >nul 2>&1
if not errorlevel 1 exit /b 0
echo.
echo [ERROR] The demo stopped within seconds. See kitchen_launcher.log.
pause
exit /b 1
