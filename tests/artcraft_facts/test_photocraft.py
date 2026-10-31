"""What photocraft-cli does that SKILL.md relies on. Each test names the SKILL.md section whose sentence it backs; when one fails after an update, change or delete that sentence rather than loosening the test."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from support.tools import lines, photocraft, steps

pytestmark = pytest.mark.slow
NEW = json.dumps({"width": 400, "height": 300})


def type_info(out: str) -> dict:
    return [d for d in lines(out) if d.get("command") == "type.info"][-1]["result"]


def test_a_missing_font_style_falls_back_to_regular_without_an_error():
    """How the CLIs fail quietly: a fontStyle the family lacks becomes Regular, visible only in the PostScript name."""
    r = photocraft("run", "--new", NEW, *steps(("type.create", {"x": 10, "y": 60, "text": "가나", "font": "Pretendard", "fontStyle": "NoSuchStyle", "size": 40}), ("type.info", {})))
    assert r.returncode == 0, r.stderr
    assert '"postscript_name": "Pretendard-Regular"' in json.dumps(type_info(r.stdout))


def test_an_unknown_parameter_key_is_ignored_but_an_out_of_range_value_fails():
    """How the CLIs fail quietly: headless run ignores a parameter key it does not know, while a value out of range is a clear error."""
    r = photocraft("run", "--new", NEW, *steps(("type.create", {"x": 10, "y": 60, "text": "가", "size": 40, "noSuchKey": 5})))
    assert r.returncode == 0, r.stderr
    r = photocraft("run", "--new", NEW, *steps(("type.create", {"x": 10, "y": 60, "text": "가", "size": 99999})))
    assert r.returncode != 0 and "size must be between" in r.stderr


def test_a_failed_step_saves_nothing(tmp_path):
    """How the CLIs fail quietly: `run` is all or nothing; one failing step leaves no file even after earlier steps worked."""
    out = tmp_path / "nothing.pcraft"
    r = photocraft("run", "--new", NEW, *steps(("type.create", {"x": 10, "y": 60, "text": "가"}), ("no.such.command", {})), "--out", str(out))
    assert r.returncode != 0 and not out.exists()


def test_an_outside_matte_becomes_a_layer_mask(tmp_path):
    """Cutouts: a greyscale matte the size of the canvas is copied in and pasted into a layer mask, so the mask stays editable in the app."""
    Image.new("RGB", (400, 300), (40, 90, 200)).save(tmp_path / "photo.png")
    matte = Image.new("L", (400, 300), 0)
    ImageDraw.Draw(matte).ellipse((100, 50, 300, 250), fill=255)
    matte.save(tmp_path / "matte.png")
    r = photocraft("run", str(tmp_path / "photo.png"), *steps(("layer.new.layerFromBackground", {}), ("file.openAs", {"path": str(tmp_path / "matte.png")}), ("select.all", {}), ("edit.copy", {}), ("document.activate", {"document": 0}), ("layer.layerMask.revealAll", {}), ("edit.paste", {"target": "mask"})), "--out", str(tmp_path / "masked.pcraft"))
    assert r.returncode == 0, r.stderr
    info = json.loads(photocraft("info", str(tmp_path / "masked.pcraft")).stdout)
    assert [layer["hasMask"] for layer in info["layers"]] == [True]
    r = photocraft("convert", str(tmp_path / "masked.pcraft"), str(tmp_path / "masked.png"))
    alpha = np.asarray(Image.open(tmp_path / "masked.png").convert("RGBA"))[..., 3]
    assert alpha[150, 200] == 255 and alpha[10, 10] == 0 and alpha[290, 390] == 0


def test_linked_placement_works_in_run_and_stores_an_absolute_path(tmp_path):
    """The document is the work: file.placeLinked in a headless run links the photo by absolute path instead of embedding it, so the document is smaller than with the photo embedded and a copy elsewhere still renders."""
    Image.fromarray((np.random.default_rng(0).random((1800, 2400, 3)) * 255).astype("uint8")).save(tmp_path / "photo.png")
    (tmp_path / "work").mkdir()
    sizes = {}
    for how in ("placeLinked", "placeEmbedded"):
        r = photocraft("run", "--new", json.dumps({"width": 800, "height": 600}), *steps((f"file.{how}", {"path": str(tmp_path / "photo.png")})), "--out", str(tmp_path / "work" / f"{how}.pcraft"))
        assert r.returncode == 0, r.stderr
        sizes[how] = (tmp_path / "work" / f"{how}.pcraft").stat().st_size
    assert sizes["placeLinked"] < sizes["placeEmbedded"] * 0.6, sizes
    text = photocraft("info", str(tmp_path / "work" / "placeLinked.pcraft")).stdout
    assert '"kind": "linked"' in text and str(tmp_path / "photo.png") in text
    deeper = tmp_path / "versions" / "a" / "b"
    deeper.mkdir(parents=True)
    (deeper / "v1.pcraft").write_bytes((tmp_path / "work" / "placeLinked.pcraft").read_bytes())
    r = photocraft("convert", str(deeper / "v1.pcraft"), str(tmp_path / "v1.png"))
    assert r.returncode == 0, r.stderr
    assert np.asarray(Image.open(tmp_path / "v1.png").convert("RGB"), dtype=float).std() > 10  # the (downscaled) noise photo, not a blank white canvas


def test_the_control_session_refuses_linked_placement_and_doc_place_embeds(tmp_path):
    """Working in the running apps: a control session (what the app bridge speaks) refuses file.placeLinked as an ambient-path command, and its doc.place embeds."""
    Image.new("RGB", (200, 100), (200, 60, 40)).save(tmp_path / "photo.png")
    requests = "\n".join(json.dumps(r) for r in [
        {"id": 1, "method": "doc.new", "params": {"width": 400, "height": 300}},
        {"id": 2, "method": "engine.execute", "params": {"command": "file.placeLinked", "params": {"path": str(tmp_path / "photo.png")}}},
        {"id": 3, "method": "doc.place", "params": {"path": str(tmp_path / "photo.png")}},
        {"id": 4, "method": "doc.inspect", "params": {}},
    ]) + "\n"
    r = photocraft("serve", "--automation-read-root", str(tmp_path), "--automation-write-root", str(tmp_path), input=requests, timeout=120)
    replies = {d["id"]: d for d in lines(r.stdout)}
    assert replies[2]["ok"] is False and "ambient filesystem paths" in replies[2]["error"]
    assert replies[3]["ok"] is True
    assert '"kind": "linked"' not in json.dumps(replies[4])
