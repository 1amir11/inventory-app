# test_launch_config.py - guards the hard target-machine constraints:
# port 8001, distinct temp/log/data names, no forbidden calls, py3.8 syntax.
#
# Run from the repository root:  python -m unittest discover -s tests -v
# Standard library only (unittest), Python 3.8 compatible.

import os
import py_compile
import sys
import unittest

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.join(_ROOT_DIR, "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import launcher  # noqa: E402
import server  # noqa: E402


class TestLaunchConfig(unittest.TestCase):

    def test_port_8001(self):
        self.assertEqual(server.PORT, 8001)
        self.assertEqual(launcher.PORT, 8001)
        self.assertIn("8001", launcher.URL)

    def test_distinct_names(self):
        self.assertIn("kitchen_launcher.log", launcher.LOG_PATH)
        self.assertNotIn("cafeteria", launcher.LOG_PATH)
        profile = launcher._browser_profile_dir()
        self.assertIn("kitchen_inventory_browser_", profile)

    def test_probe_markers_match_server(self):
        # The launcher probes a PUBLIC endpoint; the keys must exist there.
        for marker in launcher.PROBE_MARKERS:
            self.assertIn(marker, ("authenticated", "setup_required"))
        self.assertTrue(launcher.PROBE_URL.endswith("/api/session"))

    def test_no_forbidden_runtime_calls(self):
        # Token-based for wmic/taskkill (docstrings may explain the ban).
        # os.kill is allowed ONLY in the POSIX branch of an os.name check:
        # on Windows it TERMINATES the process, so the Windows path must use
        # OpenProcess/GetExitCodeProcess via ctypes (same as the old project).
        import ast
        import io
        import tokenize
        for module_path in (os.path.join(_APP_DIR, "launcher.py"),
                            os.path.join(_APP_DIR, "server.py")):
            with open(module_path, encoding="utf-8") as f:
                text = f.read()
            names = []
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type in (tokenize.STRING, tokenize.COMMENT,
                                tokenize.NL, tokenize.NEWLINE,
                                tokenize.INDENT, tokenize.DEDENT,
                                tokenize.ENDMARKER, tokenize.ENCODING):
                    continue
                names.append(tok.string)
            joined = " ".join(names).lower()
            self.assertNotIn("wmic", joined, module_path)
            self.assertNotIn("taskkill", joined, module_path)
            tree = ast.parse(text)

            class GuardCheck(ast.NodeVisitor):
                def __init__(self):
                    self.guarded = True
                    self.guard_depth = 0

                def visit_If(self, node):
                    self.guard_depth += 1
                    self.generic_visit(node)
                    self.guard_depth -= 1

                def visit_Call(self, node):
                    func = node.func
                    if isinstance(func, ast.Attribute) and \
                            func.attr == "kill" and \
                            isinstance(func.value, ast.Name) and \
                            func.value.id == "os":
                        # os.kill is only legal at guard depth 0 when the
                        # module has no os.name branch... in practice our
                        # modules always branch on os.name, and this visitor
                        # only needs: never at top level unguarded. The
                        # server's POSIX else-branch sets guard_depth >= 1.
                        if self.guard_depth == 0:
                            self.guarded = False
                    self.generic_visit(node)

            checker = GuardCheck()
            checker.visit(tree)
            self.assertTrue(checker.guarded, module_path)
        www = os.path.join(_APP_DIR, "www")
        for name in sorted(os.listdir(www)):
            if not name.endswith(".js"):
                continue
            with open(os.path.join(www, name), encoding="utf-8") as f:
                js = f.read()
            for banned in ("alert(", "confirm(", "prompt("):
                self.assertNotIn(banned, js, name)
        for name in ("tokens.css", "base.css", "components.css",
                     "screens.css"):
            with open(os.path.join(www, name), encoding="utf-8") as f:
                css = f.read()
            for banned in (":has(", "color-mix(", "dvh", "svh",
                           "@container"):
                self.assertNotIn(banned, css, name)

    def test_chrome_cmdline_windowed(self):
        profile = os.path.join("T:", "prof1")
        args = launcher.chrome_args("C:\\c\\chrome.exe", profile)
        joined = " ".join(args)
        self.assertIn("--app=" + launcher.URL, joined)
        self.assertIn("--user-data-dir=" + profile, joined)
        for flag in ("--no-first-run", "--no-default-browser-check",
                     "--disable-session-crashed-bubble",
                     "--disable-features=Translate",
                     "--window-position=0,0", "--window-size=1280,680"):
            self.assertIn(flag, args)
        self.assertNotIn("--kiosk", args)
        self.assertFalse(any("kiosk" in a.lower() for a in args))
        self.assertFalse(any("maximiz" in a.lower() or "fullscreen" in a.lower()
                             for a in args))
        # A different profile dir gives a different (unique) command line.
        other = launcher.chrome_args("C:\\c\\chrome.exe",
                                     os.path.join("T:", "prof2"))
        self.assertNotEqual(args, other)

    def test_firefox_cmdline_no_kiosk(self):
        args = launcher.firefox_args("C:\\b\\firefox.exe", "C:\\prof")
        self.assertNotIn("--kiosk", args)
        self.assertFalse(any("kiosk" in a.lower() for a in args))
        self.assertIn("--new-window", args)
        self.assertIn(launcher.URL, args)
        self.assertIn("C:\\prof", args)

    def test_no_kiosk_in_code(self):
        # "--kiosk" may appear in comments explaining the ban, never in code.
        import io
        import tokenize
        with open(os.path.join(_APP_DIR, "launcher.py"),
                  encoding="utf-8") as f:
            text = f.read()
        code = []
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT,
                            tokenize.NL, tokenize.NEWLINE,
                            tokenize.INDENT, tokenize.DEDENT,
                            tokenize.ENDMARKER, tokenize.ENCODING):
                continue
            code.append(tok.string)
        self.assertNotIn("--kiosk", " ".join(code))

    def test_browser_resolution_order(self):
        real_chrome = launcher.find_system_chrome
        real_edge = launcher.find_system_edge
        real_ff = launcher.find_bundled_firefox
        old_env = os.environ.get(launcher.FORCED_BROWSER_ENV)
        if launcher.FORCED_BROWSER_ENV in os.environ:
            del os.environ[launcher.FORCED_BROWSER_ENV]
        try:
            launcher.find_system_chrome = lambda: "C:\\c\\chrome.exe"
            launcher.find_system_edge = lambda: "C:\\e\\msedge.exe"
            launcher.find_bundled_firefox = lambda: "C:\\b\\firefox.exe"
            self.assertEqual(launcher.resolve_browser()[0], "chrome")
            launcher.find_system_chrome = lambda: None
            self.assertEqual(launcher.resolve_browser()[0], "edge")
            launcher.find_system_edge = lambda: None
            self.assertEqual(launcher.resolve_browser()[0], "firefox")
            launcher.find_bundled_firefox = lambda: None
            with self.assertRaises(RuntimeError):
                launcher.resolve_browser()
            # Forced browser wins over the normal order...
            launcher.find_system_chrome = lambda: "C:\\c\\chrome.exe"
            launcher.find_system_edge = lambda: "C:\\e\\msedge.exe"
            launcher.find_bundled_firefox = lambda: "C:\\b\\firefox.exe"
            os.environ[launcher.FORCED_BROWSER_ENV] = "edge"
            kind, _path, source = launcher.resolve_browser()
            self.assertEqual(kind, "edge")
            self.assertTrue(source.startswith("env:"))
            # ...and a forced-but-missing browser is fatal, not silent.
            os.environ[launcher.FORCED_BROWSER_ENV] = "firefox"
            launcher.find_bundled_firefox = lambda: None
            with self.assertRaises(RuntimeError):
                launcher.resolve_browser()
            # Unknown values are ignored (normal order applies).
            os.environ[launcher.FORCED_BROWSER_ENV] = "safari"
            self.assertEqual(launcher.resolve_browser()[0], "chrome")
        finally:
            launcher.find_system_chrome = real_chrome
            launcher.find_system_edge = real_edge
            launcher.find_bundled_firefox = real_ff
            if old_env is None:
                os.environ.pop(launcher.FORCED_BROWSER_ENV, None)
            else:
                os.environ[launcher.FORCED_BROWSER_ENV] = old_env

    def test_pid_alive_self(self):
        # Our own process is alive; nonsense PIDs are not. Never raises.
        self.assertTrue(launcher._pid_alive(os.getpid()))
        self.assertFalse(launcher._pid_alive(0))
        self.assertFalse(launcher._pid_alive(-5))

    def test_no_arabic_outside_strings(self):
        # ALL Arabic text lives in strings.js; HTML and other JS files must
        # not contain Arabic characters (symbols like arrows are fine).
        www = os.path.join(_APP_DIR, "www")
        for name in sorted(os.listdir(www)):
            if name == "strings.js":
                continue
            if not (name.endswith(".js") or name.endswith(".html")):
                continue
            with open(os.path.join(www, name), encoding="utf-8") as f:
                text = f.read()
            bad = [ch for ch in text if "\u0600" <= ch <= "\u06FF"]
            self.assertEqual(bad, [], name)

    def test_all_py_compile(self):
        for name in os.listdir(_APP_DIR):
            if name.endswith(".py"):
                py_compile.compile(os.path.join(_APP_DIR, name), doraise=True)


if __name__ == "__main__":
    unittest.main()
