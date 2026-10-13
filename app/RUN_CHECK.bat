@echo off
rem ============================================================
rem RUN_CHECK.bat - one-click environment report for the target PC.
rem Double-click only, no typing. Writes report.txt next to itself,
rem shows it, then pauses. Each section is isolated: a failure in
rem one section never stops the others.
rem Windows 7 safe: only commands that exist on Windows 7 SP1.
rem This app uses port 8001 (8000 belongs to the cafeteria POS).
rem ============================================================
setlocal
chcp 65001 >nul

set "APPDIR=%~dp0"
set "REPORT=%APPDIR%report.txt"
if "%1"=="nopause" set NOPAUSE=1

echo Kitchen inventory - environment report > "%REPORT%"
echo ====================================== >> "%REPORT%"
echo. >> "%REPORT%"

echo [1/10] Date, time and time zone >> "%REPORT%"
date /t >> "%REPORT%" 2>&1 || echo [FAILED] date >> "%REPORT%"
time /t >> "%REPORT%" 2>&1 || echo [FAILED] time >> "%REPORT%"
tzutil /g >> "%REPORT%" 2>&1 || echo [FAILED] tzutil >> "%REPORT%"
echo NOTE: the OS clock may be wrong - the app uses an explicit business date. >> "%REPORT%"
echo. >> "%REPORT%"

echo [2/10] Windows version >> "%REPORT%"
ver >> "%REPORT%" 2>&1 || echo [FAILED] ver >> "%REPORT%"
echo. >> "%REPORT%"

echo [3/10] RAM >> "%REPORT%"
wmic ComputerSystem get TotalPhysicalMemory /value >> "%REPORT%" 2>&1 || echo [FAILED] wmic memory >> "%REPORT%"
echo. >> "%REPORT%"

echo [4/10] Free disk space >> "%REPORT%"
wmic LogicalDisk where DriveType=3 get DeviceID,FreeSpace,Size >> "%REPORT%" 2>&1 || echo [FAILED] wmic disk >> "%REPORT%"
echo. >> "%REPORT%"

echo [5/10] Portable Python >> "%REPORT%"
if exist "%APPDIR%runtime\python.exe" (echo FOUND: runtime\python.exe >> "%REPORT%") else (echo MISSING: runtime\python.exe - see runtime\README.txt >> "%REPORT%")
if exist "%APPDIR%runtime\python.exe" ("%APPDIR%runtime\python.exe" --version >> "%REPORT%" 2>&1 || echo [FAILED] python --version >> "%REPORT%")
if not exist "%APPDIR%runtime\python.exe" (where python >> "%REPORT%" 2>&1 || echo [NOTE] no system python on PATH >> "%REPORT%")
echo. >> "%REPORT%"

echo [6/10] check_imports.py >> "%REPORT%"
if exist "%APPDIR%runtime\python.exe" (if exist "%APPDIR%check_imports.py" ("%APPDIR%runtime\python.exe" "%APPDIR%check_imports.py" >> "%REPORT%" 2>&1 || echo [FAILED] check_imports with portable python >> "%REPORT%"))
if not exist "%APPDIR%runtime\python.exe" (if exist "%APPDIR%check_imports.py" (python "%APPDIR%check_imports.py" >> "%REPORT%" 2>&1 || echo [FAILED/NOTE] check_imports with system python >> "%REPORT%"))
if not exist "%APPDIR%check_imports.py" (echo MISSING: check_imports.py >> "%REPORT%")
echo. >> "%REPORT%"

echo [7/10] Browser search >> "%REPORT%"
if exist "%APPDIR%runtime\browser\firefox.exe" (echo FOUND: runtime\browser\firefox.exe >> "%REPORT%") else (echo MISSING: runtime\browser\firefox.exe >> "%REPORT%")
if exist "%ProgramFiles%\Mozilla Firefox\firefox.exe" (echo FOUND: system Firefox [%ProgramFiles%] >> "%REPORT%") else (echo MISSING: system Firefox [%ProgramFiles%] >> "%REPORT%")
if defined ProgramFiles(x86) (if exist "%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe" (echo FOUND: system Firefox [x86] >> "%REPORT%") else (echo MISSING: system Firefox [x86] >> "%REPORT%"))
echo. >> "%REPORT%"

echo [8/10] Screen resolution >> "%REPORT%"
wmic path Win32_VideoController get CurrentHorizontalResolution,CurrentVerticalResolution >> "%REPORT%" 2>&1 || echo [FAILED] wmic video >> "%REPORT%"
echo. >> "%REPORT%"

echo [9/10] Port 8001 (8000 belongs to the cafeteria POS) >> "%REPORT%"
netstat -ano | findstr :8001 >> "%REPORT%" 2>&1 || echo FREE-or-unknown: no line with :8001 in netstat >> "%REPORT%"
echo. >> "%REPORT%"

echo [10/10] Demo data >> "%REPORT%"
if exist "%APPDIR%data_demo\kitchen.db" (echo FOUND: data_demo\kitchen.db - training data, real data stays in data\ >> "%REPORT%") else (echo MISSING: data_demo\kitchen.db - run seed_demo.py on a PC with Python >> "%REPORT%")
if exist "%APPDIR%data\kitchen.db" (echo NOTE: data\kitchen.db exists - real database present >> "%REPORT%") else (echo NOTE: data\ is empty - first run shows the setup screen >> "%REPORT%")
echo. >> "%REPORT%"

echo Done. Report written to: >> "%REPORT%"
echo %REPORT% >> "%REPORT%"

type "%REPORT%"
echo.
if not defined NOPAUSE pause
exit /b 0
