KITCHEN INVENTORY - PORTABLE RUNTIME FOLDER
===========================================

This folder must contain the Python 3.8 embeddable package (64-bit),
so the app runs on the Windows 7 target PC with NOTHING installed.

What to download (on any PC WITH internet, e.g. your dev machine):

  File:   python-3.8.10-embed-amd64.zip   (about 7.8 MB)
  Page:   https://www.python.org/downloads/release/python-3810/
          -> scroll to the bottom table "Files"
          -> row "Windows embeddable package (64-bit)"
  Direct link:
          https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip
  MD5:    3acb1d7d9bde5a79f840167b166bb633

Where to put it:

  1. Extract the ZIP file.
  2. Copy EVERYTHING it contains (python.exe, python38.dll, python38._pth,
     python38.zip, sqlite3.dll, _sqlite3.pyd, ... - just copy all files
     as they are) directly INTO THIS folder, so that you end up with:

         app\runtime\python.exe
         app\runtime\python38.dll
         app\runtime\python38._pth
         app\runtime\python38.zip
         app\runtime\sqlite3.dll
         app\runtime\_sqlite3.pyd
         ... (and the rest)

  Do NOT put it in a subfolder like app\runtime\python-3.8.10-embed-amd64\.
  The start.bat looks for app\runtime\python.exe exactly.

  3. IMPORTANT - ISOLATED MODE (python38._pth): the embeddable package
     runs Python in isolated mode, so the folder containing a script is
     NOT automatically on sys.path. "import db" would fail with
     ModuleNotFoundError even though db.py sits right next to the script.

     This is ALREADY HANDLED in the code: every app module (db.py,
     calc.py, server.py, launcher.py, seed_demo.py, routes_*.py,
     make_shortcut.py) adds its own folder to sys.path before importing
     a sibling module. There is nothing you must edit.

     The alternative (also fine, if you ever prefer it) is to add the app
     folder to python38._pth - for example a line containing just:  ..
     The sys.path approach was chosen because it keeps working even if
     the app folder is moved or the _pth file is replaced by a fresh
     download.

     To verify on the target PC, run:
         runtime\python.exe check_imports.py
     It prints [OK] / [FAIL] for every import and exit code 0 when all
     is well.

  4. Transfer to the target PC with a phone USB cable (MTP): copy the
     whole app/ folder to D:\ on the Windows 7 PC, then right-click the
     zip (if you transferred a zip) -> "Extract All" into D:\, so you
     end up with D:\app\start.bat. There is no USB stick step and no
     installer: double-click start.bat and the app opens on its own.

BROWSER (bundled, required for the kiosk):
  Portable Firefox ESR 115.42.0 lives EXTRACTED at app\runtime\browser\
  (firefox.exe next to distribution\policies.json). There is no Chrome
  involved: the launcher checks runtime\browser\ FIRST, then any system
  Firefox, and refuses to fall back to Internet Explorer - if no usable
  browser exists it shows an Arabic message instead. Keep the
  distribution\policies.json file where it is (it disables updates,
  telemetry and the first-run pages so the kiosk always opens clean).

Windows 7 note: if python.exe fails to start with a DLL/api-ms-win-crt
error, the target PC needs the Microsoft updates KB2999226 (UCRT) and
KB2533623. start.bat prints this hint automatically on failure.

NOTE: sqlite3.dll and _sqlite3.pyd ARE included in the embeddable package,
so no extra steps are needed for the database (SQLite 3.35.5).

DATABASE FILES:
  app\data\kitchen.db  - the REAL database, created on first run.
  The package ships data/ EMPTY and updates never overwrite it: to
  update, replace the app code files and keep the data/ folder as is.
  Training/demo history (if generated with seed_demo.py) lives in
  app\data_demo\ and is never part of the package.
