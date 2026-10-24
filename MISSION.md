# Mission

**Derived from:** docs/PRD.md
**Last reconciled with it:** 2026-10-24

## What Notes is

Notes is a single-user notes service a person runs on their own machine and reaches over HTTP. They add short notes, mark them done, delete them, and see how many are still open. Everything they wrote is still there after the service restarts.

It is one process, one person, one JSON file. There are no accounts, no network beyond localhost, and no user interface beyond the HTTP endpoints.

## Who it is for

- one person on one machine, using the service from a script, a shell or a browser, who wants a list that survives a restart

Notes is not a task manager, a wiki or a sync service.

## Core capabilities (in scope)

The factory may accept issues in these areas.

**Running and checking the service**
- start with `python3 -m notes --port <port> --data <path>`
- `GET /health` and `GET /build-id`

**Notes**
- create a note, list the notes with the open count, mark one done, delete one
- persistence to the JSON file named by `--data`, surviving a restart

**Quality**
- pytest tests that start the service on a free port and exercise every endpoint
- one GitHub Actions workflow named `tests` on every push and pull request

## Out of scope (NEVER, NOT "NOT YET")

The factory refuses issues in these areas, however reasonable they sound.

- accounts, login, sharing, or more than one user
- a web page, template, or any user interface beyond JSON over HTTP
- search, tags, due dates, reminders, priorities, or attachments
- a database, an ORM, or any storage beyond the one JSON file
- any third-party runtime dependency; pytest is the only development dependency
- a deployment target, container, or service beyond `python3 -m notes` on localhost
- editing a note's text after it is created

## Hard invariants

- a note that was acknowledged with `201` is on disk before the response is sent
- `open` in `GET /notes` always equals the count of notes with `done: false`
- the service never deletes or rewrites the data file except through its own endpoints
- the factory never changes `MISSION.md`, `docs/PRD.md`, `engineering.md`, `.claude/`, `docs/decisions/` or `docs/corrections/`

## Human-owned decisions

- any change to the data file's format
- any new dependency
- anything that touches the list above
