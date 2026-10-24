import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

import notes.store
from conftest import REPO, free_port, service_command
from notes.store import NoteStore


def post_note(service, body):
    return service.request("POST", "/notes", json.dumps(body).encode("utf-8"))


def read_data(service):
    return json.loads(service.data_path.read_text(encoding="utf-8"))


def test_create_returns_the_new_note(start_service):
    service = start_service()
    status, content_type, body = post_note(service, {"text": "refill the humidifier"})
    assert status == 201
    assert content_type == "application/json"
    assert set(body) == {"id", "text", "done"}
    assert isinstance(body["id"], int) and not isinstance(body["id"], bool)
    assert body["text"] == "refill the humidifier"
    assert body["done"] is False


def test_created_note_is_on_disk_before_the_answer(start_service):
    service = start_service()
    _, _, note = post_note(service, {"text": "refill the humidifier"})
    data = read_data(service)
    assert {"id": note["id"], "text": "refill the humidifier", "done": False} in data["notes"]
    assert not service.data_path.with_name("notes.json.tmp").exists()


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"text": ""}',
        b'{"text": 5}',
        b"not json",
        b'["text"]',
        b"\xff",
        b"",
        pytest.param(b"[" * 100000 + b"]" * 100000, id="deeply-nested"),
    ],
)
def test_bad_body_is_a_400_and_creates_nothing(start_service, body):
    service = start_service()
    status, content_type, answer = service.request("POST", "/notes", body)
    assert status == 400
    assert content_type == "application/json"
    assert isinstance(answer["error"], str)
    assert not service.data_path.exists()


def test_bad_body_leaves_an_existing_file_unchanged(start_service):
    service = start_service()
    post_note(service, {"text": "first"})
    before = service.data_path.read_bytes()
    for body in (b"{}", b'{"text": ""}', b'{"text": 5}', b"not json"):
        assert service.request("POST", "/notes", body)[0] == 400
    assert service.data_path.read_bytes() == before


def test_ids_increase(start_service):
    service = start_service()
    _, _, first = post_note(service, {"text": "one"})
    _, _, second = post_note(service, {"text": "two"})
    assert isinstance(first["id"], int) and isinstance(second["id"], int)
    assert second["id"] > first["id"]
    assert [n["id"] for n in read_data(service)["notes"]] == [first["id"], second["id"]]


def test_existing_file_keeps_its_notes_and_counter(start_service, tmp_path):
    existing = {"id": 7, "text": "water the plants", "done": True}
    (tmp_path / "notes.json").write_text(json.dumps({"next_id": 8, "notes": [existing]}))
    service = start_service()
    status, _, note = post_note(service, {"text": "refill the humidifier"})
    assert status == 201
    assert note["id"] == 8
    data = read_data(service)
    assert data == {
        "next_id": 9,
        "notes": [existing, {"id": 8, "text": "refill the humidifier", "done": False}],
    }


def test_ids_come_from_next_id_not_the_highest_id(start_service, tmp_path):
    existing = {"id": 7, "text": "water the plants", "done": False}
    (tmp_path / "notes.json").write_text(json.dumps({"next_id": 12, "notes": [existing]}))
    _, _, note = post_note(start_service(), {"text": "refill the humidifier"})
    assert note["id"] == 12


def test_failed_write_is_a_500_and_changes_nothing(start_service):
    service = start_service()
    post_note(service, {"text": "first"})
    before = service.data_path.read_bytes()
    tmp_path = service.data_path.with_name("notes.json.tmp")
    tmp_path.mkdir()
    status, _, answer = post_note(service, {"text": "lost"})
    assert status == 500
    assert isinstance(answer["error"], str)
    assert service.data_path.read_bytes() == before
    tmp_path.rmdir()
    assert post_note(service, {"text": "second"})[0] == 201
    assert [n["text"] for n in read_data(service)["notes"]] == ["first", "second"]


def test_create_writes_a_synced_tmp_file_then_replaces(tmp_path, monkeypatch):
    calls = []
    real_fsync, real_replace = notes.store.os.fsync, notes.store.os.replace

    def fsync(fd):
        calls.append("fsync")
        real_fsync(fd)

    def replace(src, dst):
        calls.append(("replace", str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(notes.store.os, "fsync", fsync)
    monkeypatch.setattr(notes.store.os, "replace", replace)
    path = tmp_path / "notes.json"
    NoteStore.load(path).create("x")
    assert calls == ["fsync", ("replace", f"{path}.tmp", str(path))]


def test_ids_are_not_reused_after_a_restart(start_service):
    service = start_service()
    _, _, first = post_note(service, {"text": "one"})
    service.process.terminate()
    service.process.wait(timeout=5)
    _, _, second = post_note(start_service(), {"text": "two"})
    assert second["id"] > first["id"]


@pytest.mark.parametrize(
    "content",
    [
        b"{broken",
        b"[]",
        b'{"notes": []}',
        b'{"next_id": 1, "notes": [{"id": 1, "text": "x", "done": false}]}',
        b'{"next_id": 2, "notes": [{"id": 1, "text": "x"}]}',
        b'{"next_id": 2, "notes": [{"id": true, "text": "x", "done": false}]}',
        b'{"next_id": 0, "notes": []}',
        b'{"next_id": 2, "notes": [{"id": 0, "text": "x", "done": false}]}',
        b'{"next_id": 4, "notes": [{"id": 1, "text": "x", "done": false},'
        b' {"id": 1, "text": "y", "done": false}]}',
        b'{"next_id": 4, "notes": [{"id": 3, "text": "x", "done": false},'
        b' {"id": 2, "text": "y", "done": false}]}',
        pytest.param(b"[" * 100000 + b"]" * 100000, id="deeply-nested"),
    ],
)
def test_malformed_data_file_stops_the_service(tmp_path, content):
    data_path = tmp_path / "notes.json"
    data_path.write_bytes(content)
    result = subprocess.run(
        service_command(free_port(), data_path),
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "notes.json" in result.stderr
    assert data_path.read_bytes() == content


def test_concurrent_creates_get_distinct_ids_and_all_reach_the_file(start_service):
    service = start_service()
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(lambda i: post_note(service, {"text": f"note {i}"}), range(20)))
    ids = [body["id"] for status, _, body in answers if status == 201]
    assert len(set(ids)) == 20
    assert sorted(n["id"] for n in read_data(service)["notes"]) == sorted(ids)
