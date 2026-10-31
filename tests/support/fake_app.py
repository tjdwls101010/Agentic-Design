"""Stand-ins for a running PhotoCraft or VectorCraft: an executable placed at <tmp>/<App>.app/Contents/MacOS/<App>, so `ps` shows it as the app with the flags it was started with, serving that app's control protocol on loopback.

It answers ui.inspect with the documents named in FAKE_APP_DOCS (a JSON list of paths), refuses engine.execute of file.placeLinked as an ambient-path command, answers the methods `test.notrun` and `test.noreply` with the two timeout errors, and logs every request it gets to FAKE_APP_LOG.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

SERVER = r'''#!/usr/bin/env python3
import json, os, socket, sys
args = sys.argv[1:]
def flag(name):
    return args[args.index(name) + 1] if name in args else None
port = int(flag("--control"))
token_file = flag("--control-token-file")
token = open(token_file).read().strip() if token_file else None
docs = json.loads(os.environ.get("FAKE_APP_DOCS", "[]"))
log = os.environ["FAKE_APP_LOG"]
app = os.path.basename(sys.argv[0])
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", port)); srv.listen(4)
while True:
    conn, _ = srv.accept()
    f = conn.makefile("rw")
    authed = token is None
    for line in f:
        req = json.loads(line)
        with open(log, "a") as fh:
            fh.write(json.dumps(req) + "\n")
        m, p, rid = req.get("method"), req.get("params") or {}, req.get("id")
        if not authed:
            if m == "auth" and p.get("token") == token:
                authed = True; reply = {"id": rid, "ok": True, "result": {"authenticated": True}}
            else:
                reply = {"id": rid, "ok": False, "error": "authentication required"}
                f.write(json.dumps(reply) + "\n"); f.flush(); break
        elif m == "ui.inspect":
            if app == "PhotoCraft":
                reply = {"id": rid, "ok": True, "result": {"session": {"active": 0, "documents": [{"index": i, "path": d, "dirty": False, "name": os.path.basename(d)} for i, d in enumerate(docs)]}}}
            else:
                reply = {"id": rid, "ok": True, "result": {"activeDocument": 0, "documents": [{"title": os.path.basename(d), "dirty": False} for d in docs]}}
        elif m == "engine.execute" and p.get("command") == "file.placeLinked":
            reply = {"id": rid, "ok": False, "error": "automation command `file.placeLinked` uses ambient filesystem paths and is disabled; use capability-scoped document methods"}
        elif m == "test.notrun":
            reply = {"id": rid, "ok": False, "error": "timeout: not run (the app was busy)"}
        elif m == "test.noreply":
            reply = {"id": rid, "ok": False, "error": "timeout: no reply in 60s"}
        elif m == "app.save":
            reply = {"id": rid, "ok": True, "result": {"path": p.get("path") or (docs[0] if docs else None), "warnings": []}}
        else:
            reply = {"id": rid, "ok": True, "result": None}
        f.write(json.dumps(reply) + "\n"); f.flush()
    conn.close()
'''


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(tmp: Path, app: str, docs: list[Path], *, control: bool = True, token: str | None = "f" * 64) -> tuple[subprocess.Popen, Path, int]:
    exe = tmp / f"{app}.app" / "Contents" / "MacOS" / app
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text(SERVER)
    exe.chmod(0o755)
    log = tmp / f"{app}-requests.jsonl"
    port = free_port()
    argv = [str(exe)]
    if control:
        argv += ["--control", str(port)]
        if token is not None:
            token_file = tmp / f"{app}.token"
            token_file.write_text(token)
            argv += ["--control-token-file", str(token_file)]
    env = {**os.environ, "FAKE_APP_DOCS": __import__("json").dumps([str(d) for d in docs]), "FAKE_APP_LOG": str(log)}
    if not control:
        argv = ["/bin/sh", "-c", f'exec -a "{exe}" sleep 600']
    proc = subprocess.Popen(argv, env=env)
    if control:
        import socket

        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)
    return proc, log, port


def requests(log: Path) -> list[dict]:
    import json

    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
