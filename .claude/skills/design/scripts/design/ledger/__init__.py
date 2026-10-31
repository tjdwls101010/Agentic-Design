"""The job ledger, job.json: the only place a job's brief, versions, attempts, judgments, finals and exports live.

Every write goes through `edit` (or `create`), which holds the job's lock, checks the whole document against the schema and replaces the file atomically. Reading closes attempts left `running` by a process that has died, as `interrupted`. Ledgers the earlier skill wrote (schema 4 and before) are read only, through `legacy`.

An attempt is one try at a generated image. Its id and file name, `v{N}-{k}`, count every try of the version, so no run ever reuses a file name. A running attempt changes to its result exactly once; a finished one never changes.
"""

from __future__ import annotations

import os
from pathlib import Path

from design.errors import Failure

from .legacy import summary as legacy_summary
from .schema import DOC_KINDS, GEN_KINDS, KINDS, SCHEMA, deliverables, ok_attempts, validate
from .store import create, edit, exists, now, read

__all__ = ["SCHEMA", "KINDS", "DOC_KINDS", "GEN_KINDS", "create", "edit", "exists", "read", "now", "validate", "ok_attempts", "deliverables", "legacy_summary", "version", "latest_for", "add_version", "new_attempt", "start_attempt", "finish_attempt", "parse_name"]


def version(job: dict, v: int) -> dict:
    for entry in job["versions"]:
        if entry["v"] == v:
            return entry
    raise Failure(f"no version {v} in this job (has: {[e['v'] for e in job['versions']] or 'none'})")


def latest_for(job: dict, source: str) -> dict | None:
    """The newest version whose document is `source` (a path as the ledger stores it), or None."""
    found = [e for e in job["versions"] if e.get("source") == source]
    return found[-1] if found else None


def add_version(job: dict, fields: dict, v: int | None = None) -> dict:
    """Append a version with the next number (or `v`, which must be free and higher than every other); `fields` holds everything but v and created (a generated version also gets an empty attempts list)."""
    top = max((e["v"] for e in job["versions"]), default=0)
    if v is not None and v <= top:
        raise Failure(f"v{v} is not past the last version (v{top})")
    entry = {"v": v if v is not None else top + 1, **fields, "created": now()}
    if entry["kind"] in GEN_KINDS:
        entry.setdefault("attempts", [])
    if entry.get("parent") is not None:
        version(job, entry["parent"])
    job["versions"].append(entry)
    return entry


def new_attempt(entry: dict) -> dict:
    """Open a running attempt on a generated version held inside `edit`. Returns the row; its file name is `row['id'] + '.png'`."""
    k = len(entry["attempts"]) + 1
    row = {"id": f"v{entry['v']}-{k}", "status": "running", "started": now(), "pid": os.getpid()}
    entry["attempts"].append(row)
    return row


def start_attempt(job_dir: Path, v: int) -> dict:
    with edit(job_dir) as job:
        return dict(new_attempt(version(job, v)))


def finish_attempt(job_dir: Path, v: int, attempt_id: str, fields: dict) -> dict:
    """Turn a running attempt into its result. `fields` must include the final `status`."""
    with edit(job_dir) as job:
        for row in version(job, v)["attempts"]:
            if row["id"] == attempt_id:
                if row["status"] != "running":
                    raise Failure(f"attempt {attempt_id} already finished as {row['status']}")
                row.update(fields)
                return dict(row)
    raise Failure(f"no attempt {attempt_id} in version {v}")


def parse_name(name: str) -> tuple[int, int | None]:
    """vN → (N, None); vN-k → (N, k). Raises Failure for anything else."""
    from .schema import NAME

    m = NAME.fullmatch(name.strip())
    if not m:
        raise Failure(f"{name!r} is not a version name (v3) or an attempt name (v3-2)")
    return int(m[1]), int(m[2]) if m[2] else None
