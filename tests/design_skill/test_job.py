"""new, show and record through the CLI, and show --all over jobs of every age in a sandbox data folder."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from support.images import make_png

TODAY = f"{datetime.date.today():%y%m%d}"


def new(sb, *extra, kind="썸네일", title="국감 제보"):
    r = sb.run("new", kind, title, "--request", "국감 썸네일 만들어 줘", "--no-open", *extra)
    assert r.code == 0, r.raw + r.err
    return Path(r.out["job"])


def ledger(job: Path) -> dict:
    return json.loads((job / "job.json").read_text())


def test_new_makes_the_tree_ledger_and_sheet(sandbox):
    photo = make_png(sandbox.root / "받은 것" / "의원 사진.png")
    ref = make_png(sandbox.root / "받은 것" / "선배 썸네일.png")
    job = new(sandbox, "--platform", "youtube-thumbnail", "--text", "여전한 검사 특권", "--reserved", "왼쪽 위 로고", "--source", photo, "--target", ref)
    assert job == sandbox.data / f"썸네일_{TODAY}_국감 제보"
    assert sorted(p.name for p in job.iterdir() if p.is_dir()) == sorted(["sources", "assets", "work", "versions", "proof", "exports", "etc"])
    assert (job / "sources" / "의원 사진.png").read_bytes() == photo.read_bytes()
    brief = ledger(job)["brief"]
    assert brief["size"] == [1920, 1080] and brief["aspect"] == "16:9" and brief["platform"] == "youtube-thumbnail"
    assert brief["text"] == ["여전한 검사 특권"] and brief["reserved"] == ["왼쪽 위 로고"] and brief["targets"] == ["sources/선배 썸네일.png"]
    page = (job / "contact-sheet.html").read_text()
    assert "여전한 검사 특권" in page and "비울 자리" in page
    assert sandbox.opened() == []


def test_new_opens_the_sheet_unless_told_not_to(sandbox):
    r = sandbox.run("new", "카드뉴스", "시리즈", "--request", "r")
    assert r.code == 0 and sandbox.opened() == [r.out["sheet"]]


def test_new_refuses_an_existing_folder_and_bad_names(sandbox):
    job = new(sandbox)
    (job / "sources" / "keep.txt").write_text("성진의 파일")
    r = sandbox.run("new", "썸네일", "국감 제보", "--request", "again", "--no-open")
    assert r.code == 2 and "already exists" in r.out["error"]
    assert (job / "sources" / "keep.txt").read_text() == "성진의 파일"
    assert sandbox.run("new", "썸/네일", "x", "--request", "r", "--no-open").code == 2
    assert sandbox.run("new", "썸네일", "x", "--request", "r", "--size", "0x10", "--no-open").code == 2


def test_record_notes_critique_and_finals(sandbox):
    job = new(sandbox)
    r = sandbox.run("record", job, "--note", "성진: 제목이 너무 작다")
    assert r.code == 0 and r.out["written"] == ["note"]
    r = sandbox.run("record", job, "--note", "사진 보정은 티 안 나게", "--scope", "reusable")
    assert r.code == 0
    notes = ledger(job)["notes"]
    assert [(n["text"], n["scope"]) for n in notes] == [("성진: 제목이 너무 작다", "job"), ("사진 보정은 티 안 나게", "reusable")]
    assert sandbox.run("record", job, "--version", "3", "--critique", "x").code == 1
    assert sandbox.run("record", job, "--final", "v1").code == 1
    assert sandbox.run("record", job, "--critique", "x").code == 2
    assert sandbox.run("record", job).code == 2


def test_show_reports_versions_and_unversioned_documents(sandbox):
    job = new(sandbox)
    (job / "work" / "thumb.pcraft").write_bytes(b"draft")
    r = sandbox.run("show", job)
    assert r.code == 0
    assert r.out["unversioned"] == [{"file": "work/thumb.pcraft", "state": "never versioned"}]
    assert "1 document(s) with changes no version holds" in r.out["summary"]


def _schema4(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "versions").mkdir()
    make_png(folder / "versions" / "v2-1.png")
    doc = {"schema": 4, "id": folder.name, "created": "2026-10-17T00:00:00+09:00", "brief": {"request": "보정", "aspect": "none", "notes": [{"text": "그늘 디테일은 살리고 하이라이트는 날리지 않는다", "scope": "reusable", "at": "t"}, {"text": "이번 사진만", "scope": "job", "at": "t", "version": 2}]}, "versions": [], "measurements": [], "finals": ["v2-1.png"], "exports": []}
    (folder / "job.json").write_text(json.dumps(doc, ensure_ascii=False))


def test_show_all_lists_every_age_of_job_and_the_references(sandbox):
    new(sandbox)
    _schema4(sandbox.data / "보정_261017_취향 시트")
    cards = sandbox.data / "웹포스터_260818_김대중 추모"
    make_png(cards / "card-1.png")
    make_png(sandbox.data / "_references" / "유튜브 썸네일" / "261022_최고위.jpg")
    make_png(sandbox.data / "_references" / "260907_국정감사 제보.jpg")
    (sandbox.data / "빈 폴더").mkdir()
    r = sandbox.run("show", "--all")
    assert r.code == 0, r.raw
    assert [j["job"] for j in r.out["jobs"]] == [f"썸네일_{TODAY}_국감 제보"]
    earlier = {j["job"]: j for j in r.out["earlier"]}
    assert set(earlier) == {"보정_261017_취향 시트", "웹포스터_260818_김대중 추모"}
    old = earlier["보정_261017_취향 시트"]
    assert old["schema"] == 4 and old["reusable_notes"] == ["그늘 디테일은 살리고 하이라이트는 날리지 않는다"]
    assert old["finals"] == [str(sandbox.data / "보정_261017_취향 시트" / "versions" / "v2-1.png")]
    assert earlier["웹포스터_260818_김대중 추모"]["finals"] == [str(cards / "card-1.png")]
    assert r.out["references"]["by_folder"] == {".": ["260907_국정감사 제보.jpg"], "유튜브 썸네일": ["261022_최고위.jpg"]}


def test_a_schema_4_job_is_read_only(sandbox):
    _schema4(sandbox.data / "보정_261017_취향 시트")
    r = sandbox.run("record", "보정_261017_취향 시트", "--note", "x")
    assert r.code == 1 and "read only" in r.out["error"]
