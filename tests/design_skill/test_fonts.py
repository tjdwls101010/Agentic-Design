"""fonts-install and fonts-search through the CLI: font files built with known names and characters, installed into the sandbox's fonts folder."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from support.fontfiles import build


def test_woff2_becomes_a_ttf_named_after_its_postscript_name(sandbox):
    src = build(sandbox.root / "받은 폰트" / "web.woff2", family="Design Test", style="Black", chars="가나다", flavor="woff2")
    r = sandbox.run("fonts-install", "--file", src)
    assert r.code == 0, r.raw + r.err
    (row,) = r.out["fonts"]
    assert (row["family"], row["style"], row["postscript"], row["status"]) == ("Design Test", "Black", "DesignTest-Black", "installed")
    installed = sandbox.fonts / "DesignTest-Black.ttf"
    assert row["file"] == str(installed)
    from fontTools.ttLib import TTFont

    font = TTFont(installed)
    assert font.flavor is None and set(font.getBestCmap()) == {ord(c) for c in "가나다"}
    assert row["hangul"] == 3 and row["missing_ks_x_1001"] == 2347
    assert any("3 of 11172 Hangul syllables" in w for w in r.out["warnings"])
    assert set(r.out["seen_by"]) <= {"photocraft", "vectorcraft"}


def test_the_same_web_font_converts_to_the_same_bytes(sandbox):
    src = build(sandbox.root / "w2.woff2", family="Twice", chars="가", flavor="woff2")
    assert sandbox.run("fonts-install", "--file", src).out["fonts"][0]["status"] == "installed"
    r = sandbox.run("fonts-install", "--file", src)
    assert r.code == 0 and r.out["fonts"][0]["status"] == "already_installed"


def test_a_face_without_a_family_name_is_refused(sandbox):
    nameless = build(sandbox.root / "n.woff2", family="Nameless", flavor="woff2", unnamed=True)
    named = build(sandbox.root / "ok.woff2", family="Named", flavor="woff2")
    r = sandbox.run("fonts-install", "--file", nameless, named)
    assert r.code == 0, r.raw
    assert [row["status"] for row in r.out["fonts"]] == ["refused", "installed"]
    assert "file" not in r.out["fonts"][0] and any("family name is missing" in w for w in r.out["warnings"])
    assert [p.name for p in sandbox.fonts.iterdir()] == ["Named-Regular.ttf"]
    r = sandbox.run("fonts-install", "--file", nameless)
    assert r.code == 1 and "nothing was installed" in r.out["error"]


@pytest.mark.parametrize("cff", [False, True])
def test_hangul_mapped_to_empty_glyphs_is_refused(sandbox, cff):
    gappy = build(sandbox.root / "gappy.woff2", family="Gappy", chars="가나", blank="똠펲", flavor="woff2", cff=cff)
    r = sandbox.run("fonts-install", "--file", gappy)
    assert r.code == 1 and "nothing was installed" in r.out["error"]
    (row,) = r.out["fonts"]
    assert (row["status"], row["hangul"], row["hangul_blank"]) == ("refused", 2, 2)
    assert list(sandbox.fonts.iterdir()) == []


def test_cff_woff_becomes_an_otf(sandbox):
    src = build(sandbox.root / "w.woff", family="Design Cff", chars="AB", flavor="woff", cff=True)
    r = sandbox.run("fonts-install", "--file", src)
    assert r.code == 0, r.raw + r.err
    assert r.out["fonts"][0]["file"].endswith("DesignCff-Regular.otf") and r.out["fonts"][0]["hangul"] == 0
    assert not any("Hangul" in w for w in r.out.get("warnings", []))  # a Latin font is not a Hangul subset
    # The sandbox's fonts folder is not one PhotoCraft scans, so it rightly says it cannot see the family.
    assert any("PhotoCraft lists no face under 'Design Cff'" in w for w in r.out["warnings"])


def test_a_zip_is_unpacked_skipping_resource_forks(sandbox):
    a = build(sandbox.root / "src" / "A.otf", family="Zip Fam", style="Bold", cff=True)
    b = build(sandbox.root / "src" / "B.ttf", family="Zip Fam", style="Light")
    archive = sandbox.root / "배포본.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(a, "ZipFam/A.otf")
        z.write(b, "ZipFam/B.ttf")
        z.writestr("__MACOSX/ZipFam/._A.otf", b"junk")
        z.writestr("ZipFam/readme.txt", "license")
    r = sandbox.run("fonts-install", "--file", archive)
    assert r.code == 0, r.raw + r.err
    assert sorted(row["from"] for row in r.out["fonts"]) == ["A.otf", "B.ttf"]
    assert sorted(p.name for p in sandbox.fonts.iterdir()) == ["A.otf", "B.ttf"]
    assert (sandbox.fonts / "A.otf").read_bytes() == a.read_bytes()


def test_a_file_already_there_is_never_replaced(sandbox):
    src = build(sandbox.root / "x" / "Same.ttf", family="Same Fam")
    assert sandbox.run("fonts-install", "--file", src).out["fonts"][0]["status"] == "installed"
    assert sandbox.run("fonts-install", "--file", src).out["fonts"][0]["status"] == "already_installed"
    other = build(sandbox.root / "y" / "Same.ttf", family="Same Fam", chars="가")
    r = sandbox.run("fonts-install", "--file", other)
    assert r.code == 0 and r.out["fonts"][0]["status"] == "kept_existing"
    assert (sandbox.fonts / "Same.ttf").read_bytes() == src.read_bytes()
    assert any("kept" in w for w in r.out["warnings"])


def test_not_a_font_is_bad_input(sandbox):
    junk = sandbox.root / "not-a-font.ttf"
    junk.write_bytes(b"hello")
    r = sandbox.run("fonts-install", "--file", junk)
    assert r.code == 4 and "not a font file" in r.out["error"]
    empty = sandbox.root / "e.zip"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", "x")
    assert sandbox.run("fonts-install", "--file", empty).code == 4
    assert list(sandbox.fonts.iterdir()) == []


def test_argument_errors(sandbox):
    src = build(sandbox.root / "a.ttf", family="A")
    assert sandbox.run("fonts-install", "--file", src, "--weight", "700").code == 2
    assert sandbox.run("fonts-install").code == 2
    assert sandbox.run("fonts-search", "붓", "--use", "video").code == 2
    assert sandbox.run("fonts-search", "--use", "nonsense").code == 2


@pytest.mark.network
def test_a_non_ofl_noonnu_font_is_refused_with_its_download_page(sandbox):
    r = sandbox.run("fonts-install", "--noonnu", "1279")
    assert r.code == 1 and "OFL" in r.out["error"]
    assert r.out["download_page"].startswith("https://www.gp.go.kr/") and r.out["license"]["ofl"] == "not_allowed"
    assert list(sandbox.fonts.iterdir()) == []


@pytest.mark.network
def test_an_ofl_noonnu_font_installs_one_weight(sandbox):
    r = sandbox.run("fonts-install", "--noonnu", "694", "--weight", "900")
    assert r.code == 0, r.raw + r.err
    (row,) = r.out["fonts"]
    assert row["postscript"] == "Pretendard-Black" and row["hangul"] == 11172 and row["file"].endswith("Pretendard-Black.ttf")
    assert r.out["license"]["license"]["ofl"] == "allowed"


@pytest.mark.network
def test_search_by_filters_and_by_name(sandbox):
    r = sandbox.run("fonts-search", "--use", "video", "--use", "bici", "--style", "handwriting")
    assert r.code == 0 and len(r.out["fonts"]) == 24 and "category_use_ids" in r.out["url"]
    r = sandbox.run("fonts-search", "프리텐다드")
    assert r.code == 0 and 694 in [f["id"] for f in r.out["fonts"]]


def test_a_hostile_postscript_name_cannot_leave_the_fonts_folder(sandbox):
    from fontTools.ttLib import TTFont

    src = build(sandbox.root / "evil.woff", family="Evil", flavor="woff")
    font = TTFont(src)
    for record in font["name"].names:
        if record.nameID == 6:
            record.string = "../escaped"
    font.save(src)
    r = sandbox.run("fonts-install", "--file", src)
    assert r.code == 0, r.raw
    installed = Path(r.out["fonts"][0]["file"])
    assert installed.parent == sandbox.fonts and installed.name == "escaped.ttf"
    assert not (sandbox.root / "escaped.ttf").exists()


def test_a_collection_goes_in_whole_or_not_at_all(sandbox):
    from fontTools.ttLib import TTCollection, TTFont

    good = build(sandbox.root / "g.ttf", family="Coll Good")
    gappy = build(sandbox.root / "b.ttf", family="Coll Gappy", chars="가", blank="똠")
    coll = TTCollection()
    coll.fonts = [TTFont(good), TTFont(gappy)]
    path = sandbox.root / "pair.ttc"
    coll.save(str(path))
    r = sandbox.run("fonts-install", "--file", path)
    assert r.code == 1 and r.out["fonts"][0]["status"] == "refused"
    assert list(sandbox.fonts.iterdir()) == []
    coll.fonts = [TTFont(good), TTFont(build(sandbox.root / "g2.ttf", family="Coll Good", style="Bold"))]
    coll.save(str(path))
    r = sandbox.run("fonts-install", "--file", path)
    assert r.code == 0 and [p.name for p in sandbox.fonts.iterdir()] == ["pair.ttc"]


def test_damaged_inputs_are_bad_input_not_a_traceback(sandbox):
    empty = sandbox.root / "empty.ttf"
    empty.write_bytes(b"\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
    r = sandbox.run("fonts-install", "--file", empty)
    assert r.code == 4 and r.out and "error" in r.out
    bad = sandbox.root / "bad.zip"
    bad.write_bytes(b"PK\x03\x04 not really a zip")
    r = sandbox.run("fonts-install", "--file", bad)
    assert r.code == 4 and "zip" in r.out["error"]
