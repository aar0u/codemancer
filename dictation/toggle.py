#!/usr/bin/env python3
"""Thin client: tell a running dictate.py to toggle recording.

Manual-testing / optional-extra-shortcut client — dictate.py's own evdev
hotkeys are the primary trigger (see README.md). Stdlib-only on purpose,
no uv dependency resolution on this path.
"""
import os
import socket
import sys
from pathlib import Path

SOCK_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dictate.sock"


def main() -> None:
    if not SOCK_PATH.exists():
        print(
            "No toggle socket found. Start dictate.py with --toggle first:\n"
            "  ./dictate.py --toggle",
            file=sys.stderr,
        )
        raise SystemExit(1)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(SOCK_PATH))
        sock.send(b"toggle")


if __name__ == "__main__":
    main()
