"""The HTTP service. Every response, errors included, is a JSON body, except /build-id.txt."""

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent


def build_id():
    """FACTORY_RUNTIME_CANDIDATE when set, else the git commit of the source, else "dev"."""
    candidate = os.environ.get("FACTORY_RUNTIME_CANDIDATE")
    if candidate:
        return candidate
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=SOURCE_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "dev"
    commit = result.stdout.strip()
    if result.returncode != 0 or not commit:
        return "dev"
    return commit


class Handler(BaseHTTPRequestHandler):
    server_version = "notes"

    def send_json(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def send_text(self, status, text):
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def not_found(self):
        self.send_json(404, {"error": f"no route for {self.command} {self.path}"})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self.send_json(200, {"status": "ok"})
        elif path == "/build-id":
            self.send_json(200, {"build_id": self.server.build_id})
        elif path == "/build-id.txt":
            # The runtime host compares this body to its candidate as plain text.
            self.send_text(200, self.server.build_id)
        else:
            self.not_found()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/notes":
            self.create_note()
        else:
            self.not_found()

    def read_json_object(self):
        """The request body as a dict, or None when it is not a JSON object."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(max(length, 0)))
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    def create_note(self):
        body = self.read_json_object()
        if body is None:
            self.send_json(400, {"error": "the body must be a JSON object"})
            return
        text = body.get("text")
        if not isinstance(text, str) or not text:
            self.send_json(400, {"error": "text must be a non-empty string"})
            return
        try:
            note = self.server.store.create(text)
        except OSError as err:
            self.send_json(500, {"error": f"could not save the note: {err.strerror}"})
            return
        self.send_json(201, note)

    do_PUT = not_found
    do_PATCH = not_found
    do_DELETE = not_found
    do_HEAD = not_found
    do_OPTIONS = not_found

    def send_error(self, code, message=None, explain=None):
        # http.server answers malformed requests with an HTML page; keep them JSON.
        self.close_connection = True
        if code == 501:
            # An unknown method is answered like any other unknown route.
            code, message = 404, f"no route for {self.command} {self.path}"
        try:
            self.send_json(code, {"error": message or self.responses.get(code, ("error",))[0]})
        except OSError:
            pass

    def log_message(self, format, *args):
        pass


def serve(port, store):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.store = store
    server.build_id = build_id()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
