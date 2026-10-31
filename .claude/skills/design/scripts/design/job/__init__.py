"""Starting a job, reading it back, and writing 성진's and Claude's judgments into it.

`new` makes the folder tree, the ledger and the contact sheet. `show` summarises one job, including what the ledger does not know yet (edits in work/ that no version holds, files too big for the vault's GitHub push), or every job in data/ with what outlives a job: accepted results and reusable notes, the earlier skill's jobs included, and the senior designer's references. `record` adds notes, critiques, choices and finals.
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from math import gcd
from pathlib import Path

from design import ledger, paths, platforms, sheet
from design.errors import Failure, Usage

__all__ = ["new", "show", "show_all", "record", "unversioned"]

DOC_SUFFIXES = (".pcraft", ".vectorcraft")


def _clone(src: Path, dest: Path) -> None:
    """Copy byte for byte, as an APFS clone where the volume allows (cp -c), never over an existing file."""
    if dest.exists():
        raise Usage(f"{dest.parent.name}/{dest.name} already exists; rename the file before handing it over")
    r = subprocess.run(["cp", "-c", str(src), str(dest)], capture_output=True, text=True)
    if r.returncode != 0:
        shutil.copy2(src, dest)


def new(kind: str, title: str, *, brief: dict, sources: list[Path], targets: list[Path], open_sheet: bool = True) -> dict:
    name = f"{paths.nfc(kind.strip())}_{datetime.date.today():%y%m%d}_{paths.nfc(title.strip())}"
    try:
        paths.check_name(name)
    except ValueError as exc:
        raise Usage(str(exc)) from exc
    job_dir = paths.data_root() / name
    if job_dir.exists():
        raise Usage(f"{job_dir} already exists; a job folder is never overwritten (show it, or pick another title)")
    if not brief.get("request"):
        raise Usage("new: the brief needs a request (what was asked for, in the asker's words)")
    missing = [str(p) for p in sources + targets if not p.is_file()]
    if missing:
        raise Usage("new: these files do not exist", missing=missing)
    stems = [p.name.casefold() for p in sources + targets]
    if len(set(stems)) != len(stems):
        raise Usage("new: two handed-over files share a name; rename one")
    platform = brief.get("platform")
    if platform and "size" not in brief:
        brief["size"] = list(platforms.get(platform).size)
    if brief.get("size") and "aspect" not in brief:
        w, h = brief["size"]
        g = gcd(w, h)
        if w // g <= 999 and h // g <= 999:
            brief["aspect"] = f"{w // g}:{h // g}"
    job_dir.mkdir(parents=True)
    try:
        for folder in paths.FOLDERS:
            (job_dir / folder).mkdir()
        for p in sources + targets:
            _clone(p, job_dir / "sources" / p.name)
        if targets:
            brief["targets"] = [f"sources/{p.name}" for p in targets]
        job = {"schema": ledger.SCHEMA, "id": name, "created": ledger.now(), "brief": brief, "versions": [], "notes": [], "finals": [], "exports": []}
        ledger.create(job_dir, job)
        sheet_path = sheet.rebuild(job_dir, open_it=open_sheet)
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)  # a half-made job would block the retry under the same name
        raise
    return {"job": str(job_dir), "sheet": str(sheet_path), "brief": brief, "sources": sorted(p.name for p in sources + targets), "next": "make the first draft in work/, then version it"}


def unversioned(job_dir: Path, job: dict) -> list[dict]:
    """Documents in work/ whose bytes match no snapshot of their latest version: edits (성진's in an app, or Claude's) that rebuilding or restoring would lose."""
    out = []
    work = job_dir / "work"
    for doc in sorted(p for p in work.rglob("*") if p.suffix in DOC_SUFFIXES and p.is_file()):
        stored = paths.stored(job_dir, doc)
        versions = [e for e in job["versions"] if e.get("source") == stored]
        if not versions:
            out.append({"file": stored, "state": "never versioned"})
            continue
        latest = versions[-1]
        snap = paths.from_stored(job_dir, latest["snapshot"])
        if not snap.is_file() or snap.read_bytes() != doc.read_bytes():
            out.append({"file": stored, "state": f"changed since v{latest['v']}"})
    return out


def show(job_dir: Path) -> dict:
    job = ledger.read(job_dir)
    rows = []
    for e in job["versions"]:
        row = {"v": e["v"], "kind": e["kind"], "direction": e["direction"]}
        for key in ("parent", "change", "render", "snapshot", "chosen", "restored_from"):
            if e.get(key) is not None:
                row[key] = e[key]
        if e["kind"] in ledger.GEN_KINDS:
            row["ok"] = ledger.ok_attempts(e)
            row["failed"] = sum(1 for a in e["attempts"] if a["status"] not in ("ok", "running"))
        if e.get("critique"):
            row["critique_first_line"] = e["critique"].splitlines()[0]
        rows.append(row)
    changes = unversioned(job_dir, job)
    large = paths.large_files(job_dir)
    bits = [f"{len(job['versions'])} versions", f"{len(job['finals'])} finals", f"{len(job['exports'])} exports"]
    if changes:
        bits.append(f"{len(changes)} document(s) with changes no version holds")
    if large:
        bits.append(f"{len(large)} file(s) over {paths.LARGE_FILE // 1024 // 1024} MiB")
    out = {"summary": " · ".join(bits), "brief": job["brief"], "notes": [f"[{n['scope']}] {n['text']}" + (f" (v{n['version']})" if "version" in n else "") for n in job["notes"]], "versions": rows, "finals": job["finals"], "exports": job["exports"], "sheet": str(job_dir / sheet.SHEET)}
    if changes:
        out["unversioned"] = changes
    if large:
        out["large_files"] = large
    return out


def show_all() -> dict:
    root = paths.data_root()
    jobs, earlier = [], []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        if paths.is_job(d):
            try:
                doc = json.loads((d / paths.LEDGER).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                earlier.append({"job": d.name, "error": "job.json does not parse"})
                continue
            if doc.get("schema") == ledger.SCHEMA:
                m = paths.NAME.fullmatch(paths.nfc(d.name))
                finals = []
                for f in doc.get("finals", []):
                    v, k = ledger.parse_name(f)
                    entry = next((e for e in doc["versions"] if e["v"] == v), {})
                    finals.append(str(d / entry["render"]) if k is None and entry.get("render") else str(d / "versions" / f"{f}.png"))
                jobs.append({"job": d.name, "kind": m["kind"] if m else None, "date": m["date"] if m else None, "request": doc["brief"].get("request"), "versions": len(doc["versions"]), "finals": finals, "reusable_notes": [n["text"] for n in doc["notes"] if n["scope"] == "reusable"]})
                continue
        old = ledger.legacy_summary(d)
        if old:
            earlier.append(old)
    refs = root / paths.REFERENCES
    references = {}
    if refs.is_dir():
        for p in sorted(refs.rglob("*")):
            if p.is_file() and p.name != ".DS_Store":
                references.setdefault(str(p.parent.relative_to(refs)) if p.parent != refs else ".", []).append(p.name)
    notes = sum(len(j["reusable_notes"]) for j in jobs + earlier if "reusable_notes" in j)
    return {"summary": f"{len(jobs)} jobs, {len(earlier)} from the earlier skill (read only), {notes} reusable notes, {sum(len(v) for v in references.values())} reference images", "jobs": jobs, "earlier": earlier, "references": {"folder": str(refs), "by_folder": references}}


def record(job_dir: Path, *, notes: list[str], scope: str, version: int | None, critique: str | None, chosen: str | None, finals: list[str], unfinals: list[str]) -> dict:
    written = []
    with ledger.edit(job_dir) as job:
        entry = ledger.version(job, version) if version is not None else None
        at = ledger.now()
        for text in notes:
            note = {"text": text, "scope": scope, "at": at}
            if version is not None:
                note["version"] = version
            job["notes"].append(note)
            written.append("note")
        if critique is not None:
            entry["critique"] = critique
            written.append("critique")
        if chosen is not None:
            if entry["kind"] not in ledger.GEN_KINDS:
                raise Failure(f"v{version} is a {entry['kind']} version; --chosen picks one attempt of a generated version")
            if chosen not in ledger.ok_attempts(entry):
                raise Failure(f"{chosen} is not an ok attempt of v{version} (ok: {ledger.ok_attempts(entry) or 'none'})")
            entry["chosen"] = chosen
            written.append("chosen")
        can = ledger.deliverables(job)
        for name in finals:
            ledger.parse_name(name)
            if name not in can:
                raise Failure(f"{name} is not a rendered version or an ok attempt of this job")
            if name not in job["finals"]:
                job["finals"].append(name)
            written.append(f"final {name}")
        for name in unfinals:
            if name not in job["finals"]:
                raise Failure(f"{name} is not among the finals ({job['finals'] or 'none'})")
            job["finals"].remove(name)
            written.append(f"unfinal {name}")
    sheet.rebuild(job_dir)
    return {"written": written, "finals": job["finals"]}
