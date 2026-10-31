"""Fixtures every test folder shares."""

from __future__ import annotations

import pytest

from support.sandbox import Sandbox, make_sandbox


@pytest.fixture
def sandbox(tmp_path) -> Sandbox:
    return make_sandbox(tmp_path)
