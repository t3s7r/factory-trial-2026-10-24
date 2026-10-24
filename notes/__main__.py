"""Start the service: python3 -m notes --port <port> --data <path>."""

import argparse

from notes.server import serve


def main(argv=None):
    parser = argparse.ArgumentParser(prog="notes")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data", required=True)
    args = parser.parse_args(argv)
    serve(args.port, args.data)


if __name__ == "__main__":
    main()
