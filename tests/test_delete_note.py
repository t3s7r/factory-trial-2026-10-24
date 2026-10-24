import json
import urllib.error
import urllib.request

import pytest


def post_note(service, text):
    status, _, note = service.request("POST", "/notes", json.dumps({"text": text}).encode("utf-8"))
    assert status == 201
    return note


def delete_note(service, note_id):
    """Return (status, content type, raw body bytes) for DELETE /notes/<note_id>."""
    req = urllib.request.Request(f"http://127.0.0.1:{service.port}/notes/{note_id}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers["Content-Type"], resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers["Content-Type"], err.read()


def list_notes(service):
    status, _, body = service.request("GET", "/notes")
    assert status == 200
    return body


def restart(service, start_service):
    service.process.terminate()
    service.process.wait(timeout=5)
    again = start_service()
    assert again.data_path == service.data_path
    return again


def test_deleting_the_middle_note_keeps_the_others_in_order(start_service):
    service = start_service()
    a = post_note(service, "a")
    b = post_note(service, "b")
    c = post_note(service, "c")
    status, _, body = delete_note(service, b["id"])
    assert status == 204
    assert body == b""
    listed = list_notes(service)
    assert [note["text"] for note in listed["notes"]] == ["a", "c"]
    assert listed["notes"] == [a, c]
    assert listed["open"] == 2


def test_delete_is_on_disk_before_the_answer(start_service):
    service = start_service()
    a = post_note(service, "a")
    b = post_note(service, "b")
    c = post_note(service, "c")
    assert delete_note(service, b["id"])[0] == 204
    data = json.loads(service.data_path.read_text(encoding="utf-8"))
    assert data == {"next_id": c["id"] + 1, "notes": [a, c]}
    assert not service.data_path.with_name("notes.json.tmp").exists()


def test_deleted_note_stays_gone_after_a_restart(start_service):
    first = start_service()
    keep = post_note(first, "keep")
    gone = post_note(first, "gone")
    assert delete_note(first, gone["id"])[0] == 204
    second = restart(first, start_service)
    listed = list_notes(second)
    assert gone["id"] not in [note["id"] for note in listed["notes"]]
    assert listed == {"notes": [keep], "open": 1}


def test_deleting_twice_is_a_204_then_a_404(start_service):
    service = start_service()
    note = post_note(service, "a")
    assert delete_note(service, note["id"])[:1] == (204,)
    before = service.data_path.read_bytes()
    status, content_type, body = delete_note(service, note["id"])
    assert status == 404
    assert content_type == "application/json"
    assert isinstance(json.loads(body)["error"], str)
    assert service.data_path.read_bytes() == before


@pytest.mark.parametrize("note_id", ["999999", "abc", "0", "-1", "01", "1.0", "", "1%2F2", "%31"])
def test_unknown_or_bad_id_is_a_404_and_changes_nothing(start_service, note_id):
    service = start_service()
    post_note(service, "one")
    post_note(service, "two")
    before = service.data_path.read_bytes()
    status, content_type, body = delete_note(service, note_id)
    assert status == 404
    assert content_type == "application/json"
    assert isinstance(json.loads(body)["error"], str)
    assert service.data_path.read_bytes() == before
    assert len(list_notes(service)["notes"]) == 2


def test_delete_of_a_nested_path_is_a_404(start_service):
    service = start_service()
    note = post_note(service, "one")
    before = service.data_path.read_bytes()
    status, _, body = delete_note(service, f"{note['id']}/done")
    assert status == 404
    assert isinstance(json.loads(body)["error"], str)
    assert service.data_path.read_bytes() == before


def test_unknown_id_without_a_data_file_creates_none(start_service):
    service = start_service()
    assert delete_note(service, 1)[0] == 404
    assert not service.data_path.exists()


def test_a_deleted_highest_id_is_never_issued_again(start_service):
    service = start_service()
    first = post_note(service, "one")
    second = post_note(service, "two")
    assert delete_note(service, second["id"])[0] == 204
    data = json.loads(service.data_path.read_text(encoding="utf-8"))
    assert data["next_id"] == second["id"] + 1
    third = post_note(service, "three")
    assert third["id"] > max(first["id"], second["id"])
    again = restart(service, start_service)
    fourth = post_note(again, "four")
    assert fourth["id"] > max(first["id"], second["id"], third["id"])


def test_failed_write_is_a_500_and_changes_nothing(start_service):
    service = start_service()
    note = post_note(service, "one")
    before = service.data_path.read_bytes()
    tmp_path = service.data_path.with_name("notes.json.tmp")
    tmp_path.mkdir()
    status, _, body = delete_note(service, note["id"])
    assert status == 500
    assert isinstance(json.loads(body)["error"], str)
    assert service.data_path.read_bytes() == before
    assert list_notes(service)["notes"] == [note]
    tmp_path.rmdir()
    assert delete_note(service, note["id"])[0] == 204
