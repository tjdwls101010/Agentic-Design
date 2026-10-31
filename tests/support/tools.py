"""Finding the external tools a test needs, and running the ArtCraft CLIs directly (not through the skill), for tests of what those tools do."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        pytest.skip(f"{tool} is not installed")
    return path


def lines(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip().startswith("{")]


def photocraft(*args: str, cwd: Path | None = None, input: str | None = None, timeout: float = 300) -> subprocess.CompletedProcess:
    need("photocraft-cli")
    return subprocess.run(["photocraft-cli", *args], capture_output=True, text=True, cwd=cwd, input=input, timeout=timeout)


def vectorcraft(*args: str, cwd: Path | None = None, timeout: float = 300) -> subprocess.CompletedProcess:
    need("vectorcraft-cli")
    return subprocess.run(["vectorcraft-cli", *args], capture_output=True, text=True, cwd=cwd, timeout=timeout)


def lightcraft(*args: str, cwd: Path | None = None, timeout: float = 300) -> subprocess.CompletedProcess:
    need("lightcraft-cli")
    return subprocess.run(["lightcraft-cli", *args], capture_output=True, text=True, cwd=cwd, timeout=timeout)


def steps(*pairs) -> list[str]:
    """--cmd/--params argv from (command, params) pairs."""
    argv = []
    for command, params in pairs:
        argv += ["--cmd", command, "--params", json.dumps(params, ensure_ascii=False)]
    return argv
