import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Service:
    def __init__(self, port, data_path, process):
        self.port = port
        self.data_path = data_path
        self.process = process

    def request(self, method, path):
        """Return (status, content type, parsed JSON body)."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.headers["Content-Type"], json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, err.headers["Content-Type"], json.loads(err.read())


@pytest.fixture
def start_service(tmp_path):
    """Start `python3 -m notes` on a free port; every process started is stopped after the test."""
    started = []

    def start(env_overrides=None, drop_env=()):
        env = dict(os.environ)
        for name in drop_env:
            env.pop(name, None)
        env.update(env_overrides or {})
        port = free_port()
        data_path = tmp_path / "notes.json"
        process = subprocess.Popen(
            [sys.executable, "-m", "notes", "--port", str(port), "--data", str(data_path)],
            cwd=REPO,
            env=env,
        )
        started.append(process)
        service = Service(port, data_path, process)
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                pytest.fail(f"service exited with code {process.returncode} before answering")
            try:
                if service.request("GET", "/health")[0] == 200:
                    return service
            except OSError:
                pass
            if time.monotonic() > deadline:
                pytest.fail("service did not answer /health within 15 seconds")
            time.sleep(0.05)

    yield start
    for process in started:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
