"""version, restore, proof and export through the CLI on small real documents made with the installed ArtCraft CLIs."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from support.tools import lightcraft, need, photocraft, steps, vectorcraft

pytestmark = pytest.mark.slow


def ledger(job: Path) -> dict:
    return json.loads((job / "job.json").read_text())


@pytest.fixture
def job(sandbox):
    need("photocraft-cli")
    r = sandbox.run("new", "썸네일", "테스트", "--request", "국감 썸네일", "--platform", "youtube-thumbnail", "--text", "여전한 검사 특권", "--no-open")
    assert r.code == 0, r.raw
    path = Path(r.out["job"])
    photo = path / "sources" / "photo.png"
    y, x = np.mgrid[0:540, 0:960]
    Image.fromarray(np.dstack([x * 255 / 960, y * 255 / 540, np.full_like(x, 90.0)]).astype("uint8")).save(photo)
    doc = path / "work" / "thumb.pcraft"
    r = photocraft("run", "--new", json.dumps({"width": 1920, "height": 1080}), *steps(("file.placeLinked", {"path": str(photo)}), ("type.create", {"x": 80, "y": 200, "text": "여전한 검사 특권", "font": "Pretendard", "fontStyle": "Black", "size": 120, "color": "#ffffff"})), "--out", str(doc))
    assert r.returncode == 0, r.stderr
    sandbox.job, sandbox.doc, sandbox.photo = path, doc, photo
    return sandbox


def add_type(doc: Path, text: str, **style) -> None:
    params = {"x": 80, "y": 900, "text": text, "font": "Pretendard", "fontStyle": "Bold", "size": 60, **style}
    r = photocraft("run", str(doc), *steps(("type.create", params)), "--out", str(doc), "--in-place")
    assert r.returncode == 0, r.stderr


def test_version_snapshots_the_document_and_renders_it(job):
    r = job.run("version", job.job, "--kind", "composite", "--direction", "기본")
    assert r.code == 0, r.raw + r.err
    assert r.out["version"] == 1 and "warnings" not in r.out
    snap, render = Path(r.out["snapshot"]), Path(r.out["render"])
    assert snap == job.job / "versions" / "v1.pcraft" and snap.read_bytes() == job.doc.read_bytes()
    with Image.open(render) as im:
        assert im.size == (1920, 1080)
    row = ledger(job.job)["versions"][0]
    assert (row["kind"], row["app"], row["source"], row["size"]) == ("composite", "photocraft", "work/thumb.pcraft", [1920, 1080])
    assert "versions/v1.png" in (job.job / "contact-sheet.html").read_text()
    assert job.opened() == [str(job.job / "contact-sheet.html")]


def test_restore_keeps_unversioned_edits_before_putting_the_old_state_back(job):
    assert job.run("version", job.job, "--kind", "composite", "--direction", "a").code == 0
    add_type(job.doc, "둘째 줄")
    assert job.run("version", job.job, "--kind", "composite", "--direction", "a", "--parent", "1").code == 0
    add_type(job.doc, "성진이 앱에서 고친 줄", y=1000)
    edited = job.doc.read_bytes()
    r = job.run("restore", job.job, "--version", "1")
    assert r.code == 0, r.raw + r.err
    assert r.out["kept_first"]["version"] == 3 and r.out["version"] == 4
    versions = ledger(job.job)["versions"]
    assert (job.job / "versions" / "v3.pcraft").read_bytes() == edited
    assert job.doc.read_bytes() == (job.job / "versions" / "v1.pcraft").read_bytes()
    assert versions[3]["restored_from"] == 1 and versions[3]["parent"] == 1
    r = job.run("restore", job.job, "--version", "2")
    assert r.code == 0 and "kept_first" not in r.out


def test_a_missing_linked_photo_is_reported(job):
    job.photo.unlink()
    r = job.run("version", job.job, "--kind", "composite", "--direction", "a")
    assert r.code == 0, r.raw
    assert any("linked file missing" in w and "photo.png" in w for w in r.out["warnings"])


def test_a_large_file_anywhere_in_the_job_is_warned_about(job):
    big = job.job / "assets" / "kim_cutout.pcraft"
    with open(big, "wb") as fh:
        fh.truncate(91 * 1024 * 1024)
    r = job.run("version", job.job, "--kind", "composite", "--direction", "a")
    assert any("kim_cutout.pcraft is 91.0 MiB" in w for w in r.out["warnings"])


def test_version_argument_errors(job):
    assert job.run("version", job.job, "--kind", "vector", "--direction", "a").code == 2
    assert job.run("version", job.job, "--kind", "composite", "--direction", "a", "--doc", job.photo).code == 2
    (job.job / "work" / "second.pcraft").write_bytes(job.doc.read_bytes())
    r = job.run("version", job.job, "--kind", "composite", "--direction", "a")
    assert r.code == 1 and "give --doc" in r.out["error"]


def test_proof_finds_fallback_glyph_gaps_missing_brief_text_and_strays(job):
    add_type(job.doc, "없는 굵기", fontStyle="NoSuchStyle")
    add_type(job.doc, "펲", font="Hahmlet", fontStyle="Regular", x=900, y=600)
    add_type(job.doc, "밖", x=1900, y=1050)
    r = photocraft("run", str(job.doc), *steps(("layer.select", {"name": "여전한 검사 특권"}), ("layer.delete", {})), "--out", str(job.doc), "--in-place")
    assert r.returncode == 0, r.stderr
    r = job.run("proof", job.job, "--crop", "0,0,400,300")
    assert r.code == 0, r.raw + r.err
    out = r.out
    fallback = [f for f in out["fonts"] if f["fallback"]]
    assert [(f["layer"], f["actual"]) for f in fallback] == [("없는 굵기", "Pretendard-Regular")]
    assert out["glyph_gaps"] == [{"layer": "펲", "postscript": "Hahmlet-Regular", "missing": ["펲"], "blank": []}]
    assert out["brief_text_missing"] == ["여전한 검사 특권"]
    assert [o["layer"] for o in out["outside"]] == ["밖"]
    assert out["summary"].startswith("1 font run(s) fell back")
    for sheet in out["read"]:
        assert Path(sheet).is_file()
    assert Path(out["dir"]).name == "1" and any(p.endswith("crop-1.png") for p in out["read"]) and any(p.endswith("zones.png") for p in out["read"])
    with Image.open(Path(out["dir"]) / "crop-1.png") as im:
        assert im.size == (400, 300)
    assert job.run("proof", job.job, "--crop", "1800,1000,400,300").code == 2


def test_export_renders_at_the_platform_size_and_never_overwrites(job):
    assert job.run("version", job.job, "--kind", "composite", "--direction", "a").code == 0
    r = job.run("export", job.job, "--version", "v1")
    assert r.code == 0, r.raw + r.err
    path = Path(r.out["path"])
    assert path.parent == job.job / "exports" and path.suffix == ".jpg" and r.out["target"] == "youtube-thumbnail"
    with Image.open(path) as im:
        assert im.size == (1920, 1080) and im.format == "JPEG"
    assert "violations" not in r.out
    assert ledger(job.job)["exports"][0]["of"] == "v1"
    assert job.run("export", job.job, "--version", "v1").code == 1
    r = job.run("export", job.job, "--version", "v1", "--target", "instagram-portrait")
    assert r.code == 2 and "aspect" in r.out["error"]
    r = job.run("export", job.job, "--version", "v1", "--size", "600x338", "--format", "png", "--to", job.root / "elsewhere")
    assert r.code == 0 and r.out["violations"] == ["width 600 px is under the 640 px minimum"]


def test_vector_documents_version_and_proof(sandbox):
    need("vectorcraft-cli")
    r = sandbox.run("new", "로고", "벡터", "--request", "로고", "--text", "카피더리치", "--no-open")
    job = Path(r.out["job"])
    doc = job / "work" / "logo.vectorcraft"
    r = vectorcraft("run", *steps(("text.create", {"x": 20, "y": 80, "text": "카피더리치", "font": "Pretendard", "style": "NoStyle", "size": 60})), "--export", str(doc))
    assert r.returncode == 0, r.stderr
    r = sandbox.run("version", job, "--kind", "vector", "--direction", "a")
    assert r.code == 0, r.raw + r.err
    assert Path(r.out["render"]).is_file()
    r = sandbox.run("proof", job)
    assert r.code == 0, r.raw
    assert r.out["fonts"][0]["fallback"] is True and r.out["brief_text_missing"] == []


def test_grade_versions_hold_develop_settings_and_restore_them(sandbox):
    need("lightcraft-cli")
    r = sandbox.run("new", "보정", "사진", "--request", "보정", "--no-open")
    job = Path(r.out["job"])
    photo = job / "sources" / "event.jpg"
    y, x = np.mgrid[0:300, 0:400]
    Image.fromarray(np.dstack([x * 255 / 400, y * 255 / 300, np.full_like(x, 120.0)]).astype("uint8")).save(photo, quality=95)
    library = job / "work" / "lightcraft"
    r = lightcraft("run", "--library", str(library), "--import", str(photo), "develop.set", "control=light.exposure", "value=0.6", "mask.add", "kind=linear")
    assert r.returncode == 0, r.stderr
    r = sandbox.run("version", job, "--kind", "grade", "--direction", "밝게", "--doc", library, "--photo-id", "1", "--photo", photo)
    assert r.code == 0, r.raw + r.err
    assert Path(r.out["snapshot"]).suffix == ".json" and Path(r.out["render"]).suffix == ".jpg"
    first = np.asarray(Image.open(r.out["render"]), dtype=float)
    r = lightcraft("run", "--library", str(library), "develop.set", "control=light.exposure", "value=-1")
    r = sandbox.run("restore", job, "--version", "1")
    assert r.code == 0, r.raw + r.err
    assert r.out["kept_first"]["version"] == 2
    again = np.asarray(Image.open(r.out["render"]), dtype=float)
    assert np.abs(first - again).mean() == 0
    darker = np.asarray(Image.open(job / "versions" / "v2.jpg"), dtype=float)
    assert darker.mean() < first.mean() - 20


def test_concurrent_versions_get_their_own_numbers_and_renders(job):
    second = job.job / "work" / "square.pcraft"
    assert photocraft("run", "--new", json.dumps({"width": 600, "height": 600}), *steps(("type.create", {"x": 10, "y": 60, "text": "둘", "size": 40})), "--out", str(second)).returncode == 0
    procs = [job.popen("version", job.job, "--kind", "composite", "--direction", "a", "--doc", doc) for doc in (job.doc, second, job.doc, second)]
    for p in procs:
        out, err = p.communicate(timeout=300)
        assert p.returncode == 0, out + err
    rows = ledger(job.job)["versions"]
    assert sorted(r["v"] for r in rows) == [1, 2, 3, 4]
    for r in rows:
        with Image.open(job.job / r["render"]) as im:
            assert list(im.size) == ([1920, 1080] if r["source"] == "work/thumb.pcraft" else [600, 600]) == r["size"]
    assert not list((job.job / "versions").glob(".staging-*"))


def test_a_file_left_by_a_killed_run_is_skipped_not_blocking(job):
    (job.job / "versions" / "v1.png").write_bytes(b"left behind")
    r = job.run("version", job.job, "--kind", "composite", "--direction", "a")
    assert r.code == 0 and r.out["version"] == 2
    assert (job.job / "versions" / "v1.png").read_bytes() == b"left behind"
