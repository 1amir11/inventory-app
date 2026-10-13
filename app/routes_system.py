# routes_system.py - launcher quit action and page heartbeat.
#
#   POST /api/heartbeat  one page ping every ~10 s; keeps the launcher from
#       treating an idle-but-open window as abandoned.
#   POST /api/shutdown   in-app "close program" button. Sets a flag the
#       launcher polls, plus an audit row.
#   GET /api/shutdown-status (PUBLIC): the launcher's poll endpoint -
#       {shutdown_requested, heartbeat_seen, heartbeat_idle_seconds}.
#       Public because the launcher has no session; localhost-only anyway.
#
# Standard library only, Python 3.8 compatible.

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import db  # noqa: E402
import http_kit  # noqa: E402
from http_kit import ApiError  # noqa: E402


def api_heartbeat(context, request):
    if not request.is_json_content_type():
        raise ApiError(400, "json_required")
    context.note_heartbeat()
    return http_kit.json_response({"ok": True})


def api_shutdown(context, request):
    if not request.is_json_content_type():
        raise ApiError(400, "json_required")
    body = request.json()
    user_id = body.get("user_id")
    conn = context.connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO audit_log (user_id, action, entity, reason,"
                " created_at) VALUES (?, 'shutdown', 'app',"
                " 'quit from home screen', ?)",
                (user_id if isinstance(user_id, int) else None,
                 db.now_iso()))
    finally:
        conn.close()
    context.request_shutdown()
    return http_kit.json_response({"ok": True})


def api_shutdown_status(context, request):
    seen, idle = context.heartbeat_status()
    return http_kit.json_response({
        "shutdown_requested": context.shutdown_requested(),
        "heartbeat_seen": seen,
        "heartbeat_idle_seconds": idle,
    })
