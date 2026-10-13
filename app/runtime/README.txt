PUT PORTABLE PYTHON 3.8 HERE
============================

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
     python310.zip is NOT in 3.8 - just copy all files as they are)
     directly INTO THIS folder, so that you end up with:

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
     ModuleNotFoundError even though db.py sits next to the script.

     This is ALREADY HANDLED in the code: db.py / seed.py / server.py /
     launcher.py / make_shortcut.py each add their own folder to sys.path
     before importing a sibling module. There is nothing you must edit.

     The alternative (also fine, if you ever prefer it) is to add the app
     folder to python38._pth - for example a line containing:  ..
     The sys.path approach was chosen because it keeps working even if the
     app folder is moved or the _pth file is replaced by a fresh download.

     To verify on the target PC, run:
         runtime\python.exe check_imports.py
     It prints [OK] / [FAIL] for every import and exit code 0 when all is
     well. Tested here with an isolated interpreter in both modes.

  4. Copy the whole app/ folder to a USB stick, then to the Windows 7 PC.

BROWSER (optional but recommended for the Win7 target):
  A portable browser can be bundled at app\runtime\browser\ (chrome.exe
  or firefox.exe). The launcher checks that folder FIRST, before any
  installed browser. If no usable browser is found anywhere, the launcher
  shows an Arabic message instead of falling back to Internet Explorer.

Windows 7 note: if python.exe fails to start with a DLL/api-ms-win-crt
error, the target PC needs the Microsoft updates KB2999226 (UCRT) and
KB2533623. start.bat prints this hint automatically on failure.

NOTE: sqlite3.dll and _sqlite3.pyd ARE included in the embeddable package,
so no extra steps are needed for the database.

DATABASE FILES (separate from the smoke test):
  app\data\cafeteria.db  - the real POS database (db.py + seed.py)
  app\data\test.db       - the old smoke-test database (server.py)
  Keep data/ when replacing app code; it is never overwritten.

