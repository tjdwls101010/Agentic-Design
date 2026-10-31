"""Run the real CLI the way the skill is deployed (`uv run cli.py`, its PEP 723 header) in a sandbox: a temporary data folder, fonts folder, CODEX_HOME and PATH under a folder whose name has a space and Korean, like the real vault."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "design"
CLI = SKILL / "scripts" / "cli.py"
FIXTURES = ROOT / "tests" / "fixtures"
# Absolute, so a test that narrows PATH (to hide a tool) still starts the CLI.
UV = shutil.which("uv") or "uv"


@dataclass
class Result:
    code: int
    out: dict | None
    err: str
    raw: str


@dataclass
class Sandbox:
    root: Path
    data: Path
    fonts: Path
    codex_home: Path
    bin: Path
    env: dict

    def run(self, *args, stdin: str | None = None, env: dict | None = None, timeout: float = 600) -> Result:
        proc = subprocess.run([UV, "run", "--quiet", str(CLI), *map(str, args)], input=stdin, capture_output=True, text=True, env={**self.env, **(env or {})}, timeout=timeout, cwd=self.root)
        try:
            out = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError:
            out = None
        return Result(proc.returncode, out, proc.stderr, proc.stdout)

    def popen(self, *args, stdin: str | None = None, env: dict | None = None) -> subprocess.Popen:
        return subprocess.Popen([UV, "run", "--quiet", str(CLI), *map(str, args)], stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**self.env, **(env or {})}, cwd=self.root)

    def opened(self) -> list[str]:
        log = self.root / "opened.log"
        return log.read_text().splitlines() if log.exists() else []


def make_sandbox(tmp_path: Path) -> Sandbox:
    root = tmp_path / "작업 공간"
    data = root / "🎨 data"
    data.mkdir(parents=True)
    fonts = root / "Fonts"
    fonts.mkdir()
    home = root / "codex-home"
    home.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    # A fake `open` so tests never launch a browser or an app; it records what would have been opened.
    fake = bin_dir / "open"
    fake.write_text(f"#!/bin/sh\necho \"$@\" >> '{root / 'opened.log'}'\n")
    fake.chmod(0o755)
    env = {**os.environ, "DESIGN_DATA": str(data), "DESIGN_FONTS_DIR": str(fonts), "CODEX_HOME": str(home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "PYTHONUNBUFFERED": "1"}
    for key in ("FAKE_CODEX_SCENARIO", "VIRTUAL_ENV"):
        env.pop(key, None)
    return Sandbox(root, data, fonts, home, bin_dir, env)
