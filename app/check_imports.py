# check_imports.py - verifies that the app modules import correctly.
#
# WHY THIS EXISTS: the Python 3.8 embeddable package runs in ISOLATED mode
# (python38._pth). In that mode a script's own folder is NOT automatically on
# sys.path, so "import db" can fail with ModuleNotFoundError even though the
# file sits right next to the script. Each app module therefore adds its own
# folder to sys.path before importing its siblings.
#
# Run this on the target PC to confirm, using the portable runtime:
#     runtime\python.exe check_imports.py
#
# Exit code 0 = all imports fine, 1 = a problem.
# Standard library only, Python 3.8 compatible.

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)


def report(ok, label, extra=""):
    print("[%s] %s%s" % ("OK" if ok else "FAIL", label,
                         (" - " + extra) if extra else ""))
    return ok


def main():
    print("Interpreter    : " + sys.version.replace("\n", " "))
    print("Isolated mode  : %s" % bool(sys.flags.isolated))
    print("Script folder  : " + _APP_DIR)
    print("")

    all_ok = True

    all_ok &= report(_APP_DIR in sys.path, "app folder is on sys.path")

    try:
        import db
        all_ok &= report(True, "import db", "schema version %d"
                         % db.LATEST_VERSION)
        all_ok &= report(
            hasattr(db, "connect") and hasattr(db, "apply_migrations")
            and hasattr(db, "backup_db"),
            "db exposes connect(), apply_migrations() and backup_db()",
        )
    except ImportError as exc:
        all_ok &= report(False, "import db", str(exc))

    try:
        import calc
        all_ok &= report(True, "import calc",
                         "to_base_qty(0.5, 24) = %d"
                         % calc.to_base_qty(0.5, 24))
    except ImportError as exc:
        all_ok &= report(False, "import calc", str(exc))

    try:
        import routes_inventory  # noqa: F401
        import routes_system  # noqa: F401
        import server  # noqa: F401
        import seed_demo  # noqa: F401
        import launcher  # noqa: F401
        all_ok &= report(True, "import routes/server/seed/launcher")
    except ImportError as exc:
        all_ok &= report(False, "import routes/server/seed/launcher",
                         str(exc))

    try:
        import sqlite3
        all_ok &= report(True, "import sqlite3", sqlite3.sqlite_version)
    except ImportError as exc:
        all_ok &= report(False, "import sqlite3", str(exc))

    try:
        import db
        conn = db.connect(":memory:")
        db.apply_migrations(conn)
        names = db.table_names(conn)
        conn.close()
        ok = "materials" in names and "stock_counts" in names
        all_ok &= report(ok, "in-memory schema round trip",
                         "%d tables" % len(names))
    except Exception as exc:                      # noqa: BLE001 (diagnostic)
        all_ok &= report(False, "in-memory schema round trip", repr(exc))

    print("")
    if all_ok:
        print("All import checks passed.")
        return 0
    print("Some checks FAILED - see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
