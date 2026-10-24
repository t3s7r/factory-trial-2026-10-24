import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import REPO, free_port


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
    [b"{}", b'{"text": ""}', b'{"text": 5}', b"not json", b'["text"]', b"\xff", b""],
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
    ],
)
def test_malformed_data_file_stops_the_service(tmp_path, content):
    data_path = tmp_path / "notes.json"
    data_path.write_bytes(content)
    result = subprocess.run(
        [sys.executable, "-m", "notes", "--port", str(free_port()), "--data", str(data_path)],
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
