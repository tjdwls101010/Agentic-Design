"""vectorcraft-cli, the headless VectorCraft (an Illustrator clone), as the skill uses it.

What VectorCraft owns stays in here: the CLI's argv, its one-JSON-line-per-step output and the shapes of the results the skill reads. Callers get plain dicts and lists in the skill's terms.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from design import control
from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "app_holds", "app_state", "app_launch", "app_send", "app_save", "font_styles", "info", "texts", "text_runs", "render"]

CLI = "vectorcraft-cli"


def executable() -> str | None:
    return shutil.which(CLI)


def version() -> str | None:
    try:
        r = subprocess.run([CLI, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def run(steps: list[tuple[str, dict]], *, file: Path | None = None, exports: list[Path] = (), scale: float | None = None, timeout: float = 600) -> list[dict]:
    """One `vectorcraft-cli run`: open `file` (or a new document), run the steps, write each export. Returns the steps' results in order."""
    if not executable():
        raise Unavailable(f"{CLI} is not on PATH; install it (doctor checks the environment)")
    argv = [CLI, "run"] + (["--in", str(file)] if file is not None else [])
    for command, params in steps:
        argv += ["--cmd", command, "--params", json.dumps(params, ensure_ascii=False)]
    for path in exports:
        argv += ["--export", str(path)]
    if scale is not None:
        argv += ["--scale", str(scale)]
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
            if doc.get("step") == "cmd" or "command" in doc:
                results.append(doc.get("result"))
    return results


def font_styles(family: str) -> list[str]:
    """The styles VectorCraft lists under a family name; empty when it does not know the family."""
    try:
        result = (run([("text.fontList", {"family": family})]) or [None])[0]
    except Failure as exc:
        if "is not available" in exc.message:  # an unknown family is a parameter error to VectorCraft
            return []
        raise
    if not isinstance(result, dict) or result.get("family") is None:
        return []
    return list(result.get("styles") or [])


def _call(argv: list[str], what: str, timeout: float = 600) -> str:
    if not executable():
        raise Unavailable(f"{CLI} is not on PATH; install it (doctor checks the environment)")
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise Failure(f"{CLI} {what} did not finish within {timeout:.0f}s") from exc
    if r.returncode != 0:
        raise Failure(f"{CLI} could not {what}: {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout


def _lines(stdout: str) -> list[dict]:
    out = []
    for line in stdout.splitlines():
        if line.strip().startswith("{"):
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(doc, dict):
                out.append(doc)
    return out


def info(doc: Path) -> dict:
    """The document summary: artboards [{"name", "rect": [x0, y0, x1, y1]}] in points, fonts [{"family", "style", "status": exact | substitute | missing, "resolved", "missingGlyphs"}], object kinds."""
    out = _call([CLI, "info", str(doc)], f"read {doc.name}", 300)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise Failure(f"{CLI} info printed something other than JSON; its output format may have changed ({exc})") from exc


def texts(doc: Path) -> tuple[list[dict], dict]:
    """Every type object top-down [{"id", "name", "text", "visible", "bounds": {x, y, width, height}}], and what opening the file reported (missingLinks, modifiedLinks)."""
    opened, inspected = {}, {}
    for doc_line in _lines(_call([CLI, "run", "--in", str(doc), "--cmd", "document.inspect"], f"inspect {doc.name}", 300)):
        if doc_line.get("step") == "open":
            opened = doc_line.get("result") or {}
        elif doc_line.get("command") == "document.inspect":
            inspected = doc_line.get("result") or {}
    out = []

    def walk(items):
        for item in items:
            if item.get("kind") == "Type":
                out.append({"id": item.get("id"), "name": item.get("name"), "text": item.get("text", ""), "visible": item.get("visible", True), "bounds": item.get("bounds")})
            walk(item.get("children") or [])

    walk(inspected.get("layers") or [])
    return out, {k: opened.get(k, []) for k in ("missingLinks", "modifiedLinks")}


def render(doc: Path, out: Path, *, scale: float = 1) -> list[str]:
    """Export `doc`'s first artboard to an image (format by `out`'s extension) at `scale` pixels per point; returns the export's warnings (text that does not fit its frame, …)."""
    warnings = []
    for d in _lines(_call([CLI, "run", "--in", str(doc), "--export", str(out), "--scale", str(scale)], f"export {doc.name}")):
        if d.get("step") == "export":
            warnings += (d.get("result") or {}).get("warnings", [])
    return warnings


def text_runs(doc: Path, ids: list[int]) -> dict[int, list[dict]]:
    """Each type object's style runs: {"text", "family", "style"} as stored."""
    if not ids:
        return {}
    argv = [CLI, "run", "--in", str(doc)]
    for i in ids:
        argv += ["--cmd", "text.getRange", "--params", json.dumps({"id": i})]
    results = [d.get("result") or {} for d in _lines(_call(argv, f"read the type of {doc.name}", 300)) if d.get("command") == "text.getRange"]
    return {i: [{"text": r.get("text", ""), "family": (r.get("style") or {}).get("font_family"), "style": (r.get("style") or {}).get("font_style")} for r in res.get("runs", [])] for i, res in zip(ids, results)}



def _bundle_version(app: Path) -> str | None:
    try:
        r = subprocess.run(["defaults", "read", str(app / "Contents" / "Info.plist"), "CFBundleShortVersionString"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None

APP = "VectorCraft"
APP_PATH = Path("/Applications/VectorCraft.app")
PORT = 7979


def app_state() -> dict:
    """{"app", "installed", "app_version", "cli_version", "running", "pid"?, "control_port"?, "documents"?: [{"title", "dirty", "active"}], "roots"?}. VectorCraft lists open documents by title (the file name), not path."""
    cli = version()
    state = {"app": "vectorcraft", "installed": APP_PATH.is_dir(), "app_version": _bundle_version(APP_PATH), "cli_version": cli.split(" ")[1] if cli and " " in cli else cli, "running": False}
    procs = control.processes(APP)
    if not procs:
        return state
    args = procs[0]["args"]
    state.update({"running": True, "pid": procs[0]["pid"], "control_port": None})
    port = control.flag(args, "--control")
    if port:
        state["control_port"] = int(port)
        state["roots"] = {"read": control.flag(args, "--automation-read-root"), "write": control.flag(args, "--automation-write-root")}
        try:
            with control.Channel(int(port)) as ch:
                inspected = ch.result("ui.inspect") or {}
            active = inspected.get("activeDocument")
            state["documents"] = [{"title": d.get("title"), "dirty": d.get("dirty"), "active": i == active} for i, d in enumerate(inspected.get("documents", []))]
        except (Unavailable, Failure) as exc:
            state["error"] = exc.message
    return state


def _channel() -> "control.Channel":
    procs = control.processes(APP)
    if not procs:
        raise Unavailable("VectorCraft is not running; open it with apps-open")
    port = control.flag(procs[0]["args"], "--control")
    if not port:
        raise Unavailable("VectorCraft is running without a control port, so it cannot be driven; ask 성진 to save and quit it, then apps-open")
    return control.Channel(int(port))


def app_holds(doc: Path) -> bool | None:
    """Whether the running app has a document of `doc`'s file name open: True, False, or None (running without a control port). VectorCraft reports titles only, so a same-named file elsewhere counts too."""
    state = app_state()
    if not state["running"]:
        return False
    if state.get("control_port") is None or "documents" not in state:
        return None
    return any(d.get("title") == doc.name for d in state["documents"])


def app_launch(root: Path, doc: Path | None = None) -> dict:
    """Start VectorCraft with a control port and `root` as both automation roots, and open `doc` (VectorCraft takes absolute paths only)."""
    if control.processes(APP):
        if app_state().get("control_port") is None:
            raise Unavailable("VectorCraft is already running without a control port; ask 성진 to save and quit it (do not quit it yourself), then run apps-open again")
    else:
        subprocess.run(["/usr/bin/open", "-n", "-a", str(APP_PATH), "--args", "--control", str(PORT), "--automation-read-root", str(root), "--automation-write-root", str(root)], check=True, timeout=30)
        deadline = time.monotonic() + 30
        while True:
            try:
                _channel().close()
                break
            except Unavailable:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
    opened = None
    if doc is not None:
        with _channel() as ch:
            opened = ch.result("app.open", {"path": str(doc.resolve())})
    return {"state": app_state(), "opened": opened}


def app_send(lines: list[str]) -> list[dict]:
    """Pass request lines to the running app as they are, one reply each."""
    with _channel() as ch:
        return [ch.send_line(line) for line in lines]


def app_save(doc: Path) -> dict:
    """Save the open document titled like `doc` to its own path, waiting for the write; brings it to the front first when needed."""
    state = app_state()
    docs = state.get("documents")
    if docs is None:
        raise Unavailable("VectorCraft is not reachable on a control port; nothing to save from")
    match = [i for i, d in enumerate(docs) if d.get("title") == doc.name]
    if not match:
        raise Failure(f"VectorCraft does not have {doc.name} open; version the file on disk instead")
    if len(match) > 1:
        raise Failure(f"VectorCraft has {len(match)} documents titled {doc.name} and names none by path, so which one to save cannot be told; ask 성진 to close the others")
    with _channel() as ch:
        switched = False
        if not docs[match[0]]["active"]:
            ch.result("engine.execute", {"command": "document.activate", "params": {"index": match[0]}})
            switched = True
        saved = ch.result("app.save", {"wait": True}) or {}
    if isinstance(saved, dict) and saved.get("path") and Path(saved["path"]).resolve() != doc.resolve():
        raise Failure(f"VectorCraft saved {saved['path']}, not {doc}; check the app before going on")
    return {"saved": str(doc), "switched_active_document": switched}
