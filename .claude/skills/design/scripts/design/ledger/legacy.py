"""Jobs the earlier skill left in data/, read only: schema 4 ledgers (generated, rendered and graded versions with finals and scoped notes) and the oldest card jobs with no ledger at all (card-N.png beside the HTML that drew them).

What carries over is what outlives one job: which images were accepted and the notes 성진 marked reusable.
"""

from __future__ import annotations

import json
from pathlib import Path

from design import paths


def summary(job_dir: Path) -> dict | None:
    """kind, date, title, finals (paths) and reusable notes of an earlier job, or None when the folder is not one."""
    m = paths.NAME.fullmatch(paths.nfc(job_dir.name))
    ledger = job_dir / "job.json"
    if ledger.is_file():
        try:
            job = json.loads(ledger.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"job": job_dir.name, "schema": None, "error": "job.json does not parse"}
        if not isinstance(job, dict) or job.get("schema") not in (1, 2, 3, 4):
            return None
        brief = job.get("brief") if isinstance(job.get("brief"), dict) else {}
        notes = [n["text"] for n in brief.get("notes") or [] if isinstance(n, dict) and n.get("scope") == "reusable" and isinstance(n.get("text"), str)]
        finals = [str(job_dir / "versions" / f) for f in job.get("finals") or [] if isinstance(f, str)]
        return {"job": job_dir.name, "schema": job.get("schema"), "kind": m["kind"] if m else None, "date": m["date"] if m else None, "request": brief.get("request"), "finals": finals, "reusable_notes": notes}
    cards = sorted(str(p) for p in job_dir.glob("card-*.png"))
    if not cards:
        return None
    return {"job": job_dir.name, "schema": None, "kind": m["kind"] if m else None, "date": m["date"] if m else None, "finals": cards, "reusable_notes": []}
