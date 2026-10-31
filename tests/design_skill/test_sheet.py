"""The contact sheet in a real headless Chrome: enlarging an image, stepping with ← and →, closing with Esc."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from support.sandbox import ROOT

pytestmark = pytest.mark.slow
FAKE_CODEX = ROOT / "tests" / "support" / "fake_codex.py"


@pytest.fixture
def sheet(sandbox) -> Path:
    launcher = sandbox.bin / "codex"
    launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_CODEX}" "$@"\n')
    launcher.chmod(0o755)
    r = sandbox.run("new", "포스터", "시트", "--request", "r", "--aspect", "3:4", "--no-open")
    job = Path(r.out["job"])
    for _ in range(2):
        assert sandbox.run("add", job, "--direction", "d", "--kind", "generate", stdin="Portrait 3:4. A poster.").code == 0
    r = sandbox.run("generate", job, "--version", "1", "--version", "2", "--n", "2", env={"FAKE_CODEX_SCENARIO": "ok"})
    assert r.code == 0, r.raw
    return job / "contact-sheet.html"


def test_arrows_step_through_every_image_and_escape_closes(sheet):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception as exc:  # noqa: BLE001 -- no Chrome here is a skip, not a failure
            pytest.skip(f"Chrome could not be launched: {exc}")
        page = browser.new_page()
        page.goto(sheet.as_uri())
        names = page.eval_on_selector_all("img[data-zoom]", "els => els.map(e => e.dataset.name)")
        assert names == ["v1-1", "v1-2", "v2-1", "v2-2"]

        def shown():
            return page.eval_on_selector("#zoom .cap", "e => e.textContent").split()[0]

        page.click("img[data-name='v1-2']")
        assert page.eval_on_selector("#zoom", "d => d.open") and shown() == "v1-2"
        page.keyboard.press("ArrowRight")
        assert shown() == "v2-1"
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        assert shown() == "v1-1"  # wraps around
        page.keyboard.press("ArrowLeft")
        assert shown() == "v2-2"
        page.keyboard.press("Escape")
        assert not page.eval_on_selector("#zoom", "d => d.open")
        browser.close()
