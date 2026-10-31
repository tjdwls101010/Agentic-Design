"""Which characters a font face actually draws, read from its file: the character map says which characters a face claims, and an empty glyph behind a claimed character prints as a gap that no app reports.

Faces are found by PostScript name in the folders macOS loads fonts from, the user's first.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from design import paths

__all__ = ["HANGUL", "KS_X_1001", "drawn", "coverage", "find", "gaps"]

HANGUL = range(0xAC00, 0xD7A4)  # every modern syllable, 11,172
KS_X_1001 = frozenset(c for c in HANGUL if len(chr(c).encode("euc_kr")) == 2)  # the 2,350 a cut-down copy keeps
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")


def drawn(font, codes) -> tuple[set[int], int]:
    """Of `codes`, the ones `font` (a fontTools TTFont) maps to a glyph with outlines, and how many it maps to an empty glyph."""
    from fontTools.pens.boundsPen import ControlBoundsPen

    cmap = font.getBestCmap() or {}
    glyphs = font.getGlyphSet()
    found, blank = set(), 0
    for c in codes:
        name = cmap.get(c)
        if name is None:
            continue
        pen = ControlBoundsPen(glyphs)
        glyphs[name].draw(pen)
        if pen.bounds is None:
            blank += 1
        else:
            found.add(c)
    return found, blank


def coverage(font) -> dict:
    """Hangul syllables the face draws: {"hangul", "hangul_blank"?: mapped to empty glyphs, "missing_ks_x_1001"?}."""
    found, blank = drawn(font, HANGUL)
    out = {"hangul": len(found)}
    if blank:
        out["hangul_blank"] = blank
    if 0 < len(found) < len(HANGUL):
        out["missing_ks_x_1001"] = len(KS_X_1001 - found)
    return out


def _folders() -> list[Path]:
    """Where the apps load fonts from (the user's folder first), plus the install folder when it is set elsewhere."""
    folders = [paths.fonts_dir(), Path.home() / "Library" / "Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    return list(dict.fromkeys(folders))


@lru_cache(maxsize=1)
def _index() -> dict[str, tuple[str, int]]:
    """PostScript name → (file, index in a collection), over every font file the folders hold. Built once per process."""
    from fontTools.ttLib import TTCollection, TTFont

    index: dict[str, tuple[str, int]] = {}
    for folder in _folders():
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() not in FONT_SUFFIXES:
                continue
            try:
                faces = TTCollection(str(path), lazy=True).fonts if path.suffix.lower() == ".ttc" else [TTFont(str(path), lazy=True)]
                for i, face in enumerate(faces):
                    ps = face["name"].getDebugName(6)
                    if ps:
                        index.setdefault(ps, (str(path), i))
            except Exception:  # noqa: BLE001 -- one unreadable file must not hide the rest
                continue
    return index


def find(postscript: str) -> tuple[str, int] | None:
    return _index().get(postscript)


def gaps(postscript: str, text: str) -> dict | None:
    """Characters of `text` the face named `postscript` does not draw: {"missing": [chars it has no glyph for], "blank": [chars it maps to an empty glyph]}, or None when the face's file is not found. Spaces and line breaks are skipped."""
    from fontTools.ttLib import TTCollection, TTFont

    where = find(postscript)
    if where is None:
        return None
    path, i = where
    font = TTCollection(path, lazy=True).fonts[i] if path.lower().endswith(".ttc") else TTFont(path, lazy=True)
    codes = {ord(c) for c in text if not c.isspace()}
    found, _ = drawn(font, codes)
    cmap = font.getBestCmap() or {}
    return {"missing": sorted(chr(c) for c in codes if c not in cmap), "blank": sorted(chr(c) for c in codes if c in cmap and c not in found)}
