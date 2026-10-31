"""photocraft-cli, the headless PhotoCraft (a Photoshop clone), as the skill uses it.

What PhotoCraft owns stays in here: the CLI's argv, its one-JSON-line-per-step output, how it reports a failed step, and the shapes of the results the skill reads (font faces, type layer info, the document tree). Callers get plain dicts and lists in the skill's terms.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "font_faces"]

CLI = "photocraft-cli"


def executable() -> str | None:
    return shutil.which(CLI)


def version() -> str | None:
    try:
        r = subprocess.run([CLI, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def run(steps: list[tuple[str, dict]], *, file: Path | None = None, new: dict | None = None, out: Path | None = None, in_place: bool = False, timeout: float = 600) -> list[dict]:
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
