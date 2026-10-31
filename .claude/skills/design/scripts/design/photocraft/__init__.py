"""photocraft-cli, the headless PhotoCraft (a Photoshop clone), as the skill uses it.

What PhotoCraft owns stays in here: the CLI's argv, its one-JSON-line-per-step output, how it reports a failed step, and the shapes of the results the skill reads (font faces, type layer info, the document tree). Callers get plain dicts and lists in the skill's terms.

A linked smart object renders from the pixels cached in the document: a linked file that changed shows only after an update step, and one that is missing still renders from the cache without a word. So every render here updates linked content first, and `links` says which linked files exist.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from design import control
from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "app_holds", "app_state", "app_launch", "app_send", "app_save", "font_faces", "info", "layers", "links", "type_runs", "render", "UPDATE_LINKS"]

CLI = "photocraft-cli"


def executable() -> str | None:
    return shutil.which(CLI)


def version() -> str | None:
    try:
        r = subprocess.run([CLI, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def run(steps: list[tuple[str, dict]], *, file: Path | None = None, new: dict | None = None, out: Path | None = None, in_place: bool = False, quality: int | None = None, timeout: float = 600) -> list[dict]:
    """One `photocraft-cli run`: open `file` (or start `new`), run the steps in order, save to `out`. Returns each step's result. A failed step fails the whole run and nothing is saved."""
    if not executable():
        raise Unavailable(f"{CLI} is not on PATH; install it (doctor checks the environment)")
    argv = [CLI, "run", str(file)] if file is not None else [CLI, "run", "--new", json.dumps(new or {})]
    for command, params in steps:
        argv += ["--cmd", command, "--params", json.dumps(params, ensure_ascii=False)]
    if out is not None:
        argv += ["--out", str(out)]
        if in_place:
            argv.append("--in-place")
        if quality is not None:
            argv += ["--quality", str(quality)]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise Failure(f"{CLI} run did not finish within {timeout:.0f}s") from exc
    if r.returncode != 0:
        raise Failure(f"{CLI} run failed: {(r.stderr or r.stdout).strip()[-600:]}", steps=[c for c, _ in steps])
    results = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(doc, dict) and "command" in doc:
                results.append(doc.get("result"))
    if len(results) != len(steps):
        raise Failure(f"{CLI} run printed {len(results)} results for {len(steps)} steps; its output format may have changed")
    return results


def font_faces(family: str) -> list[dict]:
    """The faces PhotoCraft resolves under a family name: [{"style", "postscript", "weight", "italic"}]. Empty when it does not know the family."""
    (result,) = run([("type.fonts", {"family": family})], new={"width": 8, "height": 8})
    return [{"style": f.get("style"), "postscript": f.get("postscriptName"), "weight": f.get("weight"), "italic": f.get("italic")} for f in (result or {}).get("faces", [])]


# Re-read every linked file that changed since the document cached it; a missing one is skipped silently (links() reports those).
UPDATE_LINKS = ("layer.smartObjects.updateAllModifiedContent", {})


def info(doc: Path) -> dict:
    if not executable():
        raise Unavailable(f"{CLI} is not on PATH; install it (doctor checks the environment)")
    try:
        r = subprocess.run([CLI, "info", str(doc)], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise Failure(f"{CLI} info did not finish within 300s") from exc
    if r.returncode != 0:
        raise Failure(f"{CLI} info could not read {doc}: {(r.stderr or r.stdout).strip()[-400:]}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise Failure(f"{CLI} info printed something other than JSON; its output format may have changed ({exc})") from exc


def layers(doc_info: dict) -> list[dict]:
    """Every layer of a document, groups opened, top-down: {"id", "name", "kind", "visible", "bounds": [x, y, w, h] | None, "text"?, "linked"?}."""
    out = []

    def walk(items):
        for layer in items:
            row = {"id": layer.get("id"), "name": layer.get("name"), "kind": layer.get("kind"), "visible": layer.get("visible", True), "bounds": layer.get("bounds")}
            if isinstance(layer.get("text"), dict):
                row["text"] = layer["text"].get("text", "")
            source = layer.get("smartSource")
            if isinstance(source, dict) and source.get("kind") == "linked":
                row["linked"] = source.get("path")
            out.append(row)
            walk(layer.get("children") or [])

    walk(doc_info.get("layers") or [])
    return out


def links(doc_info: dict) -> list[dict]:
    """Linked smart objects and whether their files exist: [{"layer", "name", "path", "exists"}]."""
    return [{"layer": l["id"], "name": l["name"], "path": l["linked"], "exists": Path(l["linked"]).is_file()} for l in layers(doc_info) if l.get("linked")]


def type_runs(doc: Path, layer_ids: list[int]) -> dict[int, list[dict]]:
    """For each type layer, its style runs: {"text", "family", "style" (as requested), "postscript" (the face actually used)}."""
    if not layer_ids:
        return {}
    results = run([("type.info", {"layer": i}) for i in layer_ids], file=doc)
    out = {}
    for layer_id, result in zip(layer_ids, results):
        text = (result or {}).get("text", "")
        out[layer_id] = [{"text": text[r["start"]:r["end"]], "family": r["style"].get("font_family"), "style": r["style"].get("font_style"), "postscript": r["style"].get("postscript_name")} for r in (result or {}).get("runs", [])]
    return out


def render(doc: Path, out: Path, *, size: tuple[int, int] | None = None, quality: int | None = None) -> None:
    """Flatten `doc` to an image file (format by `out`'s extension), linked content updated first, resampled to `size` when given."""
    steps = [UPDATE_LINKS]
    if size:
        steps.append(("image.imageSize", {"width": size[0], "height": size[1]}))
    run(steps, file=doc, out=out, quality=quality)


APP = "PhotoCraft"
APP_PATH = Path("/Applications/PhotoCraft.app")
PORT = 7977


def _token_file() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "design-skill" / "photocraft.token"


def app_state() -> dict:
    """The installed and running app: {"app", "installed", "app_version", "cli_version", "running", "pid"?, "control_port"?, "documents"?: [{"path", "dirty", "active"}], "roots"?}."""
    cli = version()
    state = {"app": "photocraft", "installed": APP_PATH.is_dir(), "app_version": _bundle_version(APP_PATH), "cli_version": cli.split(" ")[1] if cli and " " in cli else cli, "running": False}
    procs = control.processes(APP)
    if not procs:
        return state
    args = procs[0]["args"]
    state.update({"running": True, "pid": procs[0]["pid"], "control_port": None})
    port = control.flag(args, "--control")
    if port:
        state["control_port"] = int(port)
        state["roots"] = {"read": control.flag(args, "--automation-read-root"), "write": control.flag(args, "--automation-write-root")}
        token = control.flag(args, "--control-token-file")
        try:
            with control.Channel(int(port), Path(token) if token else None) as ch:
                session = (ch.result("ui.inspect") or {}).get("session") or {}
            state["documents"] = [{"path": d.get("path"), "dirty": d.get("dirty"), "active": d.get("index") == session.get("active"), "index": d.get("index")} for d in session.get("documents", [])]
        except (Unavailable, Failure) as exc:
            state["error"] = exc.message
    return state


def _bundle_version(app: Path) -> str | None:
    try:
        r = subprocess.run(["defaults", "read", str(app / "Contents" / "Info.plist"), "CFBundleShortVersionString"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def _channel() -> "control.Channel":
    procs = control.processes(APP)
    if not procs:
        raise Unavailable("PhotoCraft is not running; open it with apps-open")
    port = control.flag(procs[0]["args"], "--control")
    if not port:
        raise Unavailable("PhotoCraft is running without a control port, so it cannot be driven; ask 성진 to save and quit it, then apps-open")
    token = control.flag(procs[0]["args"], "--control-token-file")
    return control.Channel(int(port), Path(token) if token else None)


def app_holds(doc: Path) -> bool | None:
    """Whether the running app has `doc` open: True, False (not running, or running without it), or None (running without a control port, so it cannot be asked)."""
    state = app_state()
    if not state["running"]:
        return False
    if state.get("control_port") is None or "documents" not in state:
        return None
    target = doc.resolve()
    return any(d.get("path") and Path(d["path"]).resolve() == target for d in state["documents"])


def app_launch(root: Path, doc: Path | None = None) -> dict:
    """Start PhotoCraft with a control port, a token file and `root` as both automation roots (paths compare as text, so give the resolved path), and open `doc` in it."""
    if control.processes(APP):
        state = app_state()
        if state.get("control_port") is None:
            raise Unavailable("PhotoCraft is already running without a control port; ask 성진 to save and quit it (do not quit it yourself), then run apps-open again")
    else:
        token = _token_file()
        token.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP_PATH), "--args", "--control", str(PORT), "--control-token-file", str(token), "--automation-read-root", str(root), "--automation-write-root", str(root)], check=True, timeout=30)
        _wait_for_port()
    opened = None
    if doc is not None:
        with _channel() as ch:
            opened = ch.result("app.open", {"path": str(doc.resolve())})
    return {"state": app_state(), "opened": opened}


def _wait_for_port(seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        procs = control.processes(APP)
        if procs and control.flag(procs[0]["args"], "--control"):
            try:
                _channel().close()
                return
            except Unavailable:
                pass
        time.sleep(0.5)
    raise Unavailable(f"PhotoCraft did not answer on its control port within {seconds:.0f}s")


def app_send(lines: list[str]) -> list[dict]:
    """Pass request lines to the running app as they are, one reply each."""
    with _channel() as ch:
        return [ch.send_line(line) for line in lines]


def app_save(doc: Path) -> dict:
    """Save `doc` in the running app to its own path (a save to another path would make that path the document's file, and later saves would land there). Brings it to the front first when it is not the active document."""
    state = app_state()
    docs = state.get("documents")
    if docs is None:
        raise Unavailable("PhotoCraft is not reachable on a control port; nothing to save from")
    target = doc.resolve()
    match = [i for i, d in enumerate(docs) if d.get("path") and Path(d["path"]).resolve() == target]
    if not match:
        raise Failure(f"PhotoCraft does not have {doc.name} open; version the file on disk instead")
    with _channel() as ch:
        switched = False
        if not docs[match[0]]["active"]:
            ch.result("engine.execute", {"command": "document.activate", "params": {"document": docs[match[0]]["index"]}})
            switched = True
        saved = ch.result("app.save", {})
    if saved and saved.get("path") and Path(saved["path"]).resolve() != target:
        raise Failure(f"PhotoCraft saved to {saved['path']}, not {doc}; check the app before going on")
    return {"saved": str(target), "switched_active_document": switched}
