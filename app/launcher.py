# launcher.py - desktop-like launcher for the kitchen inventory app.
#
# Orchestrates the whole app lifecycle so it behaves like a desktop program:
#   1. Single instance: if our server already runs, show an Arabic message,
#      re-open the page, and exit WITHOUT touching the running copy.
#   2. Start server.py as a hidden child process (no console window).
#   3. Find a browser: system Chrome first, then system Edge, then the
#      bundled Firefox in app/runtime/browser/ as a fallback (never IE).
#   4. Open the page in a normal WINDOWED app window (taskbar stays
#      visible, minimize/Alt+Tab keep working) - never fullscreen/kiosk.
#   5. When the browser window closes, stop the server and exit.
#
# Standard library only, Python 3.8. Also runs under pythonw.exe (no
# console): popups use ctypes MessageBoxW, logging goes to a file.

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

# When launched under pythonw (no console), stdout/stderr are None.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Make strings_ar importable no matter how we were started (double-click,
# start.bat, shortcut, embeddable runtime in isolated mode).
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from strings_ar import STRINGS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(BASE_DIR, "server.py")
LOG_PATH = os.path.join(BASE_DIR, "kitchen_launcher.log")

HOST = "127.0.0.1"
PORT = 8001
URL = "http://%s:%d/" % (HOST, PORT)

# Endpoint used to detect that OUR server is up. It MUST be reachable without
# a session: /api/numbers is manager-only since Task 2 and a probe against it
# returns 401, which used to make "server failed to start" appear every time
# (see docs/DECISIONS.md). /api/session is public and identifies the app.
PROBE_URL = "http://%s:%d/api/session" % (HOST, PORT)

# Keys that must be present in the probe response for it to count as ours, so
# an unrelated program that happens to answer on this port is not mistaken for
# our server.
PROBE_MARKERS = ("authenticated", "setup_required")

# Poll the port this many seconds before giving up on the server.
SERVER_START_TIMEOUT = 15.0

# A fatal browser message stays until the user clicks OK, but the launcher
# must never hang forever on an unattended machine: close it automatically
# after this many seconds and continue with cleanup.
BROWSER_ERROR_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def log(msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (stamp, msg))
    except OSError:
        pass


def message_box(text, title=None):
    """Arabic popup: MB_ICONINFORMATION | MB_SETFOREGROUND | MB_RTLREADING."""
    if title is None:
        title = STRINGS["app_title"]
    MB = 0x00000040 | 0x00010000 | 0x00100000
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, MB)
    except Exception:
        pass


def _notify(text):
    """Show a short informational popup WITHOUT blocking the launcher.

    A modal MessageBoxW waits for the user to click OK, so a hidden pythonw
    process would sit there forever if nobody did (observed: a stale launcher
    process stayed alive after its server had already exited). The user still
    gets the message - the launcher simply no longer depends on them
    dismissing it before it can exit.
    """
    thread = threading.Thread(target=message_box, args=(text,))
    thread.daemon = True
    thread.start()


# Flags for the fatal browser popup: MB_OK | MB_ICONERROR | MB_TOPMOST,
# plus MB_RTLREADING so the Arabic text reads right-to-left.
_MB_BROWSER_ERROR = 0x00000010 | 0x00040000 | 0x00100000


def message_box_blocking(text, title=None, timeout=BROWSER_ERROR_TIMEOUT):
    """Show a VISIBLE error popup that stays until the user clicks OK.

    Unlike _notify (fire-and-forget, killed by _hard_exit before anyone
    can read it), this blocks the caller so the message is really shown.
    To keep the hung-modal fix, it never blocks longer than `timeout`
    seconds: afterwards the popup is dismissed automatically and control
    returns, so cleanup always runs. Returns the MessageBox result, or
    None when it was auto-closed or could not be shown.
    """
    if title is None:
        title = STRINGS["app_title"]
    outcome = []

    def _show():
        try:
            result = ctypes.windll.user32.MessageBoxW(
                None, text, title, _MB_BROWSER_ERROR)
            outcome.append(result)
        except Exception:
            pass

    thread = threading.Thread(target=_show)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        _dismiss_messagebox(title)
        thread.join(5)
    return outcome[0] if outcome else None


def _dismiss_messagebox(title):
    """Best-effort auto-close of the blocking popup (60s fallback)."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    except Exception:
        pass


def _hard_exit(code=0):
    """Exit immediately, even if a popup thread is still up."""
    os._exit(code)


def probe_port():
    """Return True (our server), False (free), None (unknown occupant)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((HOST, PORT))
    except (socket.error, OSError):
        return False
    finally:
        sock.close()
    # Something answers - is it our server? Ask a PUBLIC endpoint (see
    # PROBE_URL) and require our identifying keys in the JSON body.
    try:
        with urllib.request.urlopen(PROBE_URL, timeout=2) as resp:
            if resp.status != 200:
                return None
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(body, dict) and all(
        key in body for key in PROBE_MARKERS
    ):
        return True
    return None


def open_url_default_browser(url):
    """Open url in the default browser. Win7-safe (os.startfile)."""
    os.startfile(url)


# ---------------------------------------------------------------------------
# Browser discovery: system Chrome -> system Edge -> bundled Firefox.
# Everything opens WINDOWED (taskbar visible, minimize/Alt+Tab work).
# Fullscreen/kiosk is deliberately never used: on the target PC it locks
# the operator out of the taskbar until the app is closed completely.
# ---------------------------------------------------------------------------

# Exact install paths, in priority order.
CHROME_PATHS = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
)
EDGE_PATHS = (
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
)

# Optional override for testing: KITCHEN_BROWSER=chrome|edge|firefox.
FORCED_BROWSER_ENV = "KITCHEN_BROWSER"


def _app_paths_exe(name):
    """Install path from the App Paths registry key, or None.

    HKLM first, then HKCU. stdlib winreg only; never raises.
    """
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(
                root,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s"
                % name,
            ) as key:
                value, _kind = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        if value and os.path.isfile(value):
            return value
    return None


def _first_existing(paths):
    """First path that exists on disk, with %VAR% expanded, or None."""
    for template in paths:
        expanded = os.path.expandvars(template)
        if expanded and os.path.isfile(expanded):
            return expanded
    return None


def find_system_chrome():
    """System Chrome exe path, or None. Exact paths, then App Paths."""
    found = _first_existing(CHROME_PATHS)
    if found:
        return found
    found = _app_paths_exe("chrome.exe")
    if found:
        return found
    return shutil.which("chrome.exe")


def find_system_edge():
    """System Edge exe path, or None. Exact paths, then PATH lookup."""
    found = _first_existing(EDGE_PATHS)
    if found:
        return found
    return shutil.which("msedge.exe")


def find_bundled_firefox():
    """Bundled portable Firefox exe path, or None (fallback only)."""
    path = os.path.join(BASE_DIR, "runtime", "browser", "firefox.exe")
    if os.path.isfile(path):
        return path
    return None


def bundled_browser_dir():
    return os.path.join(BASE_DIR, "runtime", "browser")


def resolve_browser(log_it=True):
    """Pick the browser: system Chrome -> Edge -> bundled Firefox.

    Returns (kind, path, source) with kind in chrome/edge/firefox.
    KITCHEN_BROWSER=chrome|edge|firefox forces one browser (testing);
    a forced browser that is missing is a fatal error, never a silent
    fallback. Raises RuntimeError with an Arabic message when nothing
    usable is found.
    """
    forced = os.environ.get(FORCED_BROWSER_ENV, "").strip().lower()
    if forced in ("chrome", "edge", "firefox"):
        if log_it:
            log("browser: forced by %s=%s" % (FORCED_BROWSER_ENV, forced))
        if forced == "chrome":
            path = find_system_chrome()
        elif forced == "edge":
            path = find_system_edge()
        else:
            path = find_bundled_firefox()
        if not path:
            raise RuntimeError(STRINGS["no_browser"])
        return forced, path, "env:" + forced
    path = find_system_chrome()
    if path:
        return "chrome", path, "system:chrome"
    path = find_system_edge()
    if path:
        return "edge", path, "system:edge"
    path = find_bundled_firefox()
    if path:
        return "firefox", path, "bundled:firefox"
    if os.path.isdir(bundled_browser_dir()):
        raise RuntimeError(STRINGS["bundled_browser_missing"])
    raise RuntimeError(STRINGS["no_browser"])


def describe_pick():
    """One-line summary for RUN_CHECK.bat: what the launcher would pick.

    Never raises, never writes to the launcher log.
    """
    try:
        kind, path, source = resolve_browser(log_it=False)
    except RuntimeError as exc:
        return "launcher would pick: NONE (%s)" % exc
    except Exception as exc:                # noqa: BLE001 - diagnostics
        return "launcher would pick: UNKNOWN (%r)" % (exc,)
    return "launcher would pick: %s [%s] %s" % (kind, path, source)


def launch_browser():
    """Open the app page in a normal windowed app window.

    The taskbar stays visible; minimize, maximize, close and Alt+Tab all
    keep working, so the operator is never locked in. Returns
    (proc, profile_dir, kind); profile_dir is the fresh per-launch profile
    (close-detection for Firefox runs through it). Raises RuntimeError
    with an Arabic message when no suitable browser exists.
    """
    kind, path, source = resolve_browser()
    log("browser: %s -> %s [%s]" % (kind, path, source))
    proc, profile_dir = _spawn(kind, path)
    return proc, profile_dir, kind


def _browser_profile_dir():
    """A FRESH profile directory for this launch, in %TEMP%.

    Why fresh instead of one fixed path: a Chrome/Edge profile that was
    killed mid-write (crash, power cut, Task Manager) can become corrupt, and
    the browser then exits IMMEDIATELY - so the app opened and instantly
    closed, with the server torn down right after. Using a new directory per
    launch makes that state impossible to hit, and the previous ones are
    swept away so %TEMP% does not grow without bound.

    The dedicated directory also matters for close-detection: without it a
    running browser would absorb the new process and "browser closed" would
    fire at the wrong time.
    """
    temp_root = tempfile.gettempdir()
    _sweep_old_profiles(temp_root)
    return os.path.join(
        temp_root, "kitchen_inventory_browser_%d_%d" % (os.getpid(), int(time.time()))
    )


def _sweep_old_profiles(temp_root, keep=3):
    """Delete leftover per-launch profile directories (best effort).

    A directory still locked by a running browser is skipped silently.
    """
    try:
        entries = [
            os.path.join(temp_root, name)
            for name in os.listdir(temp_root)
            if name.startswith("kitchen_inventory_browser_")
            or name == "kitchen_smoketest_browser_profile"
        ]
    except OSError:
        return
    entries.sort(key=lambda path: os.path.getmtime(path)
                 if os.path.exists(path) else 0)
    for path in entries[:-keep] if len(entries) > keep else []:
        try:
            shutil.rmtree(path)
        except OSError:
            pass                      # locked by a live browser - fine


def chrome_args(exe_path, profile_dir):
    """Windowed --app command line for Chrome/Edge. Never --kiosk, never
    fullscreen: the window keeps normal title-bar controls and the taskbar
    stays visible. A fresh --user-data-dir per launch is mandatory, or the
    new process hands off to an already-running Chrome and exits at once.
    """
    return [
        exe_path,
        "--app=" + URL,
        "--user-data-dir=" + profile_dir,
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-features=Translate",
        "--window-position=0,0",
        "--window-size=1280,680",
    ]


def firefox_args(exe_path, profile_dir):
    """Windowed fallback command line for the bundled Firefox ESR.

    Plain window (--new-window on a fresh -profile, taskbar visible).
    Never --kiosk. -wait-for-browser keeps the first process usable for
    terminate(); lifetime detection still uses the profile lock below.
    """
    return [
        exe_path,
        "-wait-for-browser",
        "-profile",
        profile_dir,
        "--new-window",
        URL,
        "-no-remote",
    ]


def _spawn(kind, exe_path):
    """Start the browser windowed and return (Popen, profile_dir).

    The exact command line is logged (localhost URL + temp profile only,
    no secrets). Returns (Popen, profile_dir): the profile dir identifies
    the real browser process (see FirefoxWatcher), because Firefox's first
    process exits at once while the real window keeps running.
    """
    profile_dir = _browser_profile_dir()
    if kind in ("chrome", "edge"):
        args = chrome_args(exe_path, profile_dir)
    else:  # firefox
        args = firefox_args(exe_path, profile_dir)
    log("browser command: " + " ".join('"%s"' % a for a in args))
    return subprocess.Popen(args), profile_dir


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def start_server_hidden():
    """Run server.py hidden; wait until it answers on the port.

    start_demo.bat sets KITCHEN_DATA_DIR=data_demo so the demo runs on
    fake data; start.bat leaves it unset so the real data/ is used.
    """
    exe = python_exe()
    if exe is None:
        raise RuntimeError(STRINGS["server_failed"])
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    args = [exe, SERVER_SCRIPT, "--parent-pid", str(os.getpid())]
    data_dir = os.environ.get("KITCHEN_DATA_DIR")
    if data_dir:
        args += ["--data-dir", data_dir]
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        cwd=BASE_DIR,
    )
    deadline = time.time() + SERVER_START_TIMEOUT
    while time.time() < deadline:
        if probe_port() is True:
            return proc
        if proc.poll() is not None:
            break  # server died during startup
        time.sleep(0.3)
    proc.kill()
    raise RuntimeError(STRINGS["server_failed"])


def python_exe():
    """Interpreter that can run server.py (portable runtime preferred)."""
    runtime_dir = os.path.join(BASE_DIR, "runtime")
    for name in ("pythonw.exe", "python.exe"):
        p = os.path.join(runtime_dir, name)
        if os.path.isfile(p):
            return p
    for name in ("pythonw.exe", "python.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def browser_search_summary():
    """One-line summary of the browser search, for launcher.log."""
    try:
        chrome = find_system_chrome()
    except Exception as exc:
        chrome = "search failed: %r" % (exc,)
    try:
        edge = find_system_edge()
    except Exception as exc:
        edge = "search failed: %r" % (exc,)
    try:
        firefox = find_bundled_firefox()
    except Exception as exc:
        firefox = "search failed: %r" % (exc,)
    return "chrome=%s edge=%s bundled_firefox=%s forced=%s" % (
        chrome or "none", edge or "none", firefox or "none",
        os.environ.get(FORCED_BROWSER_ENV, "").strip() or "none")


def browser_fatal(server_proc, message):
    """No usable browser (or it failed to start): tell the user, then stop.

    Shows a VISIBLE modal error (stays until OK, 60s auto-close fallback
    so the launcher never hangs), THEN stops the server we just started
    and exits 1. The reason is always logged first so it can be read
    later from launcher.log.
    """
    log("browser search: " + browser_search_summary())
    log("browser fatal: " + message.replace("\n", " | "))
    message_box_blocking(message)
    try:
        server_proc.terminate()
    except OSError:
        pass
    try:
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            server_proc.kill()
        except OSError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline and probe_port() is not False:
        time.sleep(0.2)
    log("launcher exit (no browser)")
    _hard_exit(1)


# ---------------------------------------------------------------------------
# Browser lifetime: process handle for Chrome/Edge, profile lock for
# Firefox - never wmic/taskkill/subprocess polling (a hidden pythonw
# spawning those flashes a console window on every poll).
# ---------------------------------------------------------------------------
# Chrome/Edge are started with a FRESH --user-data-dir per launch, so the
# new process cannot hand off to an already-running Chrome and exit at
# once: the PID we started stays the browser's main process until its
# last window closes. Close is therefore detected straight from that
# process handle (Popen.poll() plus an OpenProcess/GetExitCodeProcess
# probe via ctypes - os.kill(pid, 0) would TERMINATE on Windows and is
# never used as a probe here).
#
# Firefox on Windows starts through a launcher process: the first
# firefox.exe exits at once (rc 0 after ~0.3 s, verified) while the real
# window keeps running. Waiting on the Popen handle therefore stops the
# server while the window is still open.
#
# Lifetime comes from the profile lock instead, with zero subprocess
# calls: Firefox holds an exclusive lock on
# <profile>/parent.lock while it runs. Verified live with Firefox 115:
# absent before launch, locked within ~1 s of window open, released on
# close. -wait-for-browser (verified present in 115) additionally keeps
# the Popen handle usable, so closing also needs no taskkill.
#
# Only the profile's leaf name is used for nothing here at all - the
# lock is checked by direct file path, so DOS 8.3 short names are not
# even a concern.

# Grace for slow starts: give the lock file this long to appear before
# "no lock" counts as closed.
FIREFOX_FIRST_SEEN_GRACE = 20.0

# Page heartbeat: every inventory page pings the server this often, and
# the launcher gives up this long after the last ping was seen (only
# once at least one ping arrived - a fresh page may take a while).
HEARTBEAT_INTERVAL = 10.0
HEARTBEAT_TIMEOUT = 60.0

# How often the browser-wait loop polls (shutdown flag, heartbeat, alive).
BROWSER_POLL_SECONDS = 2.0


def profile_lock_state(profile_dir):
    """(exists, locked) for the Firefox profile lock.

    locked=True means another process holds parent.lock open right now
    (the browser window is up). No subprocess calls: a plain file open,
    so nothing can flash a console. Never raises.
    """
    try:
        path = os.path.join(profile_dir, "parent.lock")
        if not os.path.exists(path):
            return False, False
        try:
            handle = open(path, "r+b")
        except OSError:
            return True, True
        try:
            handle.close()
        except OSError:
            pass
        return True, False
    except Exception:
        return False, False


def _pid_alive(pid):
    """True while the given PID is still running. Windows-safe liveness
    probe: OpenProcess + GetExitCodeProcess via ctypes. NOTE: os.kill(pid,
    0) on Windows TERMINATES the process (only CTRL_C/CTRL_BREAK are
    special-cased), so it must never be used as a probe. No subprocess
    calls, so no console window can flash. Never raises.
    """
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                ok = kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(code))
                return bool(ok) and code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        else:
            os.kill(pid, 0)
            return True
    except OSError:
        return False


def _process_alive(proc):
    """True while our started browser process still runs.

    Popen.poll() checks the already-open process handle (no new process,
    no flashing console); the ctypes OpenProcess probe backs it up.
    """
    try:
        if proc.poll() is not None:
            return False
    except OSError:
        return False
    try:
        return _pid_alive(proc.pid)
    except Exception:
        return False


class FirefoxWatcher(object):
    """True while the real Firefox window for this launch is open."""

    def __init__(self, profile_dir, grace=FIREFOX_FIRST_SEEN_GRACE):
        self.profile_dir = profile_dir
        self.deadline = time.time() + grace

    def alive(self):
        exists, locked = profile_lock_state(self.profile_dir)
        if locked:
            return True
        if not exists:
            # Starting: the lock file itself takes ~1 s to appear.
            return time.time() < self.deadline
        # Lock file present but not held: closed (or crashed, which is
        # equally "no live window").
        return False


def close_browser(browser_proc, profile_dir, kind):
    """Best-effort close of the app window (quit/heartbeat paths).

    Firefox: terminate() on the Popen handle works because
    -wait-for-browser keeps the first process alive with the window
    (verified live). No taskkill/wmic calls, so no console can flash.
    """
    if browser_proc is None:
        return
    try:
        browser_proc.terminate()
    except OSError:
        pass


def fetch_launcher_status(timeout=3):
    """Server-side quit/heartbeat flags for the launcher loop."""
    url = "http://%s:%d/api/shutdown-status" % (HOST, PORT)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stop_server_proc(server_proc):
    """Terminate the server and wait until the port is free."""
    try:
        server_proc.terminate()
    except OSError:
        pass
    try:
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            server_proc.kill()
        except OSError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline and probe_port() is not False:
        time.sleep(0.2)


def heartbeat_expired(status):
    """Pure decision: no ping for HEARTBEAT_TIMEOUT after pings began."""
    if not isinstance(status, dict):
        return False
    if status.get("shutdown_requested"):
        return False
    if not status.get("heartbeat_seen"):
        return False
    idle = status.get("heartbeat_idle_seconds") or 0
    return idle > HEARTBEAT_TIMEOUT


def wait_for_browser_exit(browser_proc, profile_dir, kind, server_proc):
    """Block until the window closes, quit is requested, or pings stop.

    Never returns on the quit/heartbeat paths (stops everything, exits).
    Returns "closed" when the user closed the window themselves.
    """
    watcher = None
    if kind == "firefox" and profile_dir:
        watcher = FirefoxWatcher(profile_dir, FIREFOX_FIRST_SEEN_GRACE)
    while True:
        try:
            status = fetch_launcher_status()
        except Exception:
            status = None
        if isinstance(status, dict):
            if status.get("shutdown_requested"):
                log("shutdown requested from UI - closing browser")
                close_browser(browser_proc, profile_dir, kind)
                stop_server_proc(server_proc)
                log("launcher exit (quit from UI)")
                _hard_exit(0)
            if heartbeat_expired(status):
                idle = int(status.get("heartbeat_idle_seconds") or 0)
                log("no page heartbeat for %ds - closing browser" % idle)
                close_browser(browser_proc, profile_dir, kind)
                stop_server_proc(server_proc)
                log("launcher exit (heartbeat timeout)")
                _hard_exit(0)
        if kind in ("chrome", "edge"):
            # Fresh --user-data-dir per launch means this PID is the real
            # browser process: when it is gone, the window is closed.
            if browser_proc is not None and not _process_alive(browser_proc):
                return "closed"
        elif watcher is not None:
            if not watcher.alive():
                return "closed"
        else:
            return "closed"
        time.sleep(BROWSER_POLL_SECONDS)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def main():
    log("launcher start (pid %d)" % os.getpid())

    # --- Single instance --------------------------------------------------
    state = probe_port()
    if state is True:
        # Our server is already running: re-open the page and leave the
        # running copy completely alone.
        log("already running - reopening page")
        _notify(STRINGS["already_running"])
        try:
            open_url_default_browser(URL)
        except OSError:
            pass
        _hard_exit()
    if state is None:
        # Port busy, but it is NOT our server: do not touch anything.
        log("port %d busy by unknown program" % PORT)
        _notify(STRINGS["port_busy"])
        _hard_exit()

    # --- Start the server hidden -------------------------------------------
    try:
        server_proc = start_server_hidden()
    except RuntimeError as exc:
        log("server failed to start")
        _notify(str(exc))
        _hard_exit(1)
    log("server started (pid %d)" % server_proc.pid)

    # --- Open the browser ----------------------------------------------------
    used_default_fallback = False
    browser_proc, profile_dir, kind = None, None, None
    try:
        browser_proc, profile_dir, kind = launch_browser()
    except RuntimeError as exc:
        # No suitable browser: visible error, then stop the server & exit.
        browser_fatal(server_proc, str(exc))
    except OSError as exc:
        # The browser executable failed to start (missing DLL, broken
        # portable copy, ...): same visible handling, Arabic text only.
        log("browser failed to start: %r" % (exc,))
        bundled_dir = os.path.join(BASE_DIR, "runtime", "browser")
        if os.path.isdir(bundled_dir):
            browser_fatal(server_proc, STRINGS["bundled_browser_missing"])
        else:
            browser_fatal(server_proc, STRINGS["no_browser"])
    if browser_proc is None:
        used_default_fallback = True
        log("default-browser fallback: no close detection")

    # --- Wait for the browser window to close --------------------------------
    # Chrome/Edge lifetime comes from the started process handle (fresh
    # profile per launch, so no handoff); Firefox lifetime comes from
    # profile-dir polling (its first process exits at once). The loop also
    # honors the UI quit action and the page heartbeat (both stop
    # everything and exit from inside the loop).
    try:
        if browser_proc is not None:
            wait_for_browser_exit(browser_proc, profile_dir, kind,
                                  server_proc)
    except KeyboardInterrupt:
        pass

    # --- Cleanup: stop the server --------------------------------------------
    log("browser closed - stopping server (pid %d)" % server_proc.pid)
    try:
        server_proc.terminate()
    except OSError:
        pass
    try:
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_proc.kill()

    # Make sure the server is really gone before we exit, so the next launch
    # finds a free port.
    deadline = time.time() + 5
    while time.time() < deadline and probe_port() is not False:
        time.sleep(0.2)

    log("launcher exit")
    # Hard exit: a hidden pythonw process must never risk lingering during
    # interpreter shutdown. Nothing is left to flush - log() writes and closes
    # its file on every call.
    _hard_exit(0)


if __name__ == "__main__":
    main()
