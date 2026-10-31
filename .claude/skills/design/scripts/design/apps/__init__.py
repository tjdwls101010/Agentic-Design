"""The running apps: what each has open, starting one so it can be driven, and passing requests to it.

A document open in an app is edited through the app: a change made on disk is overwritten silently by the app's next save. The apps take their control port, automation roots and library only at launch, and compare automation roots as text, so they are started with the vault's resolved path as both roots. An app already running without a control port is 성진's: it is never quit from here.
"""

from __future__ import annotations

import json
from pathlib import Path

from design import lightcraft, paths, photocraft, vectorcraft
from design.errors import Usage

__all__ = ["status", "launch", "send", "APPS"]

SYSTEMS = {"photocraft": photocraft, "vectorcraft": vectorcraft, "lightcraft": lightcraft}
APPS = list(SYSTEMS)


def status() -> dict:
    states = [SYSTEMS[name].app_state() for name in APPS]
    notes = []
    for s in states:
        if s.get("app_version") and s.get("cli_version") and s["app_version"] != s["cli_version"]:
            notes.append(f"{s['app']} app {s['app_version']} and CLI {s['cli_version']} differ (doctor)")
        if s["running"] and s.get("control_port") is None and s["app"] != "lightcraft":
            notes.append(f"{s['app']} runs without a control port: it cannot be asked what it has open; ask 성진 to save and quit it before editing its documents on disk")
    running = [s["app"] for s in states if s["running"]]
    out = {"summary": (f"running: {', '.join(running)}" if running else "no app running") + (f"; {len(notes)} note(s)" if notes else ""), "apps": states}
    if notes:
        out["notes"] = notes
    return out


def launch(app: str, doc: Path | None) -> dict:
    root = paths.data_root()
    if doc is not None:
        try:
            doc.resolve().relative_to(root)
        except ValueError:
            raise Usage(f"{doc} is outside data/ ({root}); the app's automation roots are the vault's folder") from None
    if app == "lightcraft":
        if doc is None or (doc.exists() and not doc.is_dir()):
            raise Usage("LightCraft opens a job's library folder (made when missing): give --doc <job>/work/lightcraft")
        return lightcraft.app_launch(doc)
    return SYSTEMS[app].app_launch(root, doc)


def _kind(reply: dict) -> str:
    """ok, or why not: not_run (never dispatched: safe to send again), no_reply (dispatched and may still apply: inspect before resending), refused_path (a command that takes a file path is closed to the bridge), error."""
    if reply.get("ok"):
        return "ok"
    error = str(reply.get("error", ""))
    if error.startswith("timeout: not run"):
        return "not_run"
    if error.startswith("timeout") or error.startswith("no reply"):
        return "no_reply"
    if "ambient filesystem paths" in error or "automation path rejected" in error:
        return "refused_path"
    return "error"


def send(app: str, lines: list[str]) -> dict:
    if app == "lightcraft":
        raise Usage("drive LightCraft with lightcraft-cli run --connect 127.0.0.1:7980 …")
    for line in lines:
        try:
            if not isinstance(json.loads(line), dict):
                raise ValueError
        except ValueError:
            raise Usage(f"every stdin line must be one JSON request object, e.g. {{\"method\": \"ui.inspect\", \"params\": {{}}}}; got {line[:80]!r}") from None
    replies = SYSTEMS[app].app_send(lines)
    kinds = [_kind(r) for r in replies]
    counts = {k: kinds.count(k) for k in dict.fromkeys(kinds)}
    out = {"summary": ", ".join(f"{n} {k}" for k, n in counts.items()), "replies": [{"kind": k, **r} for k, r in zip(kinds, replies)]}
    if counts.get("refused_path"):
        out["next"] = "the bridge refuses commands that take a file path (placing a linked file among them): save the document in the app, ask 성진 to close it, place headlessly with photocraft-cli run, and open it again; or 성진 uses File › Place Linked"
    return out
