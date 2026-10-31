"""Finding Korean fonts on noonnu and installing font files where PhotoCraft, VectorCraft and LightCraft find them.

Installing converts web formats (woff2, woff) to the desktop format their outlines need (.otf for CFF, .ttf for TrueType), unpacks a distributor's zip, never replaces a file already in the fonts folder, and then asks PhotoCraft and VectorCraft which names they resolve, because those are the names a type layer has to use. Hangul coverage is read from each file's character map: a webfont is often cut to the 2,350 syllables of KS X 1001, and a syllable outside them renders in a fallback font that no font-name check catches.

noonnu's own copy of a font (its webfont) is installed only when the font's license allows modifying and redistributing the file (noonnu's OFL row), since converting it is a modification; any other font comes from its distributor's download page as a file.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import asdict
from pathlib import Path

from design import noonnu, paths, photocraft, vectorcraft
from design.errors import BadInput, Failure, Unavailable

__all__ = ["search", "info", "install", "USES", "STYLES"]

USES = list(noonnu.USES)
STYLES = list(noonnu.STYLES)
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".woff", ".woff2")
HANGUL = range(0xAC00, 0xD7A4)  # every modern syllable, 11,172
KS_X_1001 = frozenset(c for c in HANGUL if len(chr(c).encode("euc_kr")) == 2)  # the 2,350 a subset keeps
PLACEHOLDER_FAMILIES = {"WebSubsetFont"}  # the name a subsetting tool gives the cut-down copies some webfonts are


def search(query: str | None, uses: list[str], styles: list[str], page: int) -> dict:
    url, cards = noonnu.search(query, uses, styles, page)
    out = {"summary": f"{len(cards)} fonts on page {page}" + (f" for {query!r}" if query else ""), "url": url, "fonts": [asdict(c) for c in cards]}
    if cards:
        out["next"] = "fonts info <id> for a font's license, styles and download page; fonts search with --page for more"
    return out


def _installable(font: noonnu.Font) -> bool:
    return font.license.get("ofl") == "allowed"


def info(font_id: int) -> dict:
    font = noonnu.font(font_id)
    doc = asdict(font)
    doc["webfont_installable"] = _installable(font)
    if not doc["webfont_installable"]:
        doc["install_from"] = "the distributor's file: download it from download_page and run fonts install <file>"
    return doc


def _coverage(font) -> dict:
    """Hangul syllables the face actually draws. A web copy cut down to KS X 1001 can keep all 11,172 in its character map and leave the rest as empty glyphs; the apps then draw nothing there, with no fallback and no missing-glyph report."""
    from fontTools.pens.boundsPen import ControlBoundsPen

    cmap = font.getBestCmap() or {}
    glyphs = font.getGlyphSet()
    drawn, blank = set(), 0
    for c in HANGUL:
        name = cmap.get(c)
        if name is None:
            continue
        pen = ControlBoundsPen(glyphs)
        glyphs[name].draw(pen)
        if pen.bounds is None:
            blank += 1
        else:
            drawn.add(c)
    out = {"hangul": len(drawn)}
    if blank:
        out["hangul_blank"] = blank
    if 0 < len(drawn) < len(HANGUL):
        out["missing_ks_x_1001"] = len(KS_X_1001 - drawn)
    return out


def _load(data: bytes, name: str):
    from fontTools.ttLib import TTCollection, TTFont, TTLibError

    try:
        if data[:4] == b"ttcf":
            return list(TTCollection(io.BytesIO(data), recalcTimestamp=False).fonts)
        return [TTFont(io.BytesIO(data), recalcTimestamp=False)]  # the same web font always converts to the same bytes, so a second install finds them already there
    except (TTLibError, AssertionError, ValueError, OSError, KeyError) as exc:
        raise BadInput(f"{name} is not a font file fontTools can read ({type(exc).__name__}: {exc})") from exc


def _names(font) -> dict:
    names = font["name"]

    def get(*ids):
        for i in ids:
            value = names.getDebugName(i)
            if value:
                return value
        return None

    return {"family": get(16, 1), "style": get(17, 2), "postscript": get(6)}


def _files_from(sources: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Font files out of what was handed over: zips are unpacked (macOS resource forks skipped), anything else must itself be a font."""
    out = []
    for name, data in sources:
        if data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members = [m for m in z.namelist() if m.lower().endswith(FONT_SUFFIXES) and "__MACOSX" not in m and not Path(m).name.startswith("._")]
                if not members:
                    raise BadInput(f"{name} holds no font file ({', '.join(FONT_SUFFIXES)})")
                out += [(Path(m).name, z.read(m)) for m in members]
        else:
            out.append((name, data))
    return out


def _write(folder: Path, name: str, data: bytes) -> tuple[Path, str]:
    """Put one desktop font in the fonts folder: installed, or already_installed (the same bytes are there), or kept_existing (a different file holds the name; it is not replaced)."""
    dest = folder / name
    if dest.exists():
        return dest, "already_installed" if dest.read_bytes() == data else "kept_existing"
    paths.place_new(dest, lambda tmp: tmp.write_bytes(data))
    return dest, "installed"


def _seen(families: list[str]) -> dict:
    """What each app resolves under the installed families; an app whose CLI is missing is left out."""
    seen: dict = {}
    for family in families:
        try:
            seen.setdefault("photocraft", {})[family] = [f["style"] for f in photocraft.font_faces(family)]
        except (Unavailable, Failure) as exc:
            seen.setdefault("photocraft", {})[family] = f"not checked: {exc.message}"
        try:
            seen.setdefault("vectorcraft", {})[family] = vectorcraft.font_styles(family)
        except (Unavailable, Failure) as exc:
            seen.setdefault("vectorcraft", {})[family] = f"not checked: {exc.message}"
    return seen


def install(*, font_id: int | None = None, files: list[Path] = (), weights: list[int] = ()) -> dict:
    """Install noonnu font `font_id` from its webfont (OFL only), or font files and zips handed over."""
    license = None
    if font_id is not None:
        font = noonnu.font(font_id)
        license = {"font": font.name, "noonnu": font.url, "license": font.license, "download_page": font.download_page}
        if not _installable(font):
            raise Failure(f"{font.name}: noonnu's webfont copy is installed only for OFL fonts (converting the file modifies it, which only the OFL plainly allows); download the font from its distributor and run fonts-install --file", **license)
        faces = noonnu.webfont_files(font)
        if weights:
            faces = [w for w in faces if w.weight in weights]
        if not faces:
            raise Failure(f"{font.name}: no webfont file" + (f" in weights {list(weights)}" if weights else ""), **license)
        sources = [(Path(w.url.split("?")[0]).name, noonnu.download(w.url)) for w in faces]
    else:
        sources = []
        for p in files:
            try:
                sources.append((p.name, p.read_bytes()))
            except OSError as exc:
                raise BadInput(f"cannot read {p} ({exc})") from exc

    folder = paths.fonts_dir()
    folder.mkdir(parents=True, exist_ok=True)
    rows, families, warnings = [], [], []
    for name, data in _files_from(sources):
        loaded = _load(data, name)
        for font in loaded:
            row = {"from": name, **_names(font), **_coverage(font)}
            unnamed = not row["family"] or row["family"] in PLACEHOLDER_FAMILIES
            if unnamed:
                # An app lists a font by its family name; without a real one it cannot be chosen, and two such files would answer to one name.
                row["status"] = "refused"
                warnings.append(f"{name}: its family name is {row['family'] or 'missing'} (web copies are often stripped or renamed when cut down), so no app could select it by name; install the distributor's file instead")
                rows.append(row)
                break
            if row.get("hangul_blank"):
                # Unlike a missing syllable, which falls back to another font, a blank one prints as a gap no check reports.
                row["status"] = "refused"
                warnings.append(f"{name}: {row['hangul_blank']} Hangul syllables are mapped to empty glyphs (a cut-down web copy), so the apps would print gaps there without any warning; install the distributor's file instead")
                rows.append(row)
                continue
            if len(loaded) > 1 or font.flavor is None and Path(name).suffix.lower() in (".ttf", ".otf"):
                payload, filename = data, name  # a desktop file (or a whole collection) goes in as it came
            else:
                font.flavor = None
                buf = io.BytesIO()
                font.save(buf)
                payload = buf.getvalue()
                filename = f"{row['postscript'] or Path(name).stem}{'.otf' if 'CFF ' in font or 'CFF2' in font else '.ttf'}"
            dest, status = _write(folder, filename, payload)
            row.update({"file": str(dest), "status": status})
            if status == "kept_existing":
                warnings.append(f"{dest.name} already exists with different contents and was kept; compare it with {name} before replacing it by hand")
            if 0 < row["hangul"] < len(HANGUL):
                warnings.append(f"{row['postscript']}: {row['hangul']} of 11172 Hangul syllables" + (" (every KS X 1001 syllable among them)" if row.get("missing_ks_x_1001") == 0 else "") + "; a syllable outside them renders in a fallback font, so check every string set in it")
            rows.append(row)
            if row["family"] not in families:
                families.append(row["family"])
            if len(loaded) > 1:
                break  # a collection is one file; its first face names it
    seen = _seen(families)
    for family, styles in seen.get("photocraft", {}).items():
        if styles == []:
            warnings.append(f"PhotoCraft lists no face under {family!r}; a type layer cannot select it by that name (check fonts with type.fonts)")
    counts = {s: sum(r["status"] == s for r in rows) for s in ("installed", "already_installed", "kept_existing", "refused")}
    out = {"summary": f"{counts['installed']} installed, {counts['already_installed']} already there, {counts['kept_existing']} kept as they were" + (f", {counts['refused']} refused" if counts["refused"] else "") + f", in {folder}", "fonts": rows, "seen_by": seen}
    if license:
        out["license"] = license
    if warnings:
        out["warnings"] = warnings
    if not counts["installed"] and not counts["already_installed"] and not counts["kept_existing"]:
        raise Failure("nothing was installed: " + "; ".join(warnings), **{k: v for k, v in out.items() if k != "summary"})
    return out
