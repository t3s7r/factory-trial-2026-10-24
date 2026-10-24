"""The HTTP service. Every response, errors included, is a JSON body."""

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

    def not_found(self):
        self.send_json(404, {"error": f"no route for {self.command} {self.path}"})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self.send_json(200, {"status": "ok"})
        elif path == "/build-id":
            self.send_json(200, {"build_id": self.server.build_id})
        else:
            self.not_found()

    do_POST = not_found
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


def serve(port, data_path):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # --data is kept for the note store; nothing here touches the file yet.
    server.data_path = data_path
    server.build_id = build_id()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
