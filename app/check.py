# check.py - runtime self-check for the Windows 7 target PC.
#
# Verifies, in order:
#   1. Python itself starts (a missing UCRT on Win7 kills it before any
#      message can be printed - start.bat handles that case).
#   2. sqlite3 imports and works (needed by server.py).
#   3. The data/ folder can be created and is writable.
#
# Version policy: strict 3.8.x when started WITHOUT arguments (this is how
# start.bat runs it with the portable runtime -> the Win7 target must be
# 3.8). With the "dev" argument (system-Python fallback on the dev PC)
# a different version is only a warning, not an error.
#
# Exit code 0 = OK, 1 = failure. All output in English (console only).

import os
import sys

_CHECK_DIR = os.path.dirname(os.path.abspath(__file__))
if _CHECK_DIR not in sys.path:
    sys.path.insert(0, _CHECK_DIR)


def fail(msg):
    print("[CHECK-FAIL] " + msg)
    sys.exit(1)


def warn(msg):
    print("[CHECK-WARN] " + msg)


def ok(msg):
    print("[CHECK-OK] " + msg)


def main():
    dev_mode = len(sys.argv) > 1 and sys.argv[1] == "dev"

    ok("Python starts: " + sys.version)

    if sys.version_info[0] != 3 or sys.version_info[1] != 8:
        msg = (
            "Expected Python 3.8.x but found %d.%d.%d"
            % sys.version_info[:3]
        )
        if dev_mode:
            warn(msg + " - allowed in dev fallback mode")
        else:
            fail(
                msg
                + " - use runtime\\python.exe from the portable folder."
            )

    try:
        import sqlite3
    except ImportError as exc:
        fail("sqlite3 import failed: %r" % (exc,))
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT 1")
        conn.close()
    except Exception as exc:
        fail("sqlite3 failed a smoke query: %r" % exc)
    ok("sqlite3 works: " + sqlite3.sqlite_version)

    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base, "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
        probe = os.path.join(data_dir, ".write_test")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
    except Exception as exc:
        fail("data/ folder is not writable: %r" % exc)
    ok("data/ folder ready: " + data_dir)

    # 4. Browser search (informational only - never fails the check).
    #    Same order the launcher uses: Chrome -> Edge -> bundled Firefox.
    try:
        import launcher as _launcher

        def _show(label, path):
            if path:
                print("[CHECK-OK] browser %s: %s" % (label, path))
            else:
                print("[CHECK-NOTE] browser %s: missing" % label)

        _show("Chrome", _launcher.find_system_chrome())
        _show("Edge", _launcher.find_system_edge())
        _show("bundled Firefox (fallback)", _launcher.find_bundled_firefox())
        print("[CHECK-OK] " + _launcher.describe_pick())
    except Exception as exc:
        print("[CHECK-NOTE] browser listing unavailable: %r" % (exc,))

    ok("All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
