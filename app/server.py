# server.py - HTTP plumbing and routing for the kitchen inventory app.
#
# Thin on purpose: socket, request lifecycle, safety checks, route table.
# Behaviour lives in routes_inventory.py (counts/prices/reports) and
# routes_system.py (heartbeat/shutdown). Calculations live in calc.py.
#
# Binds 127.0.0.1:8001 only (8000 belongs to the cafeteria POS).
# Usage:  python server.py [--data-dir DIR] [--parent-pid PID]
#
# Standard library only (Python 3.8). No external connections at runtime.

import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import db  # noqa: E402
import http_kit  # noqa: E402
import routes_inventory  # noqa: E402
import routes_system  # noqa: E402
import strings_ar  # noqa: E402
from http_kit import ApiError  # noqa: E402

S = strings_ar.STRINGS

HOST = "127.0.0.1"
PORT = 8001

ALLOWED_HOST_NAMES = ("127.0.0.1", "localhost", "[::1]")
MAX_BODY_BYTES = 64 * 1024

MATERIAL_ACTION_RE = re.compile(r"^/api/materials/(\d+)/(rename|set_active)$")
PRODUCT_ACTION_RE = re.compile(r"^/api/products/(\d+)/(rename|set_active)$")


class AppContext(object):
    """Shared services handed to every route."""

    def __init__(self, db_path=None, port=PORT):
        self.db_path = db_path or db.default_db_path()
        self.port = port
        self._shutdown_requested = False
        self._heartbeat_at = 0.0
        self._state_lock = threading.Lock()

    def connect(self):
        return db.connect(self.db_path)

    def allowed_hosts(self):
        allowed = set()
        for name in ALLOWED_HOST_NAMES:
            allowed.add(name)
            allowed.add("%s:%d" % (name, self.port))
        allowed.add("127.0.0.1:80")
        allowed.add("localhost:80")
        return allowed

    def request_shutdown(self):
        with self._state_lock:
            self._shutdown_requested = True

    def shutdown_requested(self):
        with self._state_lock:
            return self._shutdown_requested

    def note_heartbeat(self):
        with self._state_lock:
            self._heartbeat_at = time.time()

    def heartbeat_status(self):
        with self._state_lock:
            seen = self._heartbeat_at > 0.0
            idle = time.time() - self._heartbeat_at if seen else 0.0
        return seen, idle


class Router(object):
    def __init__(self):
        self.gets = {}
        self.posts = {}
        self.patterns = []  # (compiled regex, {action: handler}) for POST

    def get(self, path, handler):
        self.gets[path] = handler

    def post(self, path, handler):
        self.posts[path] = handler

    def post_actions(self, regex, handlers):
        """Register a /api/<entity>/<id>/<action> family. The regex must
        capture (id, action); the handler is called as
        handler(context, request, item_id=<id>)."""
        self.patterns.append((regex, handlers))

    def resolve(self, method, path):
        table = self.gets if method == "GET" else self.posts
        handler = table.get(path)
        if handler is not None:
            return handler, {}
        if method == "POST":
            for regex, handlers in self.patterns:
                match = regex.match(path)
                if match is None:
                    continue
                target = handlers.get(match.group(2))
                if target is None:
                    continue
                return target, {"item_id": int(match.group(1))}
        return None, None


def page_index(context, request):
    response = http_kit.serve_file("index.html")
    if response is None:
        raise ApiError(404, "not_found")
    return response


def build_router():
    router = Router()
    router.get("/", page_index)
    router.get("/api/session", routes_inventory.api_session)
    router.get("/api/strings", routes_inventory.api_strings)
    router.get("/api/users", routes_inventory.api_list_users)
    router.post("/api/users", routes_inventory.api_create_user)
    router.get("/api/settings", routes_inventory.api_get_settings)
    router.post("/api/settings", routes_inventory.api_put_settings)
    router.get("/api/materials", routes_inventory.api_list_materials)
    router.post("/api/materials", routes_inventory.api_create_material)
    router.post("/api/units", routes_inventory.api_add_unit)
    router.post("/api/costs", routes_inventory.api_add_cost)
    router.get("/api/products", routes_inventory.api_list_products)
    router.post("/api/products", routes_inventory.api_create_product)
    router.post("/api/prices", routes_inventory.api_add_price)
    router.post("/api/recipe", routes_inventory.api_add_recipe)
    router.get("/api/day", routes_inventory.api_day)
    router.post("/api/day/count", routes_inventory.api_set_count)
    router.post("/api/day/receipt", routes_inventory.api_add_receipt)
    router.post("/api/day/sale", routes_inventory.api_set_sale)
    router.post("/api/day/coffee-check", routes_inventory.api_coffee_check)
    router.post("/api/day/close", routes_inventory.api_close_day)
    router.post("/api/day/adjust", routes_inventory.api_adjust)
    router.get("/api/yield", routes_inventory.api_yield)
    router.get("/api/report", routes_inventory.api_range_report)
    router.get("/api/export.csv", routes_inventory.api_export_csv)
    router.post("/api/backup", routes_inventory.api_backup)
    router.get("/api/backups", routes_inventory.api_list_backups)
    router.get("/api/days", routes_inventory.api_days)
    router.post_actions(MATERIAL_ACTION_RE, {
        "rename": routes_inventory.api_rename_material,
        "set_active": routes_inventory.api_set_material_active,
    })
    router.post_actions(PRODUCT_ACTION_RE, {
        "rename": routes_inventory.api_rename_product,
        "set_active": routes_inventory.api_set_product_active,
    })
    router.post("/api/heartbeat", routes_system.api_heartbeat)
    router.post("/api/shutdown", routes_system.api_shutdown)
    router.get("/api/shutdown-status", routes_system.api_shutdown_status)
    return router


ROUTER = build_router()


class Handler(BaseHTTPRequestHandler):
    server_version = "KitchenInventory/1.0"
    protocol_version = "HTTP/1.1"

    context = None

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "body_too_large")
        return self.rfile.read(length)

    def _send(self, response):
        body = response.body or b""
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in response.headers:
            self.send_header(name, value)
        self.end_headers()
        if body and response.status != 204:
            self.wfile.write(body)

    def _host_allowed(self):
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return True
        return host in self.context.allowed_hosts()

    def _dispatch(self, method):
        if not self._host_allowed():
            self._send(http_kit.error_response(
                403, "bad_host",
                "Requests must use 127.0.0.1:%d or localhost:%d"
                % (self.context.port, self.context.port)))
            return
        try:
            body = self._read_body()
            request = http_kit.Request(
                method, self.path, self.headers, body, self.client_address)
            handler, kwargs = ROUTER.resolve(method, request.path)
            if handler is None:
                if method == "GET" and _is_asset(request.path):
                    response = http_kit.serve_file(request.path.lstrip("/"))
                    if response is None:
                        raise ApiError(404, "not_found")
                else:
                    raise ApiError(404, "not_found")
            else:
                response = handler(self.context, request, **kwargs)
            self._send(response)
        except ApiError as exc:
            self._send(http_kit.from_api_error(exc))
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            self.log_error("unhandled error on %s: %r", self.path, exc)
            self._send(http_kit.error_response(
                500, "server_error", S["error_generic"]))

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def log_message(self, fmt, *args):
        pass


def _is_asset(path):
    name = path.lstrip("/")
    if "/" in name or name.startswith("."):
        return False
    return name.endswith((".js", ".css", ".ico"))


# ---------------------------------------------------------------------------
# Watchdog: exit when the launcher process disappears.
# os.kill(pid, 0) KILLS on Windows - never use it as a probe. OpenProcess
# + GetExitCodeProcess via ctypes instead (no subprocess calls, so no
# console window can flash).
# ---------------------------------------------------------------------------

def _pid_alive(pid):
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
                ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                return bool(ok) and code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        else:
            os.kill(pid, 0)
            return True
    except OSError:
        return False


def start_parent_watchdog(parent_pid):
    def _watch():
        while True:
            time.sleep(2)
            if not _pid_alive(parent_pid):
                os._exit(0)
    t = threading.Thread(target=_watch, daemon=True)
    t.start()


def create_server(host=HOST, port=PORT, db_path=None):
    conn = db.init_db(db_path)
    conn.close()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    context = AppContext(db_path=db_path or db.default_db_path(),
                         port=server.server_address[1])
    server.RequestHandlerClass = type(
        "BoundHandler", (Handler,), {"context": context})
    return server, context


def parse_args(argv):
    data_dir = None
    parent_pid = None
    i = 0
    while i < len(argv):
        if argv[i] == "--data-dir" and i + 1 < len(argv):
            data_dir = argv[i + 1]
            i += 2
        elif argv[i] == "--parent-pid" and i + 1 < len(argv):
            try:
                parent_pid = int(argv[i + 1])
            except ValueError:
                parent_pid = None
            i += 2
        else:
            i += 1
    return data_dir, parent_pid


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    data_dir, parent_pid = parse_args(args)
    db_path = os.path.join(data_dir, db.DB_FILENAME) if data_dir else None
    server, context = create_server(db_path=db_path)
    # Backup on every app start (spec), best effort.
    try:
        db.backup_db(context.db_path)
    except Exception:
        pass
    if parent_pid is not None:
        start_parent_watchdog(parent_pid)
    print("Kitchen inventory running on http://%s:%d/" % (HOST, PORT))
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
