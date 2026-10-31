"""The ledger's schema (5) as its validator states it: what a valid job looks like and what is refused before it is written."""

from __future__ import annotations

import copy

from design import ledger


def job(**over) -> dict:
    doc = {"schema": 5, "id": "썸네일_261031_x", "created": "t", "brief": {"request": "r", "size": [1920, 1080], "aspect": "16:9"}, "notes": [], "finals": [], "exports": [],
           "versions": [
               {"v": 1, "kind": "composite", "direction": "d", "created": "t", "app": "photocraft", "source": "work/x.pcraft", "snapshot": "versions/v1.pcraft", "render": "versions/v1.png", "size": [1920, 1080]},
               {"v": 2, "kind": "generate", "direction": "prop", "created": "t", "prompt": "p", "refs": [], "aspect": "none", "transparent": True, "attempts": [{"id": "v2-1", "status": "ok", "started": "t", "file": "v2-1.png"}, {"id": "v2-2", "status": "refused", "started": "t"}]},
           ]}
    doc.update(over)
    return doc


def test_a_valid_job_has_no_problems():
    assert ledger.validate(job(finals=["v1", "v2-1"], exports=[{"path": "/x.jpg", "of": "v1", "format": "jpg", "at": "t", "size": [1920, 1080], "bytes": 10}])) == []


def test_unknown_keys_are_errors_everywhere():
    doc = job()
    doc["versions"][0]["layers"] = 3
    doc["brief"]["mood"] = "warm"
    problems = ledger.validate(doc)
    assert "versions[v=1]: unknown key 'layers'" in problems and "brief: unknown key 'mood'" in problems


def test_a_document_version_needs_its_snapshot_and_render_and_no_prompt():
    doc = job()
    del doc["versions"][0]["render"]
    doc["versions"][0]["prompt"] = "p"
    problems = ledger.validate(doc)
    assert "versions[v=1]: a composite version needs 'render'" in problems and "versions[v=1]: a composite version has no 'prompt'" in problems


def test_finals_name_only_rendered_versions_or_ok_attempts():
    problems = ledger.validate(job(finals=["v2-2", "v9"]))
    assert "finals: 'v2-2' is not a rendered version or an ok attempt" in problems and "finals: 'v9' is not a rendered version or an ok attempt" in problems


def test_a_parent_must_come_earlier_and_notes_name_real_versions():
    doc = job(notes=[{"text": "x", "scope": "job", "at": "t", "version": 7}])
    doc["versions"][0]["parent"] = 2
    problems = ledger.validate(doc)
    assert "versions[v=1]: parent 2 is not an earlier version" in problems and "notes[0]: version 7 is not a version of this job" in problems


def test_parse_name():
    assert ledger.parse_name("v12") == (12, None) and ledger.parse_name("v3-2") == (3, 2)
