"""The shape of job.json (schema 5), checked in full before every write.

Unknown keys are errors: the ledger grows by decision, not by a typo that silently drops a field from the sheet.

A version is either a document version (composite, grade, vector, layout: a snapshot of the editable original and its render) or a generated one (generate, edit: a gpt-image prompt and its attempts). Finals and exports name what they deliver as `vN` (a document version) or `vN-k` (one attempt of a generated version).
"""

from __future__ import annotations

import re

SCHEMA = 5

DOC_KINDS = ("composite", "grade", "vector", "layout")
GEN_KINDS = ("generate", "edit")
KINDS = DOC_KINDS + GEN_KINDS
APPS = ("photocraft", "vectorcraft", "lightcraft")
STATUSES = ("ok", "running", "interrupted", "refused", "executor_error", "timeout", "prompt_altered", "path_mismatch", "silent_no_image")
VERBATIM = ("exact", "normalized", "unverified", "mismatch")
SCOPES = ("job", "reusable")
FORMATS = ("png", "jpg", "pdf")
DETAIL_KEYS = {"code", "message", "moderation_stage", "categories", "returncode", "events_file", "agent_message", "tries"}

ASPECT = re.compile(r"[1-9]\d{0,2}:[1-9]\d{0,2}")
NAME = re.compile(r"v(\d+)(?:-(\d+))?")

# key: (type or tuple of types, required)
TOP = {"schema": (int, True), "id": (str, True), "created": (str, True), "sheet_opened": (str, False), "brief": (dict, True), "versions": (list, True), "notes": (list, True), "finals": (list, True), "exports": (list, True)}
BRIEF = {"request": (str, True), "purpose": (str, False), "size": (list, False), "aspect": (str, False), "platform": (str, False), "text": (list, False), "reserved": (list, False), "targets": (list, False)}
NOTE = {"text": (str, True), "scope": (str, True), "at": (str, True), "version": (int, False)}
VERSION = {"v": (int, True), "kind": (str, True), "direction": (str, True), "created": (str, True), "parent": (int, False), "change": (str, False), "critique": (str, False),
           # document versions
           "app": (str, False), "source": (str, False), "snapshot": (str, False), "render": (str, False), "size": (list, False), "from_app": (bool, False), "restored_from": (int, False),
           # generated versions
           "prompt": (str, False), "refs": (list, False), "aspect": (str, False), "transparent": (bool, False), "attempts": (list, False), "chosen": (str, False)}
DOC_ONLY = ("app", "source", "snapshot", "render", "size", "from_app", "restored_from")
GEN_ONLY = ("prompt", "refs", "aspect", "transparent", "attempts", "chosen")
ATTEMPT = {"id": (str, True), "status": (str, True), "started": (str, True), "pid": (int, False), "elapsed_s": ((int, float), False), "file": (str, False), "w": (int, False), "h": (int, False), "aspect_ok": (bool, False), "alpha": (dict, False), "verbatim": (str, False), "retried": (dict, False), "thread_id": (str, False), "detail": (dict, False)}
ALPHA = {"has_alpha": (bool, True), "transparent_share": ((int, float), True)}
RETRIED = {"thread_id": (str, False), "elapsed_s": ((int, float), False), "verbatim": (str, False), "events_file": (str, False)}
EXPORT = {"path": (str, True), "of": (str, True), "format": (str, True), "at": (str, True), "size": (list, True), "bytes": (int, True), "target": (str, False), "violations": (list, False), "warnings": (list, False)}


def _shape(where: str, obj, spec: dict, errors: list) -> bool:
    if not isinstance(obj, dict):
        errors.append(f"{where}: expected an object, got {type(obj).__name__}")
        return False
    for key, (kind, required) in spec.items():
        if key not in obj:
            if required:
                errors.append(f"{where}: missing required key '{key}'")
            continue
        value = obj[key]
        if isinstance(value, bool) and kind in (int, (int, float)):
            errors.append(f"{where}: '{key}' must be a number, got bool")
        elif not isinstance(value, kind):
            names = kind.__name__ if isinstance(kind, type) else "/".join(k.__name__ for k in kind)
            errors.append(f"{where}: '{key}' must be {names}, got {type(value).__name__}")
    for key in sorted(set(obj) - set(spec)):
        errors.append(f"{where}: unknown key '{key}'")
    return True


def _strings(where: str, value, errors: list) -> None:
    if isinstance(value, list) and not all(isinstance(x, str) for x in value):
        errors.append(f"{where}: every entry must be a string")


def _size(where: str, value, errors: list) -> None:
    if value is not None and not (isinstance(value, list) and len(value) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in value)):
        errors.append(f"{where}: size must be [width, height] in whole pixels")


def ok_attempts(version: dict) -> list[str]:
    """Attempt ids of a generated version that finished ok: the only ones that can be chosen or made final."""
    return [a["id"] for a in version.get("attempts") or [] if isinstance(a, dict) and a.get("status") == "ok" and a.get("file")]


def deliverables(job: dict) -> set[str]:
    """Every name a final or an export can take: vN for a document version with a render, vN-k for an ok attempt."""
    out = set()
    for entry in job.get("versions") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("kind") in DOC_KINDS and entry.get("render"):
            out.add(f"v{entry.get('v')}")
        out.update(ok_attempts(entry))
    return out


def validate(job) -> list[str]:
    errors: list[str] = []
    if not _shape("job", job, TOP, errors):
        return errors
    if job.get("schema") != SCHEMA:
        errors.append(f"job: schema must be {SCHEMA}, got {job.get('schema')!r}")

    brief = job.get("brief")
    if _shape("brief", brief, BRIEF, errors):
        aspect = brief.get("aspect")
        if isinstance(aspect, str) and not ASPECT.fullmatch(aspect):
            errors.append(f"brief: aspect must be W:H, got {aspect!r}")
        _size("brief", brief.get("size"), errors)
        for key in ("text", "reserved", "targets"):
            _strings(f"brief.{key}", brief.get(key), errors)

    numbers: set = set()
    ids: set = set()
    files: set = set()
    for entry in job.get("versions") if isinstance(job.get("versions"), list) else []:
        where = f"versions[v={entry.get('v')}]" if isinstance(entry, dict) else "versions[]"
        if not _shape(where, entry, VERSION, errors):
            continue
        num = entry.get("v")
        if num in numbers:
            errors.append(f"{where}: duplicate version number")
        numbers.add(num)
        for key in ("parent", "restored_from"):
            ref = entry.get(key)
            if ref is not None and (ref not in numbers or ref == num):
                errors.append(f"{where}: {key} {ref} is not an earlier version")
        kind = entry.get("kind")
        if kind not in KINDS:
            errors.append(f"{where}: kind must be one of {list(KINDS)}, got {kind!r}")
        elif kind in DOC_KINDS:
            for key in ("app", "source", "snapshot", "render"):
                if key not in entry:
                    errors.append(f"{where}: a {kind} version needs '{key}'")
            for key in GEN_ONLY:
                if key in entry:
                    errors.append(f"{where}: a {kind} version has no '{key}'")
            if entry.get("app") is not None and entry["app"] not in APPS:
                errors.append(f"{where}: app must be one of {list(APPS)}")
            _size(where, entry.get("size"), errors)
        else:
            for key in ("prompt", "refs", "aspect", "transparent", "attempts"):
                if key not in entry:
                    errors.append(f"{where}: a {kind} version needs '{key}'")
            for key in DOC_ONLY:
                if key in entry:
                    errors.append(f"{where}: a {kind} version has no '{key}'")
            if kind == "edit" and not entry.get("refs"):
                errors.append(f"{where}: an edit version needs at least one ref")
            aspect = entry.get("aspect")
            if isinstance(aspect, str) and aspect != "none" and not ASPECT.fullmatch(aspect):
                errors.append(f"{where}: aspect must be W:H or none, got {aspect!r}")
            _strings(f"{where}.refs", entry.get("refs"), errors)
            for i, attempt in enumerate(entry.get("attempts") or []):
                aw = f"{where}.attempts[{i}]"
                if not _shape(aw, attempt, ATTEMPT, errors):
                    continue
                if attempt.get("id") in ids:
                    errors.append(f"{aw}: duplicate attempt id {attempt.get('id')!r}")
                ids.add(attempt.get("id"))
                status = attempt.get("status")
                if status not in STATUSES:
                    errors.append(f"{aw}: status must be one of {list(STATUSES)}, got {status!r}")
                if status == "running" and "pid" not in attempt:
                    errors.append(f"{aw}: a running attempt needs its pid")
                if attempt.get("verbatim") is not None and attempt["verbatim"] not in VERBATIM:
                    errors.append(f"{aw}: verbatim must be one of {list(VERBATIM)}")
                if "alpha" in attempt:
                    _shape(f"{aw}.alpha", attempt["alpha"], ALPHA, errors)
                if "retried" in attempt:
                    _shape(f"{aw}.retried", attempt["retried"], RETRIED, errors)
                if isinstance(attempt.get("detail"), dict):
                    for key in sorted(set(attempt["detail"]) - DETAIL_KEYS):
                        errors.append(f"{aw}.detail: unknown key '{key}'")
                name = attempt.get("file")
                if name:
                    if name in files:
                        errors.append(f"{aw}: file {name!r} already belongs to another attempt")
                    files.add(name)
            chosen = entry.get("chosen")
            if chosen is not None and chosen not in ok_attempts(entry):
                errors.append(f"{where}: chosen {chosen!r} is not an ok attempt of this version")

    for i, note in enumerate(job.get("notes") or []):
        if not _shape(f"notes[{i}]", note, NOTE, errors):
            continue
        if note.get("scope") not in SCOPES:
            errors.append(f"notes[{i}]: scope must be one of {list(SCOPES)}, got {note.get('scope')!r}")
        if "version" in note and note["version"] not in numbers:
            errors.append(f"notes[{i}]: version {note['version']!r} is not a version of this job")

    can = deliverables(job)
    finals = job.get("finals") if isinstance(job.get("finals"), list) else []
    for name in finals:
        if name not in can:
            errors.append(f"finals: {name!r} is not a rendered version or an ok attempt")
    if len(set(map(str, finals))) != len(finals):
        errors.append("finals: listed twice")
    for i, ex in enumerate(job.get("exports") or []):
        where = f"exports[{i}]"
        if not _shape(where, ex, EXPORT, errors):
            continue
        if ex.get("format") not in FORMATS:
            errors.append(f"{where}: format must be one of {list(FORMATS)}")
        if ex.get("of") not in can:
            errors.append(f"{where}: {ex.get('of')!r} is not a rendered version or an ok attempt")
        _size(where, ex.get("size"), errors)
    return errors
