"""Tiny font files built with fontTools, so a test knows exactly which characters and names a font has."""

from __future__ import annotations

from pathlib import Path


def build(path: Path, *, family: str, style: str = "Regular", chars: str = "가나다ABC", flavor: str | None = None, cff: bool = False, unnamed: bool = False, blank: str = "") -> Path:
    """A font whose cmap holds exactly `chars` (plus .notdef), named family/style, PostScript name Family-Style without spaces. `flavor` woff or woff2 writes a web font; `unnamed` strips the family names (IDs 1 and 16), as some web copies are; the characters in `blank` are mapped to empty glyphs, as in a web copy cut down to KS X 1001."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = [".notdef"] + [f"uni{ord(c):04X}" for c in chars + blank]
    fb = FontBuilder(1000, isTTF=not cff)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in chars + blank})
    empty = {f"uni{ord(c):04X}" for c in blank}
    ps = f"{family.replace(' ', '')}-{style.replace(' ', '')}"

    def box(pen):
        pen.moveTo((100, 0))
        pen.lineTo((100, 700))
        pen.lineTo((600, 700))
        pen.lineTo((600, 0))
        pen.closePath()

    if cff:
        glyphs = {}
        for n in names:
            pen = T2CharStringPen(700, None)
            if n not in empty:
                box(pen)
            glyphs[n] = pen.getCharString()
        fb.setupCFF(ps, {"FullName": f"{family} {style}"}, glyphs, {})
    else:
        glyphs = {}
        for n in names:
            pen = TTGlyphPen(None)
            if n not in empty:
                box(pen)
            glyphs[n] = pen.glyph()
        fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (700, 100) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": style, "psName": ps, "typographicFamily": family, "typographicSubfamily": style})
    if unnamed:
        fb.font["name"].names = [r for r in fb.font["name"].names if r.nameID not in (1, 16)]
    fb.setupOS2()
    fb.setupPost()
    path.parent.mkdir(parents=True, exist_ok=True)
    if flavor:
        fb.font.flavor = flavor
    fb.save(str(path))
    return path
