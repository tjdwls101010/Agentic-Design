"""What the running apps do that SKILL.md relies on, checked against the real apps. Opens app windows on the screen, so it runs only with -m app, when 성진 knows. Each test names the SKILL.md section whose sentence it backs."""

from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path

import pytest

from support.fontfiles import build
from support.tools import lightcraft, photocraft, steps

pytestmark = pytest.mark.app


def _quit(sandbox, app: str) -> None:
    sandbox.run("apps-send", app, stdin='{"method": "app.quit"}\n')
    time.sleep(1)
    sandbox.run("apps-send", app, stdin='{"method": "ui.dialog.confirm", "params": {"dialog": "discard", "choice": "dontSave"}}\n' if app == "photocraft" else '{"method": "ui.dialog.set", "params": {"dialog": "saveChanges", "field": "discard", "value": true}}\n{"method": "ui.dialog.confirm", "params": {"dialog": "saveChanges"}}\n')
    time.sleep(2)


@pytest.fixture
def photocraft_app(sandbox):
    from design import control

    if control.processes("PhotoCraft"):
        pytest.skip("PhotoCraft is already running; it is 성진's")
    doc = sandbox.data / "작업" / "doc.pcraft"
    doc.parent.mkdir()
    assert photocraft("run", "--new", json.dumps({"width": 800, "height": 600}), *steps(("type.create", {"x": 10, "y": 60, "text": "가", "size": 40})), "--out", str(doc)).returncode == 0
    r = sandbox.run("apps-open", "photocraft", "--doc", doc)
    assert r.code == 0, r.raw + r.err
    yield sandbox, doc
    _quit(sandbox, "photocraft")


def send(sandbox, app, *requests) -> list[dict]:
    r = sandbox.run("apps-send", app, stdin="\n".join(json.dumps(x, ensure_ascii=False) for x in requests) + "\n")
    return r.out["replies"]


def documents(sandbox) -> list[dict]:
    return next(a for a in sandbox.run("apps-status").out["apps"] if a["app"] == "photocraft")["documents"]


def test_photocraft_bridge_facts(photocraft_app, tmp_path):
    """Working in the running apps: the vault's resolved path (emoji included) works as automation root; the bridge refuses file.placeLinked; app.save to another path makes that path the document's file; an edit made in the window shows in ui.inspect; a font installed after launch is not seen until restart."""
    sandbox, doc = photocraft_app
    assert [d["path"] for d in documents(sandbox)] == [str(doc.resolve())]
    (reply,) = send(sandbox, "photocraft", {"method": "engine.execute", "params": {"command": "file.placeLinked", "params": {"path": str(doc)}}})
    assert reply["kind"] == "refused_path"
    send(sandbox, "photocraft", {"method": "engine.execute", "params": {"command": "layer.select", "params": {"name": "Background"}}}, {"method": "ui.set", "params": {"tool": "brush", "brushSize": 30}})
    send(sandbox, "photocraft", {"method": "ui.pointer", "params": {"events": [{"kind": "down", "x": 100, "y": 100}, {"kind": "move", "x": 400, "y": 300}, {"kind": "up", "x": 400, "y": 300}]}})
    time.sleep(1)
    assert documents(sandbox)[0]["dirty"] is True
    other = doc.with_name("other.pcraft")
    send(sandbox, "photocraft", {"method": "app.save", "params": {"path": str(other)}})
    assert [d["path"] for d in documents(sandbox)] == [str(other.resolve())]
    font = Path.home() / "Library" / "Fonts" / "ZzDesignLate-Regular.ttf"
    build(font, family="ZzDesign Late", chars="가")
    try:
        (reply,) = send(sandbox, "photocraft", {"method": "engine.execute", "params": {"command": "type.fonts", "params": {"family": "ZzDesign Late"}}})
        assert reply["result"]["faces"] == []
        assert "ZzDesignLate-Regular" in photocraft("run", "--new", '{"width":8,"height":8}', *steps(("type.fonts", {"family": "ZzDesign Late"}))).stdout
    finally:
        font.unlink(missing_ok=True)


def test_vectorcraft_takes_absolute_paths_only(sandbox):
    """Working in the running apps: VectorCraft's bridge refuses a relative path and opens an absolute one."""
    from design import control

    if control.processes("VectorCraft"):
        pytest.skip("VectorCraft is already running; it is 성진's")
    doc = sandbox.data / "logo.vectorcraft"
    subprocess.run(["vectorcraft-cli", "run", *steps(("text.create", {"x": 10, "y": 60, "text": "가", "size": 40})), "--export", str(doc)], check=True, capture_output=True)
    r = sandbox.run("apps-open", "vectorcraft", "--doc", doc)
    try:
        assert r.code == 0, r.raw
        (rel,) = send(sandbox, "vectorcraft", {"method": "app.open", "params": {"path": "logo.vectorcraft"}})
        assert rel["kind"] == "refused_path"
        vc = next(a for a in sandbox.run("apps-status").out["apps"] if a["app"] == "vectorcraft")
        assert vc["documents"][0]["title"] == "logo.vectorcraft"
    finally:
        _quit(sandbox, "vectorcraft")


def test_lightcraft_opens_on_the_jobs_library(sandbox):
    """Working in the running apps: LightCraft starts on a job's library and is driven with lightcraft-cli run --connect."""
    from design import control

    if control.processes("LightCraft"):
        pytest.skip("LightCraft is already running; it is 성진's")
    library = sandbox.data / "job" / "work" / "lightcraft"
    library.parent.mkdir(parents=True)
    r = sandbox.run("apps-open", "lightcraft", "--doc", library)
    try:
        assert r.code == 0, r.raw + r.err
        r2 = lightcraft("run", "--connect", "127.0.0.1:7980", "library.info")
        assert r2.returncode == 0 and str(library) in r2.stdout
        lc = next(a for a in sandbox.run("apps-status").out["apps"] if a["app"] == "lightcraft")
        assert Path(lc["library"]).resolve() == library.resolve()
    finally:
        try:
            with socket.create_connection(("127.0.0.1", 7980), timeout=5) as s:
                s.sendall(b'{"id":1,"method":"app.quit","params":{}}\n')
        except OSError:
            pass
        time.sleep(2)
