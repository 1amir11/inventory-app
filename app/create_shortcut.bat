@echo off
rem ============================================================
rem create_shortcut.bat - puts the app shortcut on the Desktop.
rem Name is Arabic (created via a UTF-16 script, so it works on
rem any codepage). Icon: app\icon.ico. Double-clicking it opens
rem the app hidden (no console window).
rem ============================================================
setlocal
chcp 65001 >nul

set "APPDIR=%~dp0"

set "PYTHON=%APPDIR%runtime\python.exe"
if not exist "%PYTHON%" (
    echo [WARN] Portable Python not found - using system Python.
    set "PYTHON=python"
)

"%PYTHON%" "%APPDIR%make_shortcut.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Could not create the desktop shortcut.
    pause
    exit /b 1
)

echo.
echo Done. Look for the new shortcut on your Desktop.
pause
