"""photocraft-cli, the headless PhotoCraft (a Photoshop clone), as the skill uses it.

What PhotoCraft owns stays in here: the CLI's argv, its one-JSON-line-per-step output, how it reports a failed step, and the shapes of the results the skill reads (font faces, type layer info, the document tree). Callers get plain dicts and lists in the skill's terms.

A linked smart object renders from the pixels cached in the document: a linked file that changed shows only after an update step, and one that is missing still renders from the cache without a word. So every render here updates linked content first, and `links` says which linked files exist.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "app_holds", "font_faces", "info", "layers", "links", "type_runs", "render", "UPDATE_LINKS"]

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
                results.append(json.loads(line).get("result"))
            except json.JSONDecodeError:
                continue
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
    r = subprocess.run([CLI, "info", str(doc)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise Failure(f"{CLI} info could not read {doc}: {(r.stderr or r.stdout).strip()[-400:]}")
    return json.loads(r.stdout)


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


def app_holds(doc: Path) -> bool | None:
    """Whether the running app has `doc` open: True, False (not running, or running without it), or None (running without a control port, so it cannot be asked)."""
    return False  # 성진: replaced by the control-channel query in the apps step; until then nothing is detected
