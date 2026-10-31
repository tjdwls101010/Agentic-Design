"""lightcraft-cli, the headless LightCraft (a Lightroom clone), as the skill uses it: a photo's develop settings in a job's library, read and written back, and the developed photo exported.

What LightCraft owns stays in here: the CLI's argv, its `{"command", "ok", "result" | "error"}` lines, the library flag, and how a photo is named (its id). Callers get settings as a dict and files on disk.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "app_holds", "settings", "restore_settings", "export", "render"]

CLI = "lightcraft-cli"


def executable() -> str | None:
    return shutil.which(CLI)


def version() -> str | None:
    try:
        r = subprocess.run([CLI, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def run(library: Path, commands: list[tuple[str, dict]], timeout: float = 600) -> list[dict]:
    """Run commands against a library, in order, stopping at the first failure. Returns each command's result."""
    if not executable():
        raise Unavailable(f"{CLI} is not on PATH; install it (doctor checks the environment)")
    script = "\n".join(json.dumps({"command": c, "params": p}, ensure_ascii=False) for c, p in commands) + "\n"
    r = subprocess.run([CLI, "run", "--library", str(library), "--script", "-"], input=script, capture_output=True, text=True, timeout=timeout)
    lines = [json.loads(l) for l in r.stdout.splitlines() if l.strip().startswith("{")]
    failed = [l for l in lines if not l.get("ok")]
    if failed or r.returncode != 0:
        first = failed[0] if failed else {}
        raise Failure(f"{CLI} {first.get('command', 'run')} failed: {first.get('error') or r.stderr.strip()[-400:]}")
    return [l.get("result") for l in lines]


def settings(library: Path, photo_id: str) -> dict:
    """A photo's full develop settings (sliders, curves, masks) as LightCraft stores them."""
    (result,) = run(library, [("develop.get", {"id": photo_id})])
    return result


def restore_settings(library: Path, photo_id: str, saved: dict) -> None:
    """Put saved develop settings back on a photo: reset, then merge the saved settings."""
    run(library, [("library.select", {"ids": [photo_id], "active": photo_id}), ("develop.reset", {"ids": [photo_id]}), ("develop.merge", {"settings": saved, "label": "restore"})])


def export(library: Path, photo_id: str, out: Path, *, long_edge: int = 0, quality: int = 95) -> None:
    """Export the developed photo as 8-bit sRGB (format by `out`'s extension); long_edge 0 keeps the full size."""
    run(library, [("app.export", {"ids": [photo_id], "path": str(out), "longEdge": long_edge, "quality": quality, "colorSpace": "srgb", "bitDepth": 8, "conflict": "skip"})])


def render(photo: Path, out: Path, *, settings_file: Path, long_edge: int = 0, quality: int = 95) -> None:
    """Develop the original `photo` with saved settings, outside any library, as 8-bit sRGB (format by `out`'s extension); long_edge 0 keeps the full size."""
    if not executable():
        raise Unavailable(f"{CLI} is not on PATH; install it (doctor checks the environment)")
    argv = [CLI, "render", str(photo), "-o", str(out), "--settings", str(settings_file), "--quality", str(quality), "--opt", "bitDepth=8", "--opt", "colorSpace=srgb"]
    if long_edge:
        argv += ["--size", str(long_edge)]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise Failure(f"{CLI} render failed: {r.stderr.strip()[-400:]}")


def app_holds(doc: Path) -> bool | None:
    """Whether the running app has `doc` open: True, False (not running, or running without it), or None (running without a control port, so it cannot be asked)."""
    return False  # 성진: replaced by the control-channel query in the apps step; until then nothing is detected
