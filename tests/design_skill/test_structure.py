"""The skill's code keeps the agreed tree: two top-level names, one-way imports, units used only through their interfaces, no sys.path edits."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from support.structure import check_tree

from support.sandbox import ROOT, SKILL
PKG = "design"


def test_real_tree_passes():
    assert check_tree(SKILL, ROOT / "tests") == []


def _skipped(directory: str, names: list[str]) -> set[str]:
    """__pycache__ at any depth, and only the top-level data/, which holds real jobs."""
    skipped = {n for n in names if n == "__pycache__"}
    if Path(directory) == SKILL and "data" in names:
        skipped.add("data")
    return skipped


@pytest.fixture
def broken(tmp_path):
    copy = tmp_path / "design"
    shutil.copytree(SKILL, copy, symlinks=True, ignore=_skipped)
    return copy


def append(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")


def test_extra_top_level_name_fails(broken):
    (broken / "scripts" / "helpers.py").write_text("x = 1\n")
    (broken / "notes.txt").write_text("x\n")
    problems = check_tree(broken)
    assert any("scripts/: unexpected top-level name 'helpers.py'" in p for p in problems)
    assert any("skill folder: unexpected top-level name 'notes.txt'" in p for p in problems)


def test_store_importing_feature_fails(broken):
    append(broken / "scripts" / PKG / "ledger" / "__init__.py", f"from {PKG} import sheet")
    assert any("store 'ledger' imports feature 'sheet'" in p for p in check_tree(broken))


def test_system_importing_store_fails(broken):
    append(broken / "scripts" / PKG / "codex" / "__init__.py", f"import {PKG}.ledger")
    assert any("system 'codex' imports store 'ledger'" in p for p in check_tree(broken))


def test_helper_importing_feature_fails(broken):
    append(broken / "scripts" / PKG / "paths.py", f"from {PKG} import fonts")
    assert any("helper 'paths' imports feature 'fonts'" in p for p in check_tree(broken))


def test_system_importing_feature_fails(broken):
    append(broken / "scripts" / PKG / "vision" / "__init__.py", f"import {PKG}.job")
    assert any("system 'vision' imports feature 'job'" in p for p in check_tree(broken))


@pytest.mark.parametrize("src, dst", [("sheet", "generate"), ("fonts", "job")])
def test_feature_importing_feature_outside_the_allowed_edges_fails(broken, src, dst):
    append(broken / "scripts" / PKG / src / "__init__.py", f"from {PKG} import {dst}")
    assert any(f"feature '{src}' imports feature '{dst}'" in p for p in check_tree(broken))


@pytest.mark.parametrize("system, a, b", [("codex", "generate", "job"), ("noonnu", "fonts", "sheet")])
def test_reaching_past_an_interface_fails(broken, system, a, b):
    inner = broken / "scripts" / PKG / system / "inner.py"
    inner.write_text("X = 1\n")
    append(broken / "scripts" / PKG / a / "__init__.py", f"from {PKG}.{system}.inner import X")
    append(broken / "scripts" / PKG / b / "__init__.py", f"from {PKG}.{system} import inner")
    problems = check_tree(broken)
    assert any(f"{a}/__init__.py" in p and f"reaches past the interface of '{system}'" in p for p in problems)
    assert any(f"{b}/__init__.py" in p and f"reaches past the interface of '{system}'" in p for p in problems)


@pytest.mark.parametrize("system", ["codex", "vision"])
def test_tests_reaching_past_an_interface_fails(broken, tmp_path, system):
    (broken / "scripts" / PKG / system / "inner.py").write_text("X = 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_x.py").write_text(f"from {PKG}.{system}.inner import X\n")
    assert any("test_x.py" in p and "reaches past" in p for p in check_tree(broken, tests))


@pytest.mark.parametrize("module", ["paths.py", "platforms.py"])
def test_sys_path_edit_fails(broken, module):
    append(broken / "scripts" / PKG / module, "import sys\nsys.path.insert(0, '/tmp')")
    append(broken / "scripts" / "cli.py", "sys.path[0:0] = ['/tmp']")
    problems = check_tree(broken)
    assert any(module in p and "edits sys.path" in p for p in problems)
    assert any("cli.py" in p and "edits sys.path" in p for p in problems)


def test_unclassified_unit_fails(broken):
    (broken / "scripts" / PKG / "extra.py").write_text("x = 1\n")
    assert any("unit 'extra' is not classified" in p for p in check_tree(broken))


def test_helper_importing_system_fails(broken):
    append(broken / "scripts" / PKG / "control.py", f"from {PKG} import photocraft")
    assert any("helper 'control' imports system 'photocraft'" in p for p in check_tree(broken))


def test_feature_importing_feature_is_allowed_only_for_named_edges(broken):
    append(broken / "scripts" / PKG / "version" / "__init__.py", f"from {PKG} import proof")
    assert any("feature 'version' imports feature 'proof'" in p for p in check_tree(broken))
    assert not any("feature 'version' imports feature 'sheet'" in p for p in check_tree(broken))
