"""The HTTP service. Every response, errors included, is a JSON body, except /build-id.txt
and the empty body of a 204."""

import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
# An id in a path is a decimal integer written without leading zeros; anything else names no note.
DONE_PATH = re.compile(r"/notes/([^/]*)/done")
NOTE_PATH = re.compile(r"/notes/([^/]*)")
NOTE_ID = re.compile(r"0|[1-9][0-9]*")


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

    def send_empty(self, status):
        # A 204 carries no body and, per RFC 9110, no Content-Length.
        self.send_response(status)
        self.end_headers()

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
        elif path == "/notes":
            self.list_notes()
        else:
            self.not_found()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        done_match = DONE_PATH.fullmatch(path)
        if path == "/notes":
            self.create_note()
        elif done_match:
            self.mark_done(done_match.group(1))
        else:
            self.not_found()

    def list_notes(self):
        notes = self.server.store.list()
        # open is counted from the notes being returned, never stored.
        self.send_json(200, {"notes": notes, "open": sum(1 for note in notes if not note["done"])})

    def read_json_object(self):
        """The request body as a dict, or None when it is not a JSON object."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(max(length, 0)))
        except (ValueError, RecursionError):
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

    def mark_done(self, raw_id):
        note = None
        if NOTE_ID.fullmatch(raw_id):
            try:
                note = self.server.store.mark_done(int(raw_id))
            except OSError as err:
                self.send_json(500, {"error": f"could not save the note: {err.strerror}"})
                return
        if note is None:
            self.send_json(404, {"error": f"no note with id {raw_id}"})
            return
        self.send_json(200, note)

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        note_match = NOTE_PATH.fullmatch(path)
        if note_match:
            self.delete_note(note_match.group(1))
        else:
            self.not_found()

    def delete_note(self, raw_id):
        deleted = False
        if NOTE_ID.fullmatch(raw_id):
            try:
                deleted = self.server.store.delete(int(raw_id))
            except OSError as err:
                self.send_json(500, {"error": f"could not save the change: {err.strerror}"})
                return
        if not deleted:
            self.send_json(404, {"error": f"no note with id {raw_id}"})
            return
        self.send_empty(204)

    do_PUT = not_found
    do_PATCH = not_found
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
