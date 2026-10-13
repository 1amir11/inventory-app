# http_kit.py - small HTTP request/response helpers shared by the route
# modules. Keeps server.py thin and stops route modules importing server.py
# (which would be a circular import).
#
# Standard library only, Python 3.8 compatible.

import json
import mimetypes
import os
import sys
import urllib.parse

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

WWW_DIR = os.path.join(_APP_DIR, "www")

# Content types must include charset=utf-8 so Arabic renders correctly.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
}

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


class ApiError(Exception):
    """Raised by a route to send a JSON error response.

    code is both the HTTP status and the machine-readable payload key.
    """

    def __init__(self, status, error, message=None, extra=None):
        Exception.__init__(self, error)
        self.status = status
        self.error = error
        self.message = message
        self.extra = extra or {}

    def payload(self):
        data = {"error": self.error}
        if self.message:
            data["message"] = self.message
        data.update(self.extra)
        return data


class Request(object):
    """Everything a route needs to know about one HTTP request."""

    def __init__(self, method, raw_path, headers, body, client_address):
        self.method = method
        self.raw_path = raw_path
        self.headers = headers                      # email.message.Message
        self.body = body or b""
        self.client_address = client_address
        parsed = urllib.parse.urlsplit(raw_path)
        self.path = urllib.parse.unquote(parsed.path)
        self.query = dict(urllib.parse.parse_qsl(parsed.query))
        self.cookies = parse_cookies(self.headers.get("Cookie"))
        self._json = None
        self._json_parsed = False

    # -- headers ---------------------------------------------------------

    @property
    def host(self):
        return (self.headers.get("Host") or "").strip()

    @property
    def content_type(self):
        return (self.headers.get("Content-Type") or "").strip()

    def is_json_content_type(self):
        """True when the body Content-Type is application/json (with any
        charset parameter)."""
        base = self.content_type.split(";")[0].strip().lower()
        return base == "application/json"

    # -- body ------------------------------------------------------------

    def json(self):
        """Parse the body as JSON. Raises ApiError(400) when not valid.

        Requires Content-Type: application/json - the caller must check
        that first with is_json_content_type().
        """
        if self._json_parsed:
            if self._json is None:
                raise ApiError(400, "invalid_json")
            return self._json
        self._json_parsed = True
        try:
            text = self.body.decode("utf-8")
            value = json.loads(text) if text.strip() else {}
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "invalid_json")
        if not isinstance(value, dict):
            raise ApiError(400, "invalid_json")
        self._json = value
        return value

    def get_cookie(self, name):
        return self.cookies.get(name)


class Response(object):
    """A finished HTTP response."""

    def __init__(self, status=200, body=b"", content_type=None, headers=None):
        self.status = status
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.body = body
        self.content_type = content_type or "text/plain; charset=utf-8"
        self.headers = list(headers or [])

    def add_header(self, name, value):
        self.headers.append((name, value))
        return self


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def json_response(payload, status=200, headers=None):
    body = json.dumps(payload, ensure_ascii=False)
    return Response(status, body, JSON_CONTENT_TYPE, headers)


def error_response(status, code, message=None, extra=None):
    payload = {"error": code}
    if message:
        payload["message"] = message
    if extra:
        payload.update(extra)
    return json_response(payload, status)


def from_api_error(exc):
    return json_response(exc.payload(), exc.status)


def html_response(text, status=200, headers=None):
    return Response(status, text, CONTENT_TYPES[".html"], headers)


def redirect(location):
    return Response(303, b"", "text/plain; charset=utf-8",
                    [("Location", location)])


def no_content():
    return Response(204, b"", "text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


def guess_content_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in CONTENT_TYPES:
        return CONTENT_TYPES[ext]
    guessed = mimetypes.guess_type(path)[0]
    return (guessed + "; charset=utf-8") if guessed else "application/octet-stream"


def safe_join(root, relative_path):
    """Join relative_path onto root, refusing anything outside root.

    Returns the absolute path, or None when the path escapes root.

    NOTE: this must not rely on os.path.normpath alone. On Windows normpath
    turns '/' into '\\', so a naive "normpath('/' + p).lstrip('/')" leaves a
    leading separator behind AND stops the '..' check from working - which
    both 404s every asset and lets a traversal reach ../../app/db.py
    (found by tests). We therefore normalise separators ourselves and verify
    the RESULT is still inside root.
    """
    cleaned = (relative_path or "").replace("\\", "/")
    parts = []
    for part in cleaned.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            # Walk back out of root -> refuse.
            if not parts:
                return None
            parts.pop()
            return None
        parts.append(part)
    if not parts:
        return None

    root_abs = os.path.abspath(root)
    candidate = os.path.abspath(os.path.join(root_abs, *parts))
    # Final safety net: the resolved path must sit inside root.
    if candidate != root_abs and not candidate.startswith(
            root_abs + os.sep):
        return None
    return candidate


def serve_file(relative_path, root=None):
    """Serve a file under www/ (or another root). Path traversal blocked."""
    root = root or WWW_DIR
    full = safe_join(root, relative_path)
    if full is None or not os.path.isfile(full):
        return None                                  # let the caller 404
    with open(full, "rb") as handle:
        body = handle.read()
    return Response(200, body, guess_content_type(full))


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def parse_cookies(header_value):
    """Parse a Cookie header into a dict. Never raises."""
    cookies = {}
    if not header_value:
        return cookies
    for part in header_value.split(";"):
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies[name.strip()] = value.strip()
    return cookies


def session_cookie_header(token, max_age=None):
    """Build the Set-Cookie header value for the session token.

    HttpOnly       -> JavaScript cannot read the token (XSS containment).
    SameSite=Strict-> the browser will not send it on cross-site requests.
    Path=/         -> applies to the whole app.
    No Secure flag: the app is plain HTTP on localhost (there is no TLS), so
    Secure would make the cookie undeliverable.
    """
    parts = [
        "%s=%s" % (SESSION_COOKIE_NAME, token),
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
    ]
    if max_age is not None:
        parts.append("Max-Age=%d" % max_age)
    return "; ".join(parts)


def expired_session_cookie_header():
    """Set-Cookie value that deletes the session cookie."""
    return "%s=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" % (
        SESSION_COOKIE_NAME,
    )


# Imported late to keep the module import-light; mirrors auth.COOKIE_NAME.
SESSION_COOKIE_NAME = "session"
