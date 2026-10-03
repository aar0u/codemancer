#!/usr/bin/env python3
"""Thin client for dictate.py's socket: `toggle.py [toggle | start <source> | stop <source>]`.

Hyprland binds call `start kbd` on key press and `stop kbd` on release (see README.md).
Stdlib-only on purpose, so no uv dependency resolution on this path.
"""
import os
import socket
import sys
from pathlib import Path

SOCK_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dictate.sock"


def main() -> None:
    message = " ".join(sys.argv[1:]) or "toggle"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(SOCK_PATH))
            sock.sendall(message.encode())
    except OSError as e:  # missing socket file, or a stale one left by a crashed daemon
        print(f"dictate socket unavailable ({e}). Is dictate.service running?", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
