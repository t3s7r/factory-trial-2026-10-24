"""Start the service: python3 -m notes --port <port> --data <path>."""

import argparse
import sys

from notes.server import serve
from notes.store import DataFileError, NoteStore


def main(argv=None):
    parser = argparse.ArgumentParser(prog="notes")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data", required=True)
    args = parser.parse_args(argv)
    try:
        store = NoteStore.load(args.data)
    except DataFileError as err:
        sys.exit(f"notes: {err}")
    serve(args.port, store)


if __name__ == "__main__":
    main()
