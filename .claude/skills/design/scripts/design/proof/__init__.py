"""Check sheets for the current document: what it looks like at the size people see it and at 100%, which fonts and characters actually rendered, which strings are on it, and what sits outside the canvas or links to a missing file.

Each call writes a fresh numbered folder under the job's proof/, so a path returned earlier is never overwritten; the folder is disposable. A font a type layer asks for can silently become another face (a missing style turns into Regular) and a character the face lacks or draws empty prints in a fallback font or as a gap; the render alone does not say which, so the PostScript name and the glyphs are read here.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from design import glyphs, paths, photocraft, platforms, vectorcraft
from design.errors import Failure, Usage

__all__ = ["proof"]

LABEL_FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")


def _folder(job_dir: Path) -> Path:
    root = job_dir / "proof"
    root.mkdir(exist_ok=True)
    n = max((int(m[1]) for p in root.iterdir() if (m := re.fullmatch(r"(\d+)", p.name))), default=0) + 1
    while True:
        try:
            (root / str(n)).mkdir()
            return root / str(n)
        except FileExistsError:
            n += 1


def _label(draw: ImageDraw.ImageDraw, xy, text: str, size: int = 18) -> None:
    try:
        font = ImageFont.truetype(LABEL_FONT, size)
    except OSError:
        font = ImageFont.load_default()
    x, y = xy
    box = draw.textbbox((x, y), text, font=font)
    draw.rectangle((box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3), fill=(0, 0, 0, 190))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))


def _views(full: Image.Image, widths: tuple[int, ...], out: Path) -> None:
    """The render at each on-screen width, side by side at their real pixel size, on a feed-grey ground."""
    shots = [full.resize((w, max(1, round(full.height * w / full.width))), Image.LANCZOS) for w in widths]
    pad = 24
    sheet = Image.new("RGB", (sum(s.width for s in shots) + pad * (len(shots) + 1), max(s.height for s in shots) + pad * 2 + 30), (238, 238, 238))
    draw = ImageDraw.Draw(sheet, "RGBA")
    x = pad
    for w, shot in zip(widths, shots):
        sheet.paste(shot.convert("RGB"), (x, pad + 30))
        _label(draw, (x, 4), f"{w}px wide", 16)
        x += shot.width + pad
    sheet.save(out)


def _zones(full: Image.Image, platform: platforms.Platform, out: Path) -> None:
    shown = full.convert("RGBA").resize((1080, round(full.height * 1080 / full.width)), Image.LANCZOS) if full.width > 1080 else full.convert("RGBA")
    layer = Image.new("RGBA", shown.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    W, H = shown.size
    for zone in platform.zones:
        x, y, w, h = zone.box
        box = (round(x * W), round(y * H), round((x + w) * W), round((y + h) * H))
        draw.rectangle(box, fill=(255, 0, 60, 70), outline=(255, 0, 60, 255), width=3)
        _label(draw, (box[0] + 6, box[1] + 6), zone.name + ("" if zone.official else " (unofficial)"), 16)
    Image.alpha_composite(shown, layer).convert("RGB").save(out)


def _crop(full: Image.Image, box: tuple[int, int, int, int], out: Path) -> None:
    x, y, w, h = box
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > full.width or y + h > full.height:
        raise Usage(f"--crop {x},{y},{w},{h} is not inside the {full.width}x{full.height} render")
    full.crop((x, y, x + w, y + h)).save(out)


def _photocraft_checks(doc: Path) -> dict:
    info = photocraft.info(doc)
    W, H = info["width"], info["height"]
    layers = photocraft.layers(info)
    types = [l for l in layers if l["kind"] == "Type"]
    runs = photocraft.type_runs(doc, [l["id"] for l in types])
    faces_by_family: dict[str, list[dict]] = {}
    fonts, gaps = [], []
    for layer in types:
        for run in runs.get(layer["id"], []):
            family, style, actual = run["family"], run["style"], run["postscript"]
            if family not in faces_by_family:
                faces_by_family[family] = photocraft.font_faces(family) if family else []
            expected = next((f["postscript"] for f in faces_by_family[family] if f["style"] == style), None)
            row = {"layer": layer["name"], "requested": f"{family} {style}", "actual": actual, "fallback": expected is None or expected != actual}
            if row["fallback"]:
                row["why"] = f"PhotoCraft has no {family!r} family" if not faces_by_family[family] else f"{family!r} has no {style!r} style (has: {', '.join(f['style'] for f in faces_by_family[family])})" if expected is None else f"expected {expected}"
            fonts.append(row)
            gap = glyphs.gaps(actual, run["text"]) if actual else None
            if gap and (gap["missing"] or gap["blank"]):
                gaps.append({"layer": layer["name"], "postscript": actual, **gap})
    outside = []
    for l in layers:
        b = l.get("bounds")
        if not b or l["kind"] in ("Group",) or not l["visible"] or l["name"] == "Background":
            continue
        x, y, w, h = b
        if x >= W or y >= H or x + w <= 0 or y + h <= 0:
            outside.append({"layer": l["name"], "kind": l["kind"], "where": "entirely outside the canvas"})
        elif x < 0 or y < 0 or x + w > W or y + h > H:
            outside.append({"layer": l["name"], "kind": l["kind"], "where": "partly outside the canvas"})
    strings = [{"layer": l["name"], "text": l.get("text", "")} for l in types if l["visible"]]
    return {"size": [W, H], "fonts": fonts, "glyph_gaps": gaps, "strings": strings, "outside": outside, "missing_links": [l for l in photocraft.links(info) if not l["exists"]]}


def _vectorcraft_checks(doc: Path) -> dict:
    info = vectorcraft.info(doc)
    texts, opened = vectorcraft.texts(doc)
    fonts = [{"requested": f"{f['family']} {f['style']}", "actual": f"{f['resolved']['family']} {f['resolved']['style']}", "fallback": f["status"] != "exact", "missing_glyphs": f.get("missingGlyphs", 0)} for f in info.get("fonts", [])]
    return {"fonts": fonts, "glyph_gaps": [], "strings": [{"layer": t["name"], "text": t["text"]} for t in texts if t["visible"]], "outside": [], "missing_links": opened.get("missingLinks", [])}


def _missing_brief_text(brief: list[str], strings: list[dict]) -> list[str]:
    """Strings the brief requires that no visible type layer holds, comparing with whitespace and line breaks collapsed."""
    def flat(s: str) -> str:
        return " ".join(s.split())

    have = [flat(s["text"]) for s in strings]
    joined = flat(" ".join(s["text"] for s in strings))
    return [t for t in brief if not any(flat(t) in h for h in have) and flat(t) not in joined]


def proof(job_dir: Path, brief: dict, *, doc: Path, target: str | None, crops: list[tuple[int, int, int, int]]) -> dict:
    if not doc.exists():
        raise Failure(f"{doc} does not exist")
    out = _folder(job_dir)
    full_path = out / "full.png"
    checks: dict = {}
    if doc.suffix == ".pcraft":
        checks = _photocraft_checks(doc)
        photocraft.render(doc, full_path)
    elif doc.suffix == ".vectorcraft":
        checks = _vectorcraft_checks(doc)
        checks["export_warnings"] = vectorcraft.render(doc, full_path)
    elif doc.suffix.lower() in IMAGE_SUFFIXES:
        with Image.open(doc) as im:
            im.convert("RGBA").save(full_path)
    else:
        raise Usage(f"{doc.name}: proof reads a .pcraft, a .vectorcraft or an image")
    full = Image.open(full_path)
    read = [str(full_path)]
    name = target or brief.get("platform")
    platform = platforms.get(name) if name else None
    widths = platform.views if platform else (360,)
    _views(full, widths, out / "views.png")
    read.insert(0, str(out / "views.png"))
    if platform and platform.zones:
        _zones(full, platform, out / "zones.png")
        read.insert(1, str(out / "zones.png"))
    for i, box in enumerate(crops, 1):
        _crop(full, box, out / f"crop-{i}.png")
        read.append(str(out / f"crop-{i}.png"))
    result = {"dir": str(out), "read": read, "render_size": list(full.size)}
    if platform:
        want = platform.aspect[0] / platform.aspect[1]
        if abs(full.width / full.height / want - 1) > platforms.ASPECT_TOLERANCE:
            checks.setdefault("platform", []).append(f"{full.width}x{full.height} is not {platform.aspect[0]}:{platform.aspect[1]} ({platform.name})")
        result["platform_notes"] = list(platform.notes)
    result.update(checks)
    if brief.get("text") and "strings" in checks:
        result["brief_text_missing"] = _missing_brief_text(brief["text"], checks["strings"])
    problems = []
    fallback = [f for f in checks.get("fonts", []) if f["fallback"]]
    if fallback:
        problems.append(f"{len(fallback)} font run(s) fell back: " + "; ".join(f"{f.get('layer', '')} asked {f['requested']}, got {f['actual']}" for f in fallback))
    if checks.get("glyph_gaps"):
        problems.append("characters the face does not draw: " + "; ".join(f"{g['layer']}: {''.join(g['missing'] + g['blank'])}" for g in checks["glyph_gaps"]))
    if result.get("brief_text_missing"):
        problems.append("brief strings not on the canvas: " + ", ".join(result["brief_text_missing"]))
    if checks.get("outside"):
        problems.append(f"{len(checks['outside'])} layer(s) outside the canvas")
    if checks.get("missing_links"):
        problems.append(f"{len(checks['missing_links'])} linked file(s) missing (rendered from cache)")
    problems += checks.get("platform", [])
    result = {"summary": ("; ".join(problems) if problems else "no font fallback, glyph gap, missing brief string, stray layer or missing link found") + f" — read {len(read)} sheet(s)", **result}
    return result
