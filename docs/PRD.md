# Notes service: product requirements (trial release 1)

A single-user notes service, run locally, reached over HTTP. One person keeps short notes, marks them done, and sees how many are still open. The data survives a restart. Nothing else.

## Who it is for

One person on one machine, using the service from a script or a browser. There are no accounts and no sharing.

## Stack and conventions

- Python 3.10 or later, standard library only: `http.server` for HTTP, `json` for storage. No third-party runtime dependency.
- Tests with `pytest` (the only development dependency), run with `python3 -m pytest -q`.
- Continuous integration: one GitHub Actions workflow named `tests` that runs the test suite on every push and pull request.
- The service starts with `python3 -m notes --port <port> --data <path>` and stores every note in the JSON file at `--data`.
- Every response is JSON, except `GET /build-id.txt` (Story 1.4). Errors return `{"error": "<message>"}` with the right HTTP status.

## Phase 1: the skeleton

- Story 1.1: as the operator I start the service and ask `GET /health`; it answers `200 {"status": "ok"}`.
- Story 1.2: as the operator I ask `GET /build-id`; it answers `200 {"build_id": "<the git commit the service was built from, or 'dev'>"}`.
- Story 1.3: the test suite starts the service on a free port, calls both endpoints, and passes; CI runs it green on `main`.
- Story 1.4: as the runtime host I ask `GET /build-id.txt`; it answers `200` with `Content-Type: text/plain` and the bare build id (the same value as `/build-id`'s `build_id`) and nothing else. This is the one endpoint that is not JSON, because the factory's runtime host compares the body to the candidate as plain text (decided 2026-10-24 by the trial's operator, the harnesA4 seat, as option c of the loop's first report; the owner was not asked and had not seen the report).

## Phase 2: notes

- Story 2.1: `POST /notes` with `{"text": "refill the humidifier"}` creates a note and returns `201` with `{"id": <integer>, "text": ..., "done": false}`. An empty or missing `text` returns `400`.
- Story 2.2: `GET /notes` lists every note, newest last, as `{"notes": [...], "open": <count of notes with done false>}`.
- Story 2.3: after the service is stopped and started again with the same `--data` file, `GET /notes` returns the same notes.

## Phase 3: done and gone

- Story 3.1: `POST /notes/<id>/done` marks the note done and returns `200` with the note; the `open` count in `GET /notes` goes down by one. An unknown id returns `404`.
- Story 3.2: `DELETE /notes/<id>` removes the note and returns `204`; it is absent from `GET /notes` afterwards and after a restart. An unknown id returns `404`.

## Out of scope for this release

Accounts, sharing, search, tags, due dates, any web page or user interface, any database beyond the JSON file, any dependency beyond pytest.
