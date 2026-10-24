# Runtime scenarios

Journeys for the Notes service, written from docs/PRD.md. Shared runtime verification owns execution and evidence. The service is started with `python3 -m notes --port <port> --data <fresh path>`.

## The service is up and says which build it is

1. `GET /health` returns `200` with `{"status": "ok"}`.
2. `GET /build-id` returns `200` with a non-empty `build_id`.

**What would make this fail:** a non-200, an empty or missing field, or a build id that does not match the delivered revision when `FACTORY_RUNTIME_CANDIDATE` is set.

## A person keeps a note and finishes it

1. `POST /notes` with `{"text": "refill the humidifier"}` returns `201` and a note with an integer `id`, that `text`, and `done` false.
2. `GET /notes` lists it, `open` is 1.
3. `POST /notes/<id>/done` returns `200` with `done` true.
4. `GET /notes` still lists it, now done, and `open` is 0.

**What would make this fail:** the note comes back changed, `open` does not move, or marking one note done touches another.

## Notes survive a restart

1. Add two notes with distinct texts; mark the first done.
2. Stop the service and start it again with the same `--data` file.
3. `GET /notes` returns both notes, exactly the first is done, `open` is 1.

**What would make this fail:** anything held only in memory, or a write acknowledged before it reached the file.

## Bad input and unknown ids are refused

1. `POST /notes` with `{}` or `{"text": ""}` returns `400` with an `error` field.
2. `POST /notes/999999/done` and `DELETE /notes/999999` return `404` with an `error` field.
3. `GET /notes` is unchanged by any of the above.

**What would make this fail:** a `500`, a note created from empty text, or a 404 that changed the list.
