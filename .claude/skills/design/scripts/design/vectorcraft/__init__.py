"""vectorcraft-cli, the headless VectorCraft (an Illustrator clone), as the skill uses it.

What VectorCraft owns stays in here: the CLI's argv, its one-JSON-line-per-step output and the shapes of the results the skill reads. Callers get plain dicts and lists in the skill's terms.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "font_styles"]

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
