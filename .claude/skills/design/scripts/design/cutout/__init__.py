"""Cutting a person or an object out of a photo as a matte, and putting the matte on the photo's layer in a PhotoCraft document as a layer mask 성진 can refine by hand.

PhotoCraft has no model: its Select Subject is a heuristic that takes walls and people behind. The edge here comes from macOS Vision (person segmentation at full resolution, hair included) and who is kept from Vision's person numbers or from a SAM 3 description run through LightCraft, which picks one named person or an object Vision cannot name. A matte drawn by hand, or fixed by hand, comes in as it is.

The matte is placed by the photo layer's bounds in the document: the layer must show the whole photo unrotated (a linked smart object placed and scaled, not rotated or cropped by a transform).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from design import ledger, lightcraft, paths, photocraft, vision
from design.errors import BadInput, Conflict, Failure, Usage

__all__ = ["cutout"]

# How far past a selection's own edge Vision's edge may reach, in cells of the selection's grid: a coarse selection is unsure by about a cell, and reaching further lets in what stands next to the person (a microphone, someone behind), which Vision's person matte includes.
REACH_CELLS = 1.5


def _upright(path: Path) -> Image.Image:
    try:
        im = Image.open(path)
        im.seek(0)
        im.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BadInput(f"cannot read {path} as an image ({exc})") from exc
    return ImageOps.exif_transpose(im).convert("RGB")


def _reach(region: np.ndarray, cell: float) -> np.ndarray:
    """`region` (0..255) grown by REACH_CELLS of its grid's cells and softened, worked at a reduced size so it stays cheap."""
    h, w = region.shape
    scale = min(1.0, 1024 / max(h, w))
    small = Image.fromarray(region).resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR)
    k = max(3, int(2 * REACH_CELLS * cell * scale) | 1)
    grown = small.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.GaussianBlur(k / 4))
    return np.asarray(grown.resize((w, h), Image.BILINEAR))


def _matte(photo: Image.Image, src: Path, *, kind: str, instance: int | None, select: str | None) -> tuple[np.ndarray, dict]:
    W, H = photo.size
    stats: dict = {}
    scene = vision.run(np.asarray(photo))
    stats["people"] = scene.people_count
    if kind == "person" and scene.people_count == 0 and select is None:
        raise Failure("Vision found no person in this photo; give --kind subject, --select a description, or --matte a matte drawn by hand", people=0)
    if select is not None:
        chosen, cell = lightcraft.prompt_matte(src, select, W, H)
        stats["selected_by"] = f"SAM 3: {select!r}"
        if kind == "subject":
            return chosen, stats  # SAM's own edge: coarse but it keeps what it was told to (a held microphone, a sign)
        base = scene.person
        return np.minimum(base, _reach(chosen, cell)).astype(np.uint8), stats
    base = scene.person if kind == "person" else scene.subject
    if instance is not None:
        if kind != "person":
            raise Usage("--instance numbers people; give --kind person, or --select for an object")
        if not 1 <= instance <= scene.people_count:
            raise Failure(f"person {instance} does not exist: Vision numbered {scene.people_count} people, left to right", people=scene.people_count)
        region = np.where(scene.people == instance, 255, 0).astype(np.uint8)
        stats["selected_by"] = f"Vision person {instance} of {scene.people_count}"
        return np.minimum(base, _reach(region, scene.cell)).astype(np.uint8), stats
    stats["selected_by"] = "Vision: every person" if kind == "person" else "Vision: every foreground subject"
    return base, stats


def _new_asset(job_dir: Path, stem: str, suffix: str) -> Path:
    assets = job_dir / "assets"
    assets.mkdir(exist_ok=True)
    taken = [int(m[1] or 1) for p in assets.iterdir() if (m := re.fullmatch(re.escape(stem) + r"(?:-(\d+))?" + re.escape(suffix), p.name))]
    n = max(taken, default=0) + 1
    return assets / (f"{stem}{suffix}" if n == 1 else f"{stem}-{n}{suffix}")


def _attach(doc: Path, layer_name: str, src: Path, matte: Image.Image, scratch: Path) -> dict:
    """Paste the matte, placed by the layer's bounds on a canvas-size black ground, into that layer's mask."""
    info = photocraft.info(doc)
    layers = [l for l in photocraft.layers(info) if l["name"] == layer_name]
    if len(layers) != 1:
        raise Failure(f"{doc.name} has {len(layers)} layers named {layer_name!r}; name the photo layer exactly (layers: {', '.join(repr(l['name']) for l in photocraft.layers(info))})")
    layer = layers[0]
    if layer.get("linked") and Path(layer["linked"]).resolve() != src.resolve():
        raise Failure(f"layer {layer_name!r} links {layer['linked']}, not {src}; the matte belongs to the photo it was made from")
    if not layer.get("bounds"):
        raise Failure(f"layer {layer_name!r} is a {layer['kind']} with no pixel bounds; name the photo's own layer")
    x, y, w, h = layer["bounds"]
    if abs((w / h) / (matte.width / matte.height) - 1) > 0.01:
        raise Failure(f"layer {layer_name!r} is {w}x{h} on the canvas, not the photo's {matte.width}:{matte.height} shape: it is cropped, rotated or clipped, so the matte would not line up. Put the photo in whole (linked, scaled only) or attach the matte in the app", bounds=[x, y, w, h])
    # 성진: bounds place the matte for a scaled, unrotated layer; a rotated or skewed smart object needs its transform matrix, which info does not give.
    canvas = Image.new("L", (info["width"], info["height"]), 0)
    canvas.paste(matte.resize((round(w), round(h)), Image.LANCZOS), (round(x), round(y)))
    canvas_path = scratch / f".mask-{uuid.uuid4().hex[:8]}.png"
    canvas.save(canvas_path)
    try:
        steps = [("layer.select", {"layer": layer["id"]})]
        if _has_mask(info, layer["id"]):  # a second cut replaces the first
            steps.append(("layer.layerMask.delete", {}))
        steps += [("file.openAs", {"path": str(canvas_path)}), ("select.all", {}), ("edit.copy", {}), ("file.close", {}), ("document.activate", {"document": 0}), ("layer.select", {"layer": layer["id"]}), ("layer.layerMask.revealAll", {}), ("edit.paste", {"target": "mask"})]
        photocraft.run(steps, file=doc, out=doc, in_place=True)
    finally:
        canvas_path.unlink(missing_ok=True)
    return {"doc": str(doc), "layer": layer_name, "placed_at": [x, y, w, h]}


def _guard_hand_edits(job_dir: Path, doc: Path, layer_name: str) -> None:
    """Replacing a layer's mask throws away whatever was painted into it; when the document holds edits no version has, that may be 성진's hand work, so it is versioned first."""
    latest = ledger.latest_for(ledger.read(job_dir), paths.stored(job_dir, doc))
    if latest is not None and paths.from_stored(job_dir, latest["snapshot"]).read_bytes() == doc.read_bytes():
        return
    info = photocraft.info(doc)
    target = [l for l in photocraft.layers(info) if l["name"] == layer_name]
    if target and _has_mask(info, target[0]["id"]):
        raise Conflict(f"layer {layer_name!r} already has a mask and {doc.name} holds edits no version has (perhaps a mask painted by hand); version the document first, then cut again")


def _has_mask(info: dict, layer_id: int) -> bool:
    def walk(items):
        for l in items:
            if l.get("id") == layer_id:
                return bool(l.get("hasMask"))
            found = walk(l.get("children") or [])
            if found is not None:
                return found
        return None

    return bool(walk(info.get("layers") or []))


def cutout(job_dir: Path, src: Path, *, kind: str, instance: int | None, select: str | None, matte_file: Path | None, doc: Path | None, layer: str | None, choke: int = 0) -> dict:
    photo = _upright(src)
    W, H = photo.size
    if matte_file is not None:
        given = _upright(matte_file).convert("L")
        if given.size != (W, H):
            raise Usage(f"--matte is {given.size[0]}x{given.size[1]} and the upright photo {W}x{H}; a matte covers the photo pixel for pixel")
        matte, stats = np.asarray(given), {"selected_by": f"given matte {matte_file.name}"}
    else:
        matte, stats = _matte(photo, src, kind=kind, instance=instance, select=select)
    if choke:
        # A soft edge made against a bright ground carries that ground's light into the rim of dark hair; pulling the edge in by a pixel or two removes the rim.
        matte = np.asarray(Image.fromarray(matte).filter(ImageFilter.MinFilter(2 * choke + 1)))
    out = _new_asset(job_dir, f"{src.stem}_matte", ".png")
    paths.place_new(out, lambda tmp: Image.fromarray(matte).save(tmp))
    covered = matte >= 128
    soft = (matte > 10) & (matte < 245)
    rows, cols = np.nonzero(covered)
    result = {"summary": f"{covered.mean():.0%} of the photo kept ({stats['selected_by']})", "matte": str(out), "size": [W, H], "coverage": round(float(covered.mean()), 4), "edge_share": round(float(soft.sum() / max(1, covered.sum())), 4), "box": [int(cols.min()), int(rows.min()), int(cols.max() - cols.min() + 1), int(rows.max() - rows.min() + 1)] if rows.size else None, **stats}
    if not covered.any():
        raise Failure("the matte keeps nothing; try another --instance or --select", **result)
    if doc is not None:
        if layer is None:
            raise Usage("--doc needs --layer: the name of the photo's layer in that document")
        try:
            doc.resolve().relative_to((job_dir / "work").resolve())
        except ValueError:
            raise Usage(f"{doc} is not in this job's work/; the matte goes on the current document, never on a version's snapshot or another job's file") from None
        held = photocraft.app_holds(doc)
        if held is not False:
            raise Conflict(f"PhotoCraft {'has' if held else 'may have'} {doc.name} open: a mask written on disk would be overwritten by the app's next save. Ask 성진 to save and close it, then run this again")
        _guard_hand_edits(job_dir, doc, layer)
        result["attached"] = _attach(doc, layer, src, Image.fromarray(matte), job_dir / "etc")
        result["summary"] += f"; mask on layer {layer!r} of {doc.name}"
    result["next"] = "look at the edge at 100% (proof --crop on hair, hands, glasses, held objects); fix the mask in the app or with a corrected --matte"
    return result
