"""The note store: every note lives in the JSON file at --data.

The file is {"next_id": <int>, "notes": [{"id": <int>, "text": <str>, "done": <bool>}, ...]},
notes in creation order. next_id only ever increases, so an id is never issued twice.
Changing this format is a human-owned decision (MISSION.md).
"""

import json
import os
import threading


class DataFileError(Exception):
    """The data file exists but is not a notes file this service can read."""


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_note(note):
    if not isinstance(note, dict) or set(note) != {"id", "text", "done"}:
        raise DataFileError("each note must be an object with exactly id, text and done")
    if not is_int(note["id"]) or not isinstance(note["text"], str) or not isinstance(note["done"], bool):
        raise DataFileError(f"note {note['id']!r} has a field of the wrong type")


def check_state(state):
    if not isinstance(state, dict) or set(state) != {"next_id", "notes"}:
        raise DataFileError("the top level must be an object with exactly next_id and notes")
    if not is_int(state["next_id"]) or not isinstance(state["notes"], list):
        raise DataFileError("next_id must be an integer and notes a list")
    if state["next_id"] < 1:
        raise DataFileError(f"next_id {state['next_id']} is below 1")
    previous_id = 0
    for note in state["notes"]:
        check_note(note)
        if not previous_id < note["id"] < state["next_id"]:
            raise DataFileError(
                f"note id {note['id']} is not above {previous_id} and below next_id {state['next_id']}"
            )
        previous_id = note["id"]


class NoteStore:
    def __init__(self, path, state):
        self.path = path
        self.state = state
        self.lock = threading.Lock()

    @classmethod
    def load(cls, path):
        """Read the file at path, or start empty without creating it when it does not exist."""
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            return cls(path, {"next_id": 1, "notes": []})
        except OSError as err:
            raise DataFileError(f"cannot read {path}: {err.strerror}") from err
        try:
            state = json.loads(raw)
        except (ValueError, RecursionError) as err:
            raise DataFileError(f"{path} is not valid JSON: {err}") from err
        try:
            check_state(state)
        except DataFileError as err:
            raise DataFileError(f"{path} is not a notes file: {err}") from err
        return cls(path, state)

    def list(self):
        """Every note in creation order, read from memory; never touches the file."""
        with self.lock:
            return [dict(note) for note in self.state["notes"]]

    def create(self, text):
        """Write a new note to the file and return it; the note exists only once it is on disk."""
        with self.lock:
            note = {"id": self.state["next_id"], "text": text, "done": False}
            state = {"next_id": note["id"] + 1, "notes": self.state["notes"] + [note]}
            self.write(state)
            self.state = state
            return note

    def mark_done(self, note_id):
        """Set done on the note with note_id and return it, or None when there is no such note.

        The change is on disk before it is returned; a note already done is returned unchanged
        without writing, and only the named note changes.
        """
        with self.lock:
            for index, note in enumerate(self.state["notes"]):
                if note["id"] == note_id:
                    break
            else:
                return None
            if note["done"]:
                return dict(note)
            done = dict(note, done=True)
            notes = self.state["notes"][:index] + [done] + self.state["notes"][index + 1 :]
            state = {"next_id": self.state["next_id"], "notes": notes}
            self.write(state)
            self.state = state
            return dict(done)

    def write(self, state):
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.path)
