"""vectorcraft-cli, the headless VectorCraft (an Illustrator clone), as the skill uses it.

What VectorCraft owns stays in here: the CLI's argv, its one-JSON-line-per-step output and the shapes of the results the skill reads. Callers get plain dicts and lists in the skill's terms.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "app_holds", "font_styles", "info", "texts", "render"]

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
        (result,) = run([("text.fontList", {"family": family})])
    except Failure as exc:
        if "is not available" in exc.message:  # an unknown family is a parameter error to VectorCraft
            return []
        raise
    if not isinstance(result, dict) or result.get("family") is None:
        return []
    return list(result.get("styles") or [])


def info(doc: Path) -> dict:
    """The document summary: artboards [{"name", "rect": [x0, y0, x1, y1]}] in points, fonts [{"family", "style", "status": exact | substitute | missing, "resolved", "missingGlyphs"}], object kinds."""
    if not executable():
        raise Unavailable(f"{CLI} is not on PATH; install it (doctor checks the environment)")
    r = subprocess.run([CLI, "info", str(doc)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise Failure(f"{CLI} info could not read {doc}: {(r.stderr or r.stdout).strip()[-400:]}")
    return json.loads(r.stdout)


def texts(doc: Path) -> tuple[list[dict], dict]:
    """Every type object top-down [{"id", "name", "text", "visible", "bounds": {x, y, width, height}}], and what opening the file reported (missingLinks, modifiedLinks)."""
    argv = [CLI, "run", "--in", str(doc), "--cmd", "document.inspect"]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise Failure(f"{CLI} could not inspect {doc}: {(r.stderr or r.stdout).strip()[-400:]}")
    opened, inspected = {}, {}
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            doc_line = json.loads(line)
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
    argv = [CLI, "run", "--in", str(doc), "--export", str(out), "--scale", str(scale)]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise Failure(f"{CLI} could not export {doc}: {(r.stderr or r.stdout).strip()[-400:]}")
    warnings = []
    for line in r.stdout.splitlines():
        if line.startswith("{"):
            d = json.loads(line)
            if d.get("step") == "export":
                warnings += (d.get("result") or {}).get("warnings", [])
    return warnings


def app_holds(doc: Path) -> bool | None:
    """Whether the running app has `doc` open: True, False (not running, or running without it), or None (running without a control port, so it cannot be asked)."""
    return False  # 성진: replaced by the control-channel query in the apps step; until then nothing is detected
