"""Loopback-only HTTP controller. Tests call the router without opening sockets."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit

from .catalogue import CATALOGUE
from .store import Error

STATIC = Path(__file__).parent / "static"
LIMIT = 256 * 1024
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/static/style.css": ("style.css", "text/css; charset=utf-8")}


class Application:
    def __init__(self, store, bridge, *, port):
        self.store, self.bridge, self.port = store, bridge, port
        self.csrf_token = secrets.token_urlsafe(32)

    def handle(self, method, url, headers, raw=b""):
        headers = {k.lower(): v for k, v in headers.items()}
        host = headers.get("host", "")
        try:
            if host not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
                raise Error("invalid_host", 403)
            origin = headers.get("origin")
            if origin is not None and origin != "http://" + host:
                raise Error("invalid_origin", 403)
            data = {}
            if method != "GET":
                if not hmac.compare_digest(headers.get("x-cr-token", ""), self.csrf_token):
                    raise Error("invalid_token", 403)
                if origin != "http://" + host:
                    raise Error("invalid_origin", 403)
                if headers.get("content-type", "").split(";")[0].strip() != "application/json":
                    raise Error("json_required", 415)
                if len(raw) > LIMIT:
                    raise Error("request_too_large", 413)
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise Error("invalid_json", 400) from None
                if not isinstance(data, dict):
                    raise Error("invalid_json_object", 400)
            path = urlsplit(url).path
            if method == "GET" and path in ASSETS:
                filename, mime = ASSETS[path]
                return 200, mime, (STATIC / filename).read_bytes()
            if method == "GET" and path == "/favicon.ico":
                return 204, "image/x-icon", b""
            status, result = self.route(method, path, data)
        except Error as error:
            status, result = error.status, {"error": error.code, "message": str(error)}
            if error.current is not None:
                result["current"] = error.current
        return status, "application/json; charset=utf-8", json.dumps(result, ensure_ascii=True).encode() if status != 204 else b""

    def route(self, method, path, data):
        if method == "GET" and path == "/api/state":
            return 200, dict(self.store.state(), catalogue=CATALOGUE, csrf_token=self.csrf_token,
                             session={"connected": self.bridge.ready(), "label": "This Codex session"})
        if method == "POST" and path == "/api/notes":
            return 201, self.store.create(data)
        note = re.fullmatch(r"/api/notes/([a-zA-Z0-9-]+)", path)
        if note and method == "PATCH":
            return 200, self.store.update(note[1], data)
        if note and method == "DELETE":
            self.store.delete(note[1], data.get("version"))
            return 204, None
        if method == "POST" and path == "/api/batches":
            if not self.bridge.ready():
                raise Error("session_missing", 409)
            batch, created = self.store.submit(data.get("request_id"), data.get("notes"))
            if created:
                batch = self.bridge.send(batch["id"])
            return (201 if created else 200), batch
        retry = re.fullmatch(r"/api/batches/([a-zA-Z0-9-]+)/retry", path)
        if method == "POST" and retry:
            batch = self.store.get_batch(retry[1])
            if batch["status"] not in ("failed", "uncertain", "queued"):
                raise Error("not_retryable", 409)
            return 200, self.bridge.send(batch["id"])
        raise Error("not_found", 404)


def serve(app):
    class Handler(BaseHTTPRequestHandler):
        def handle_one_request(self):
            self.connection.settimeout(5)
            return super().handle_one_request()

        def dispatch(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 <= length <= LIMIT or self.headers.get("Transfer-Encoding"):
                    self.send_error(413)
                    return
                status, mime, body = app.handle(self.command, self.path, dict(self.headers), self.rfile.read(length))
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                self.end_headers()
                self.wfile.write(body)
            except (ValueError, TimeoutError):
                self.send_error(400)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_POST = do_PATCH = do_DELETE = dispatch

        def log_message(self, fmt, *args):
            pass  # Notes and query strings do not belong in access logs.

    with ThreadingHTTPServer(("127.0.0.1", app.port), Handler) as server:
        print(f"MaxPane change requests: http://127.0.0.1:{app.port}", flush=True)
        server.serve_forever()
