import json

import pytest


def post_note(service, text):
    status, _, note = service.request("POST", "/notes", json.dumps({"text": text}).encode("utf-8"))
    assert status == 201
    return note


def mark_done(service, note_id):
    return service.request("POST", f"/notes/{note_id}/done")


def list_notes(service):
    status, _, body = service.request("GET", "/notes")
    assert status == 200
    return body


def test_marking_one_note_done_leaves_the_other_open(start_service):
    service = start_service()
    first = post_note(service, "refill the humidifier")
    second = post_note(service, "water the plants")
    status, content_type, body = mark_done(service, first["id"])
    assert status == 200
    assert content_type == "application/json"
    assert body == {"id": first["id"], "text": "refill the humidifier", "done": True}
    listed = list_notes(service)
    assert listed["open"] == 1
    assert listed["notes"] == [body, second]
    assert listed["notes"][1]["done"] is False


def test_done_is_on_disk_before_the_answer(start_service):
    service = start_service()
    first = post_note(service, "one")
    second = post_note(service, "two")
    mark_done(service, first["id"])
    data = json.loads(service.data_path.read_text(encoding="utf-8"))
    assert data["notes"] == [dict(first, done=True), second]
    assert data["next_id"] == second["id"] + 1
    assert not service.data_path.with_name("notes.json.tmp").exists()


def test_done_twice_stays_done_once(start_service):
    service = start_service()
    note = post_note(service, "refill the humidifier")
    first_status, _, first_body = mark_done(service, note["id"])
    after_first = service.data_path.read_bytes()
    second_status, _, second_body = mark_done(service, note["id"])
    assert first_status == 200 and second_status == 200
    assert first_body == second_body == dict(note, done=True)
    assert service.data_path.read_bytes() == after_first
    assert list_notes(service) == {"notes": [dict(note, done=True)], "open": 0}


@pytest.mark.parametrize("note_id", ["999999", "abc", "0", "-1", "01", "1.0", "", "1%2F2", "%31"])
def test_unknown_or_bad_id_is_a_404_and_changes_nothing(start_service, note_id):
    service = start_service()
    post_note(service, "one")
    post_note(service, "two")
    before = service.data_path.read_bytes()
    status, content_type, body = mark_done(service, note_id)
    assert status == 404
    assert content_type == "application/json"
    assert isinstance(body["error"], str)
    assert service.data_path.read_bytes() == before
    assert list_notes(service)["open"] == 2


def test_unknown_id_without_a_data_file_creates_none(start_service):
    service = start_service()
    assert mark_done(service, 1)[0] == 404
    assert not service.data_path.exists()


def test_done_survives_a_restart(start_service):
    first = start_service()
    note = post_note(first, "refill the humidifier")
    other = post_note(first, "water the plants")
    assert mark_done(first, note["id"])[0] == 200
    first.process.terminate()
    first.process.wait(timeout=5)
    second = start_service()
    assert second.data_path == first.data_path
    assert list_notes(second) == {"notes": [dict(note, done=True), other], "open": 1}


def test_failed_write_is_a_500_and_changes_nothing(start_service):
    service = start_service()
    note = post_note(service, "one")
    before = service.data_path.read_bytes()
    tmp_path = service.data_path.with_name("notes.json.tmp")
    tmp_path.mkdir()
    status, _, body = mark_done(service, note["id"])
    assert status == 500
    assert isinstance(body["error"], str)
    assert service.data_path.read_bytes() == before
    assert list_notes(service)["open"] == 1
    tmp_path.rmdir()
    assert mark_done(service, note["id"])[0] == 200
