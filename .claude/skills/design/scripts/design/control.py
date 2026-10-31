"""Talking to a running ArtCraft app: finding its process and the flags it was started with, and one JSON-lines connection to its loopback control port.

The apps take their control port, token file, automation roots and library only at launch, so the process's own arguments are the record of how it can be reached; nothing is stored beside them.
"""

from __future__ import annotations

import json
import shlex
import socket
import subprocess
from pathlib import Path

from design.errors import Failure, Unavailable

__all__ = ["processes", "flag", "Channel"]


def processes(app: str) -> list[dict]:
    """Running instances of /Applications/<app>.app: [{"pid", "args": [...]}]."""
    try:
        r = subprocess.run(["ps", "-axo", "pid=,args="], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    marker = f"/{app}.app/Contents/MacOS/{app}"
    out = []
    for line in r.stdout.splitlines():
        pid, _, rest = line.strip().partition(" ")
        if marker in rest:
            exe, _, args = rest.partition(marker)
            try:
                parts = shlex.split(args)
            except ValueError:
                parts = args.split()
            out.append({"pid": int(pid), "args": parts})
    return out


def flag(args: list[str], name: str) -> str | None:
    """The value of `--name value` or `--name=value`. A path with spaces arrives split by ps, so the value runs to the next flag."""
    for i, a in enumerate(args):
        if a == name:
            value = []
            for b in args[i + 1:]:
                if b.startswith("--"):
                    break
                value.append(b)
            return " ".join(value) or None
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


class Channel:
    """One connection to an app's control port; PhotoCraft wants its token as the first request."""

    def __init__(self, port: int, token_file: Path | None = None, timeout: float = 65):
        try:
            self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        except OSError as exc:
            raise Unavailable(f"nothing answers on 127.0.0.1:{port} ({exc})") from exc
        self.file = self.sock.makefile("rw", encoding="utf-8")
        self.next_id = 0
        if token_file is not None:
            try:
                token = token_file.read_text().strip()
            except OSError as exc:
                raise Unavailable(f"cannot read the control token {token_file} ({exc})") from exc
            reply = self.call("auth", {"token": token})
            if not reply.get("ok"):
                raise Unavailable(f"the app refused the control token: {reply.get('error')}")

    def send_line(self, line: str) -> dict:
        self.file.write(line.rstrip("\n") + "\n")
        self.file.flush()
        raw = self.file.readline()
        if not raw:
            return {"ok": False, "error": "no reply: the connection closed"}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"unreadable reply: {raw[:200]}"}

    def call(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        return self.send_line(json.dumps({"id": self.next_id, "method": method, "params": params or {}}, ensure_ascii=False))

    def result(self, method: str, params: dict | None = None):
        reply = self.call(method, params)
        if not reply.get("ok"):
            raise Failure(f"the app answered {method} with an error: {reply.get('error')}")
        return reply.get("result")

    def close(self) -> None:
        try:
            self.file.close()
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
