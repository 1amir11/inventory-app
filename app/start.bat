@echo off
rem ============================================================
rem start.bat - desktop-like launcher for the kitchen inventory app.
rem Runs the self-check, then starts launcher.py fully hidden
rem (pythonw.exe: no console for server or browser handling).
rem Target: Windows 7 SP1 64-bit and newer, nothing installed.
rem Uses 127.0.0.1:8001 (8000 belongs to the cafeteria POS).
rem ============================================================
setlocal
chcp 65001 >nul

set "APPDIR=%~dp0"

set "PYTHON=%APPDIR%runtime\python.exe"
if not exist "%PYTHON%" (
    echo [WARN] Portable Python not found: runtime\python.exe
    echo [WARN] Falling back to system Python on PATH.
    echo [WARN] For the Windows 7 target PC, download
    echo [WARN]   python-3.8.10-embed-amd64.zip
    echo [WARN] and extract ALL files directly into app\runtime\
    echo [WARN] See runtime\README.txt for the exact steps.
    set "PYTHON=python"
)

rem --- Self-check: Python starts, sqlite3 imports, data/ writable.
rem     "dev" arg = system-Python fallback (version warning only).
if "%PYTHON%" == "python" (
    "%PYTHON%" "%APPDIR%check.py" dev
) else (
    "%PYTHON%" "%APPDIR%check.py"
)
if errorlevel 1 goto :pythonfail

rem --- Find pythonw.exe for the hidden launch (same preference order).
set "PYW=%APPDIR%runtime\pythonw.exe"
if not exist "%PYW%" (
    where pythonw >nul 2>nul && (
        for /f "delims=" %%i in ('where pythonw') do set "PYW=%%i"
    )
)
if not exist "%PYW%" (
    if "%PYTHON%" == "python" (
        rem No pythonw anywhere: run the launcher visibly in this console.
        "%PYTHON%" "%APPDIR%launcher.py"
        exit /b 0
    ) else (
        set "PYW=%APPDIR%runtime\python.exe"
    )
)

rem --- Launch hidden: no console window for launcher/server/browser.
start "" "%PYW%" "%APPDIR%launcher.py"

rem --- Early-exit watch: the launcher is hidden, so a death within seconds
rem     (no browser, server failed) would otherwise close silently with
rem     nothing shown. Wait a few seconds; if nothing listens on port 8001
rem     the launch already failed, so print the tail of kitchen_launcher.log
rem     and pause. (Port check, not a process scan: wmic output is UTF-16 and
rem     findstr can never match it.) Win7-safe only.
ping -n 6 127.0.0.1 >nul
netstat -ano | findstr LISTENING | findstr :8001 >nul 2>&1
if not errorlevel 1 goto :launchexitok
echo.
echo [ERROR] The app stopped within seconds. Last lines of kitchen_launcher.log:
if exist "%APPDIR%kitchen_launcher.log" "%PYTHON%" -c "import collections,sys; p=sys.argv[1]; print(''.join(list(collections.deque(open(p,encoding='utf-8',errors='replace'),25))))" "%APPDIR%kitchen_launcher.log"
if not exist "%APPDIR%kitchen_launcher.log" echo (no kitchen_launcher.log found yet)
echo.
pause
exit /b 1

:launchexitok
exit /b 0

:pythonfail
echo.
echo [ERROR] Python failed to start or failed the self-check.
echo.
echo If the message was "not recognized as a command":
echo   No Python on PATH and no runtime\python.exe present.
echo   Extract the embeddable package into runtime\ first.
echo.
echo If a DLL error appeared (e.g. api-ms-win-crt-*.dll not found,
echo or the program failed to initialize):
echo   Windows 7 needs BOTH updates for Python 3.8:
echo     - KB2999226 (Universal C Runtime)
echo     - KB2533623 (API sets update)
echo   Install both, reboot, then run start.bat again.
echo.
pause
exit /b 1
