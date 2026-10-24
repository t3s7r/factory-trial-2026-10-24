import json


def post_note(service, text):
    status, _, note = service.request("POST", "/notes", json.dumps({"text": text}).encode("utf-8"))
    assert status == 201
    return note


def list_notes(service):
    status, content_type, body = service.request("GET", "/notes")
    assert status == 200
    assert content_type == "application/json"
    return body


def test_no_data_file_lists_nothing_and_creates_no_file(start_service):
    service = start_service()
    status, _, body = service.request("GET", "/notes")
    assert status == 200
    assert body == {"notes": [], "open": 0}
    assert not service.data_path.exists()


def test_notes_come_back_in_creation_order(start_service):
    service = start_service()
    created = [post_note(service, text) for text in ("a", "b", "c")]
    body = list_notes(service)
    assert body["notes"] == created
    assert [note["text"] for note in body["notes"]] == ["a", "b", "c"]
    assert all(note["done"] is False for note in body["notes"])
    assert body["open"] == 3


def test_open_counts_the_notes_not_done(start_service, tmp_path):
    seeded = [
        {"id": 1, "text": "water the plants", "done": False},
        {"id": 2, "text": "refill the humidifier", "done": True},
        {"id": 3, "text": "call the plumber", "done": False},
    ]
    (tmp_path / "notes.json").write_text(json.dumps({"next_id": 4, "notes": seeded}))
    body = list_notes(start_service())
    assert body == {"notes": seeded, "open": 2}


def test_notes_survive_a_restart(start_service):
    first = start_service()
    created = [post_note(first, text) for text in ("one", "two")]
    first.process.terminate()
    first.process.wait(timeout=5)
    second = start_service()
    assert second.data_path == first.data_path
    body = list_notes(second)
    assert body["notes"] == created
    assert body["open"] == 2


def test_listing_never_writes_the_data_file(start_service):
    service = start_service()
    post_note(service, "one")
    post_note(service, "two")
    before = service.data_path.read_bytes()
    mtime = service.data_path.stat().st_mtime_ns
    for _ in range(3):
        list_notes(service)
    assert service.data_path.read_bytes() == before
    assert service.data_path.stat().st_mtime_ns == mtime
    assert not service.data_path.with_name("notes.json.tmp").exists()
