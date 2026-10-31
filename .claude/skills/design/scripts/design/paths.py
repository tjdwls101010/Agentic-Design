"""Where things live: the data folder (the vault, resolved through its symlink), a job's folder name rule and its subfolders, the fonts folder, writing a file that must not exist yet, and the size check that keeps a job's files under GitHub's per-file limit.

A job is a folder holding job.json. A short name is one folder under `data/`; anything that starts with `/`, `~` or `.` is a path used as written. Names are NFC-normalised because APFS hands back NFD while argv carries NFC, and the two spellings of one Korean name compare unequal everywhere they are quoted.
"""

from __future__ import annotations

import datetime
import os
import re
import unicodedata
import uuid
from pathlib import Path

from design.errors import Failure

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
LEDGER = "job.json"
# sources: material handed over, never edited · assets: mattes, cut-outs, generated images, developed photos, textures, chart SVGs · work: the current editable documents · versions: snapshots and renders of every version · proof: disposable check sheets · exports: deliveries · etc: logs
FOLDERS = ("sources", "assets", "work", "versions", "proof", "exports", "etc")
NAME = re.compile(r"(?P<kind>[^_/]+)_(?P<date>\d{6})_(?P<title>[^/]*\S[^/]*)")
REFERENCES = "_references"
# GitHub refuses a file over 100 MiB and the vault is pushed there; warn with room to spare.
LARGE_FILE = 90 * 1024 * 1024


def data_root() -> Path:
    """`DESIGN_DATA` when set (tests), else the skill's `data/` with its symlink resolved: the apps compare automation roots and link paths as text, so the vault's real path is the only spelling used."""
    override = os.environ.get("DESIGN_DATA")
    return Path(override).expanduser().resolve() if override else (SKILL_DIR / "data").resolve()


def fonts_dir() -> Path:
    """`DESIGN_FONTS_DIR` when set (tests), else the user's font folder, which PhotoCraft, VectorCraft and LightCraft all read."""
    override = os.environ.get("DESIGN_FONTS_DIR")
    return Path(override).expanduser() if override else Path.home() / "Library" / "Fonts"


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def is_path(raw: str) -> bool:
    return raw.startswith(("/", "~", "."))


def resolve_job(raw: str) -> Path:
    """A short name → data/<name>; `/…`, `~…`, `./…`, `../…` → that path. Raises ValueError for an empty name or a short name with a slash in it."""
    raw = nfc(raw.strip())
    if not raw:
        raise ValueError("a job cannot be empty")
    if is_path(raw):
        return Path(raw).expanduser().resolve()
    if "/" in raw:
        raise ValueError(f"{raw!r}: a short name is one folder under data/; give a path (./…, ../…, ~/…, /…) for a job anywhere else")
    return data_root() / raw


def check_name(raw: str) -> None:
    """A new job's short name must read <kind>_<YYMMDD>_<title>, the date a real one. Raises ValueError."""
    raw = nfc(raw.strip())
    m = NAME.fullmatch(raw)
    if not m:
        raise ValueError(f"{raw!r}: a new job's short name must read <kind>_<YYMMDD>_<title>, e.g. 썸네일_261031_국정감사")
    try:
        datetime.datetime.strptime(m["date"], "%y%m%d")
    except ValueError:
        raise ValueError(f"{raw!r}: {m['date']} is not a date in YYMMDD") from None


def resolve_input(raw: str | Path) -> Path:
    """An input file named on the command line: absolute, or relative to the caller's cwd."""
    return Path(nfc(str(raw))).expanduser().resolve()


def is_job(path: Path) -> bool:
    return (path / LEDGER).is_file()


def job_of(path: Path) -> Path | None:
    """The job a file sits in: the nearest folder above it that holds job.json."""
    for parent in path.resolve().parents:
        if is_job(parent):
            return parent
    return None


def stored(job_dir: Path, path: Path) -> str:
    """How a path is written into the ledger: relative to the job folder when inside it, else absolute."""
    path = path.resolve()
    try:
        return str(path.relative_to(job_dir.resolve()))
    except ValueError:
        return str(path)


def from_stored(job_dir: Path, value: str) -> Path:
    """The inverse of `stored`."""
    p = Path(value)
    return p if p.is_absolute() else job_dir / p


def place_new(dest: Path, write) -> None:
    """Write a file that must not exist yet. `write(tmp)` writes beside it under a temporary name with the same extension, which is then linked into place, so `dest` never holds a half-written file and a file already there is never replaced."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.stem}.{uuid.uuid4().hex[:8]}{dest.suffix}")
    try:
        write(tmp)
        try:
            os.link(tmp, dest)
        except FileExistsError:
            raise Failure(f"{dest} already exists; it is never overwritten") from None
    finally:
        tmp.unlink(missing_ok=True)


def large_files(folder: Path) -> list[dict]:
    """Files under `folder`, whoever wrote them, at or over LARGE_FILE: GitHub refuses a file over 100 MiB, and the vault is pushed there."""
    out = []
    for root, _, files in os.walk(folder):
        for name in files:
            p = Path(root) / name
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size >= LARGE_FILE:
                out.append({"file": str(p), "mib": round(size / 1024 / 1024, 1)})
    return sorted(out, key=lambda d: -d["mib"])
