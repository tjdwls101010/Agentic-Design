"""What vectorcraft-cli does that SKILL.md relies on. Each test names the SKILL.md section whose sentence it backs; when one fails after an update, change or delete that sentence rather than loosening the test."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from support.tools import lines, steps, vectorcraft

pytestmark = pytest.mark.slow


def kinds(path) -> str:
    r = vectorcraft("run", "--in", str(path), "--cmd", "document.inspect")
    assert r.returncode == 0, r.stderr
    return json.dumps([d["result"] for d in lines(r.stdout)], ensure_ascii=False)


def test_decorated_type_saved_as_svg_comes_back_as_paths(tmp_path):
    """Vector work: type with a stroke and live effects saved as plain SVG reopens as paths, no longer editable type; the .vectorcraft keeps it as type."""
    r = vectorcraft("run", *steps(("text.create", {"x": 20, "y": 80, "text": "원본글자", "font": "Pretendard", "style": "Black", "size": 60}), ("appearance.addStroke", {"id": "$0.id"}), ("effect.apply", {"id": "$0.id", "effect": "stylize.dropShadow"}), ("effect.apply", {"id": "$0.id", "effect": "warp.arc"})), "--export", str(tmp_path / "deco.svg"), "--export", str(tmp_path / "deco.vectorcraft"))
    assert r.returncode == 0, r.stderr
    native, svg = kinds(tmp_path / "deco.vectorcraft"), kinds(tmp_path / "deco.svg")
    assert '"kind": "Type"' in native and "원본글자" in native
    assert '"kind": "Type"' not in svg and "원본글자" not in svg


def _ink_right(path, top: int, bottom: int) -> int:
    rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=float)
    dark = (rgba[..., 3] > 128) & (rgba[..., :3].mean(axis=2) < 128)
    cols = np.nonzero(dark[top:bottom].any(axis=0))[0]
    return int(cols.max()) if cols.size else -1


def test_area_type_breaks_a_korean_word_between_syllables_without_a_warning(tmp_path):
    """Vector work: area type wraps Korean between any two syllables (국정감사 제/보를), and neither the step nor the export warns."""
    style = {"font": "Pretendard", "style": "Bold", "size": 40}
    r = vectorcraft("run", *steps(("text.create", {"x": 20, "y": 60, "text": "국정감사", **style})), "--export", str(tmp_path / "word.png"))
    assert r.returncode == 0, r.stderr
    r = vectorcraft("run", *steps(("text.create", {"x": 20, "y": 20, "text": "국정감사 제보를 기다립니다", "area": {"width": 200, "height": 400}, **style})), "--export", str(tmp_path / "area.png"))
    assert r.returncode == 0, r.stderr
    created, export = lines(r.stdout)
    assert "overflow" not in created["result"] and export["result"]["warnings"] == []
    word_end = _ink_right(tmp_path / "word.png", 0, 80)
    first_line_end = _ink_right(tmp_path / "area.png", 20, 70)
    assert first_line_end > word_end + 20  # the first syllable of 제보를 sits on line one


def test_area_type_that_does_not_fit_is_reported(tmp_path):
    """Vector work: text past the end of an area frame is reported (overflow in the step, a warning on export) and not drawn."""
    r = vectorcraft("run", *steps(("text.create", {"x": 20, "y": 20, "text": "국정감사 제보를 기다립니다 개인정보는 철저히 보호합니다", "font": "Pretendard", "style": "Bold", "size": 40, "area": {"width": 260, "height": 60}})), "--export", str(tmp_path / "over.png"))
    assert r.returncode == 0, r.stderr
    created, export = lines(r.stdout)
    assert created["result"]["overflow"] == [created["result"]["id"]]
    assert any("doesn't fit its frame" in w for w in export["result"]["warnings"])
