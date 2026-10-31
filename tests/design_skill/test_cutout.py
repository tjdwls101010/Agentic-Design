"""cutout through the CLI: a hand-drawn matte placed into a real PhotoCraft layer mask, and real macOS Vision / SAM 3 on photos whose people were marked by hand."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from support.sandbox import FIXTURES
from support.tools import lightcraft, lines, need, photocraft, steps

pytestmark = pytest.mark.slow
PHOTOS = FIXTURES / "photos"
# Marked by eye on the fixtures, as [x0, y0, x1, y1] in pixels.
ONE_PERSON = (130, 120, 850, 800)  # one.jpg: the speaker, head to the lectern
PAIR_LEFT_FACE = (200, 350, 385, 560)  # pair.jpg: the man with glasses, dark hair
PAIR_RIGHT_FACE = (460, 380, 600, 570)  # pair.jpg: the man with white hair


@pytest.fixture
def job(sandbox):
    r = sandbox.run("new", "썸네일", "누끼", "--request", "누끼", "--no-open", "--source", PHOTOS / "one.jpg", "--source", PHOTOS / "pair.jpg", "--source", PHOTOS / "empty.jpg")
    assert r.code == 0, r.raw
    sandbox.job = Path(r.out["job"])
    return sandbox


def mean_in(matte: np.ndarray, box) -> float:
    x0, y0, x1, y1 = box
    return float(matte[y0:y1, x0:x1].mean())


def test_a_given_matte_lands_in_the_layer_mask_where_the_photo_is_placed(job):
    need("photocraft-cli")
    src = job.job / "sources" / "one.jpg"
    matte = Image.new("L", (1200, 800), 0)
    ImageDraw.Draw(matte).ellipse((300, 200, 900, 600), fill=255)
    matte_path = job.root / "hand.png"
    matte.save(matte_path)
    doc = job.job / "work" / "doc.pcraft"
    r = photocraft("run", "--new", json.dumps({"width": 1600, "height": 1200, "background": "transparent"}), *steps(("file.placeLinked", {"path": str(src)})), "--out", str(doc))
    assert r.returncode == 0, r.stderr
    placed = [d for d in lines(r.stdout) if d["command"] == "file.placeLinked"][0]["result"]["bounds"]
    r = job.run("cutout", job.job, src, "--matte", matte_path, "--doc", doc, "--layer", "one")
    assert r.code == 0, r.raw + r.err
    assert r.out["attached"]["layer"] == "one" and r.out["coverage"] == pytest.approx(np.pi * 300 * 200 / (1200 * 800), abs=0.005)
    assert np.array_equal(np.asarray(Image.open(r.out["matte"])), np.asarray(matte))
    out = job.root / "render.png"
    assert photocraft("convert", str(doc), str(out)).returncode == 0
    alpha = np.asarray(Image.open(out).convert("RGBA"))[..., 3]
    x0, y0, x1, y1 = placed
    sx, sy = (x1 - x0) / 1200, (y1 - y0) / 800

    def canvas(px, py):
        return round(x0 + px * sx), round(y0 + py * sy)

    for inside in [(600, 400), (400, 400), (800, 400), (600, 250), (600, 550)]:
        cx, cy = canvas(*inside)
        assert alpha[cy, cx] > 240, inside
    for outside in [(100, 100), (1100, 700), (320, 220), (880, 580)]:
        cx, cy = canvas(*outside)
        assert alpha[cy, cx] < 15, outside
    r = job.run("cutout", job.job, src, "--matte", matte_path, "--doc", doc, "--layer", "one")
    assert r.code == 0 and Path(r.out["matte"]).name == "one_matte-2.png"  # a second cut replaces the mask and keeps the first matte file


def test_vision_keeps_the_one_person_marked_by_hand(job):
    r = job.run("cutout", job.job, job.job / "sources" / "one.jpg")
    assert r.code == 0, r.raw + r.err
    assert r.out["people"] == 1
    matte = np.asarray(Image.open(r.out["matte"]))
    kept = matte >= 128
    x0, y0, x1, y1 = ONE_PERSON
    inside = kept[y0:y1, x0:x1].sum() / kept.sum()
    assert inside > 0.95 and kept[y0:y1, x0:x1].mean() > 0.3


def test_one_person_out_of_several_by_vision_number(job):
    src = job.job / "sources" / "pair.jpg"
    whole = job.run("cutout", job.job, src)
    assert whole.code == 0 and whole.out["people"] >= 2
    shares = []
    for n in range(1, whole.out["people"] + 1):
        r = job.run("cutout", job.job, src, "--instance", str(n))
        assert r.code == 0, r.raw
        shares.append(r.out["coverage"])
    assert all(s < whole.out["coverage"] for s in shares)
    assert sum(shares) < whole.out["coverage"] * 1.15
    assert job.run("cutout", job.job, src, "--instance", "9").code == 1


def test_a_described_person_is_kept_and_the_other_is_not(job):
    need("lightcraft-cli")
    status = lines(lightcraft("run", "segment.model.status").stdout)
    if not status or not status[0].get("result", {}).get("installed"):
        pytest.skip("SAM 3 is not installed in LightCraft")
    r = job.run("cutout", job.job, job.job / "sources" / "pair.jpg", "--select", "man with white hair")
    assert r.code == 0, r.raw + r.err
    matte = np.asarray(Image.open(r.out["matte"]))
    assert mean_in(matte, PAIR_RIGHT_FACE) > 200 and mean_in(matte, PAIR_LEFT_FACE) < 30
    r = job.run("cutout", job.job, job.job / "sources" / "pair.jpg", "--select", "흰 머리 남자")
    assert r.code == 1 and "English" in r.out["error"]


def test_no_person_and_bad_arguments(job):
    r = job.run("cutout", job.job, job.job / "sources" / "empty.jpg")
    assert r.code == 1 and r.out["people"] == 0
    small = job.root / "small.png"
    Image.new("L", (10, 10)).save(small)
    assert job.run("cutout", job.job, job.job / "sources" / "one.jpg", "--matte", small).code == 2
    assert job.run("cutout", job.job, job.job / "sources" / "one.jpg", "--instance", "1", "--select", "x").code == 2
    assert job.run("cutout", job.job, job.job / "sources" / "one.jpg", "--doc", job.job / "work" / "x.pcraft").code == 2


def test_choke_pulls_the_edge_in_by_whole_pixels(job):
    matte = Image.new("L", (1200, 800), 0)
    ImageDraw.Draw(matte).rectangle((300, 200, 899, 599), fill=255)
    path = job.root / "box.png"
    matte.save(path)
    r = job.run("cutout", job.job, job.job / "sources" / "one.jpg", "--matte", path, "--choke", "4")
    assert r.code == 0, r.raw
    out = np.asarray(Image.open(r.out["matte"]))
    assert out[400, 303] == 0 and out[400, 304] == 255 and out[400, 895] == 255 and out[400, 896] == 0
    assert r.out["box"] == [304, 204, 592, 392]
