"""apps-status, apps-send, and the open-document guards of version and restore, against stand-ins for running apps that speak the control protocol."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from support import fake_app
from support.tools import need, photocraft, steps


@pytest.fixture(autouse=True)
def no_real_apps():
    from design import control

    if any(control.processes(app) for app in ("PhotoCraft", "VectorCraft", "LightCraft")):
        pytest.skip("a real ArtCraft app is running; these tests stand in for one")


@pytest.fixture
def running(tmp_path):
    procs = []

    def start(app, docs, **kw):
        proc, log, port = fake_app.start(tmp_path / f"fake-{len(procs)}", app, docs, **kw)
        procs.append(proc)
        return log, port

    yield start
    for p in procs:
        p.terminate()
        p.wait(timeout=10)


def test_status_reports_what_photocraft_has_open(sandbox, running):
    doc = sandbox.data / "x.pcraft"
    running("PhotoCraft", [doc])
    r = sandbox.run("apps-status")
    assert r.code == 0, r.raw
    pc = next(a for a in r.out["apps"] if a["app"] == "photocraft")
    assert pc["running"] is True and pc["documents"] == [{"path": str(doc), "dirty": False, "active": True}]


def test_an_app_without_a_control_port_is_flagged(sandbox, running):
    running("PhotoCraft", [], control=False)
    r = sandbox.run("apps-status")
    pc = next(a for a in r.out["apps"] if a["app"] == "photocraft")
    assert pc["running"] is True and pc["control_port"] is None and "documents" not in pc
    assert any("without a control port" in n for n in r.out["notes"])
    assert sandbox.run("apps-send", "photocraft", stdin='{"method": "ui.inspect"}\n').code == 3


def test_send_passes_requests_unchanged_and_sorts_the_replies(sandbox, running):
    log, _ = running("PhotoCraft", [])
    lines = ['{"id": 7, "method": "engine.execute", "params": {"command": "layer.new", "params": {"name": "글자"}}}', '{"method": "engine.execute", "params": {"command": "file.placeLinked", "params": {"path": "/x.png"}}}', '{"method": "test.notrun"}', '{"method": "test.noreply"}']
    r = sandbox.run("apps-send", "photocraft", stdin="\n".join(lines) + "\n")
    assert r.code == 1, r.raw
    assert [x["kind"] for x in r.out["replies"]] == ["ok", "refused_path", "not_run", "no_reply"]
    assert "Place Linked" in r.out["next"]
    got = fake_app.requests(log)
    assert got[0]["method"] == "auth" and got[0]["params"]["token"] == "f" * 64
    assert [json.dumps(g, ensure_ascii=False) for g in got[1:]] == [json.dumps(json.loads(l), ensure_ascii=False) for l in lines]


def test_send_with_a_wrong_token_is_refused(sandbox, running, tmp_path):
    running("PhotoCraft", [])
    for token_file in tmp_path.rglob("PhotoCraft.token"):
        token_file.write_text("0" * 64)
    r = sandbox.run("apps-send", "photocraft", stdin='{"method": "ui.inspect"}\n')
    assert r.code == 3 and "token" in r.out["error"]


def test_send_refuses_lines_that_are_not_requests(sandbox, running):
    running("PhotoCraft", [])
    assert sandbox.run("apps-send", "photocraft", stdin="not json\n").code == 2


@pytest.fixture
def versioned(sandbox):
    need("photocraft-cli")
    r = sandbox.run("new", "썸네일", "앱", "--request", "r", "--no-open")
    job = Path(r.out["job"])
    doc = job / "work" / "thumb.pcraft"
    assert photocraft("run", "--new", json.dumps({"width": 400, "height": 300}), *steps(("type.create", {"x": 10, "y": 60, "text": "가", "size": 40})), "--out", str(doc)).returncode == 0
    assert sandbox.run("version", job, "--kind", "composite", "--direction", "a").code == 0
    sandbox.job, sandbox.doc = job, doc
    return sandbox


@pytest.mark.slow
def test_an_open_document_is_versioned_only_through_the_app(versioned, running):
    log, _ = running("PhotoCraft", [versioned.doc])
    r = versioned.run("version", versioned.job, "--kind", "composite", "--direction", "a")
    assert r.code == 5 and "--from-app" in r.out["error"]
    r = versioned.run("version", versioned.job, "--kind", "composite", "--direction", "a", "--from-app")
    assert r.code == 0, r.raw + r.err
    assert r.out["saved_in_app"]["saved"] == str(versioned.doc.resolve())
    saves = [g for g in fake_app.requests(log) if g["method"] == "app.save"]
    assert saves == [{"id": saves[0]["id"], "method": "app.save", "params": {}}]  # its own path: no "path" sent
    assert json.loads((versioned.job / "job.json").read_text())["versions"][-1]["from_app"] is True


@pytest.mark.slow
def test_restore_refuses_an_open_document_and_a_portless_app(versioned, running):
    running("PhotoCraft", [versioned.doc])
    r = versioned.run("restore", versioned.job, "--version", "1")
    assert r.code == 5 and "open" in r.out["error"]


@pytest.mark.slow
def test_restore_refuses_when_photocraft_cannot_be_asked(versioned, running):
    running("PhotoCraft", [], control=False)
    r = versioned.run("restore", versioned.job, "--version", "1")
    assert r.code == 5 and "without a control port" in r.out["error"]
    r = versioned.run("version", versioned.job, "--kind", "composite", "--direction", "a")
    assert r.code == 0 and any("without a control port" in w for w in r.out["warnings"])


def test_vectorcraft_documents_are_matched_by_title(sandbox, running):
    log, _ = running("VectorCraft", [sandbox.data / "logo.vectorcraft"], token=None)
    r = sandbox.run("apps-status")
    vc = next(a for a in r.out["apps"] if a["app"] == "vectorcraft")
    assert vc["documents"] == [{"title": "logo.vectorcraft", "dirty": False, "active": True}]
    r = sandbox.run("apps-send", "vectorcraft", stdin='{"method": "ui.inspect"}\n')
    assert r.code == 0 and fake_app.requests(log)[0]["method"] == "ui.inspect"  # no auth line for VectorCraft
