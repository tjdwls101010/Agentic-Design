"""lightcraft-cli, the headless LightCraft (a Lightroom clone), as the skill uses it: a photo's develop settings in a job's library, read and written back, and the developed photo exported.

What LightCraft owns stays in here: the CLI's argv, its `{"command", "ok", "result" | "error"}` lines, the library flag, how a photo is named (its id), and how it stores a SAM 3 selection (a square grid of logits over the upright photo, quantized, deflated and base64 encoded). Callers get settings as a dict, mattes as arrays and files on disk.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
import zlib
from pathlib import Path

import numpy as np

from design import control
from design.errors import Failure, Unavailable

__all__ = ["CLI", "executable", "version", "run", "app_holds", "app_state", "app_launch", "sam_status", "settings", "restore_settings", "export", "render", "prompt_matte"]

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



def _bundle_version(app: Path) -> str | None:
    try:
        r = subprocess.run(["defaults", "read", str(app / "Contents" / "Info.plist"), "CFBundleShortVersionString"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None

APP = "LightCraft"
APP_PATH = Path("/Applications/LightCraft.app")
PORT = 7980


def app_state() -> dict:
    """{"app", "installed", "app_version", "cli_version", "running", "pid"?, "control_port"?, "library"?}. The library the app works on is the one it was started with."""
    cli = version()
    state = {"app": "lightcraft", "installed": APP_PATH.is_dir(), "app_version": _bundle_version(APP_PATH), "cli_version": cli.split(" ")[1] if cli and " " in cli else cli, "running": False}
    procs = control.processes(APP)
    if procs:
        args = procs[0]["args"]
        port = control.flag(args, "--control")
        state.update({"running": True, "pid": procs[0]["pid"], "control_port": int(port) if port else None, "library": control.flag(args, "--library")})
    return state


def app_holds(doc: Path) -> bool | None:
    """Whether the running app works on the library `doc`: True, False, or None (running on its default library, which cannot be told apart)."""
    state = app_state()
    if not state["running"]:
        return False
    if not state.get("library"):
        return None
    return Path(state["library"]).resolve() == doc.resolve()


def app_launch(library: Path) -> dict:
    """Start LightCraft on a job's library with a control port; drive it with `lightcraft-cli run --connect`."""
    if control.processes(APP):
        state = app_state()
        if state.get("library") and Path(state["library"]).resolve() == library.resolve() and state.get("control_port"):
            return {"state": state, "opened": None}
        raise Unavailable("LightCraft is already running" + (f" on {state['library']}" if state.get("library") else "") + "; ask 성진 to quit it (do not quit it yourself), then run apps-open again")
    subprocess.run(["/usr/bin/open", "-n", "-a", str(APP_PATH), "--args", "--library", str(library), "--no-demo", "--control", str(PORT)], check=True, timeout=30)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            control.Channel(PORT).close()
            return {"state": app_state(), "opened": str(library), "drive": f"lightcraft-cli run --connect 127.0.0.1:{PORT} <command> …"}
        except Unavailable:
            time.sleep(0.5)
    raise Unavailable(f"LightCraft did not answer on its control port within 30s")


LOGIT_SCALE = 8.0  # stored logits are steps of 1/8


def _logits(seg: dict) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    side = int(seg["side"])
    raw = zlib.decompress(base64.b64decode(seg["data"]), -15)  # raw deflate, no zlib header
    if len(raw) != side * side:
        raise Failure(f"LightCraft's stored selection has {len(raw)} cells, not {side}x{side}; its storage format may have changed")
    grid = np.frombuffer(raw, dtype=np.int8).astype(np.float32).reshape(side, side) / LOGIT_SCALE
    return grid, tuple(seg.get("rect") or (0.0, 0.0, 1.0, 1.0))


def _sample(grid: np.ndarray, rect, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Bilinear logits at every pixel centre of a width×height image, as LightCraft samples them, and where the grid covers."""
    side = grid.shape[0]
    xs = ((np.arange(width) + 0.5) / width - rect[0]) / (rect[2] - rect[0])
    ys = ((np.arange(height) + 0.5) / height - rect[1]) / (rect[3] - rect[1])
    fx = np.clip(xs * side - 0.5, 0, side - 1)
    fy = np.clip(ys * side - 0.5, 0, side - 1)
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    x1, y1 = np.minimum(x0 + 1, side - 1), np.minimum(y0 + 1, side - 1)
    tx, ty = (fx - x0)[None, :], (fy - y0)[:, None]
    top = grid[y0][:, x0] * (1 - tx) + grid[y0][:, x1] * tx
    bot = grid[y1][:, x0] * (1 - tx) + grid[y1][:, x1] * tx
    inside = ((xs >= 0) & (xs <= 1))[None, :] & ((ys >= 0) & (ys <= 1))[:, None]
    return top * (1 - ty) + bot * ty, inside


def prompt_matte(photo: Path, text: str, width: int, height: int) -> tuple[np.ndarray, float]:
    """What SAM 3 selects in `photo` for an English description, as an 8-bit matte of width×height over the upright photo. The model understands English only; a description it finds nothing for is a Failure. The stored grid is coarse (a few hundred cells a side), so edges are soft at full resolution; the second value is how many photo pixels one cell spans."""
    with tempfile.TemporaryDirectory(prefix="design-sam-") as tmp:
        library = Path(tmp) / "library"
        (result,) = run(library, [("library.import", {"paths": [str(photo)], "mode": "add"})])[:1]
        if not (result or {}).get("imported"):
            raise Failure(f"LightCraft could not import {photo.name} to analyse it: {result}")
        try:
            run(library, [("library.selectAll", {}), ("mask.add", {"kind": "prompt", "text": text})])
        except Failure as exc:
            raise Failure(f"SAM 3 found nothing for {text!r} ({exc.message}); describe it in English, by what it looks like") from exc
        settings = run(library, [("library.selectAll", {}), ("develop.get", {})])[-1]
    comps = [c for m in settings.get("masks", []) for c in m.get("components", []) if c.get("shape", {}).get("kind") == "prompt"]
    if not comps:
        raise Failure("LightCraft made no prompt selection; its settings format may have changed")
    shape = comps[-1]["shape"]
    logits = np.full((height, width), -16.0, np.float32)
    cell = float(max(width, height))
    if shape.get("seg"):
        cell = max(width, height) / int(shape["seg"]["side"])
        grid, rect = _logits(shape["seg"])
        logits, _ = _sample(grid, rect, width, height)
    fine = None
    for patch in shape.get("detail") or []:
        grid, rect = _logits(patch)
        value, inside = _sample(grid, rect, width, height)
        value = np.where(inside, value, -np.inf)
        fine = value if fine is None else np.maximum(fine, value)
    if fine is not None:
        logits = np.where(np.isfinite(fine), fine, logits)
    return np.round(255 / (1 + np.exp(-logits))).astype(np.uint8), cell


def sam_status() -> dict:
    """{"installed": bool, "detail"?}: whether LightCraft's SAM 3 model (Object and Describe masks) is in place."""
    if not executable():
        return {"installed": False, "detail": f"{CLI} is not on PATH"}
    r = subprocess.run([CLI, "run", "segment.model.status"], capture_output=True, text=True, timeout=60)
    for line in r.stdout.splitlines():
        if line.strip().startswith("{"):
            result = (json.loads(line).get("result") or {})
            return {"installed": bool(result.get("installed")), "dir": result.get("dir")}
    return {"installed": False, "detail": r.stderr.strip()[-200:]}
