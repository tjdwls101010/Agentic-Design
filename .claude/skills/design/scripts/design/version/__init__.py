"""Versions of the editable original: a snapshot of the document as it is now plus its render, as one ledger row; putting an earlier snapshot back; and delivering a version as a file checked against where it goes.

The document in work/ is the work; a version is a copy of it at a moment 성진 saw. Restoring never drops edits: when the document holds changes no version has (성진's in an app, or Claude's since the last version), they are versioned first. A PhotoCraft render updates linked content first, so a re-developed photo or a re-exported SVG shows; a linked file that is missing renders from the document's cache, so it is reported.

A LightCraft version is a photo's develop settings (sliders, curves, masks) in the job's library, not a file copy; its render is the photo developed with them.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path

from PIL import Image

from design import ledger, lightcraft, paths, photocraft, platforms, sheet, vectorcraft
from design.errors import Conflict, Failure, Usage

__all__ = ["snapshot", "restore", "export", "app_of", "pick_doc", "GRADE_LONG_EDGE"]

# A grade's render is for looking at on the sheet; the delivery is developed at full size by export.
GRADE_LONG_EDGE = 2400
STALE_STAGING_S = 6 * 3600
APP_BY_SUFFIX = {".pcraft": "photocraft", ".vectorcraft": "vectorcraft"}


def app_of(doc: Path) -> str:
    if doc.is_dir():
        return "lightcraft"
    try:
        return APP_BY_SUFFIX[doc.suffix]
    except KeyError:
        raise Usage(f"{doc.name}: a version is taken of a .pcraft, a .vectorcraft or a LightCraft library folder") from None


def _inside_work(job_dir: Path, doc: Path) -> None:
    try:
        doc.resolve().relative_to((job_dir / "work").resolve())
    except ValueError:
        raise Usage(f"{doc} is not inside this job's work/; the editable original lives there") from None


def pick_doc(job_dir: Path) -> Path:
    docs = [p for p in sorted((job_dir / "work").rglob("*")) if p.suffix in APP_BY_SUFFIX and p.is_file()]
    if len(docs) != 1:
        raise Failure("give --doc: " + ("work/ holds no document yet" if not docs else f"work/ holds {len(docs)} documents ({', '.join(paths.stored(job_dir, d) for d in docs)})"))
    return docs[0]


def _render(app: str, snap: Path, out: Path, *, photo_file: Path | None = None) -> list[str]:
    """Render a snapshot to `out`; returns warnings worth reading."""
    warnings = []
    if app == "photocraft":
        missing = [l for l in photocraft.links(photocraft.info(snap)) if not l["exists"]]
        warnings += [f"linked file missing, rendered from the document's cache: {l['path']} (layer {l['name']!r})" for l in missing]
        photocraft.render(snap, out)
    elif app == "vectorcraft":
        warnings += vectorcraft.render(snap, out)
    else:
        lightcraft.render(photo_file, out, settings_file=snap, long_edge=GRADE_LONG_EDGE)
    return warnings


def _copy_new(src: Path, dest: Path) -> None:
    paths.place_new(dest, lambda tmp: shutil.copy2(src, tmp))


def _record(job_dir: Path, fields: dict, write_snapshot, ext: str) -> tuple[dict, list[str]]:
    """Write the snapshot and its render in a private staging folder, then, under the ledger's lock, give them the next free version number and add the row. Numbering at the end means two commands versioning at once never share a number or a render, and a file left by a killed run is skipped rather than blocking the number."""
    versions = job_dir / "versions"
    for old in versions.glob(".staging-*"):  # left by a run that was killed; none lives this long
        if time.time() - old.stat().st_mtime > STALE_STAGING_S:
            shutil.rmtree(old, ignore_errors=True)
    stage = versions / f".staging-{uuid.uuid4().hex[:8]}"
    stage.mkdir(parents=True)
    render_ext = ".jpg" if fields["app"] == "lightcraft" else ".png"
    linked: list[Path] = []
    try:
        if fields.get("parent") is not None:
            ledger.version(ledger.read(job_dir), fields["parent"])
        snap_tmp, render_tmp = stage / f"snapshot{ext}", stage / f"render{render_ext}"
        write_snapshot(snap_tmp)
        warnings = _render(fields["app"], snap_tmp, render_tmp, photo_file=paths.from_stored(job_dir, fields["photo_file"]) if fields.get("photo_file") else None)
        with Image.open(render_tmp) as im:
            size = list(im.size)
        with ledger.edit(job_dir) as job:
            v = max((e["v"] for e in job["versions"]), default=0) + 1
            while any(versions.glob(f"v{v}.*")):
                v += 1
            snap, render = versions / f"v{v}{ext}", versions / f"v{v}{render_ext}"
            for src, dest in ((snap_tmp, snap), (render_tmp, render)):
                paths.link_new(src, dest)
                linked.append(dest)
            entry = ledger.add_version(job, {**fields, "snapshot": paths.stored(job_dir, snap), "render": paths.stored(job_dir, render), "size": size}, v=v)
        linked.clear()
        return entry, warnings
    finally:
        for dest in linked:  # the ledger refused the row: the files it would have named go too
            dest.unlink(missing_ok=True)
        shutil.rmtree(stage, ignore_errors=True)


def snapshot(job_dir: Path, *, kind: str, direction: str, change: str | None, parent: int | None, doc: Path | None, photo: int | None, photo_file: Path | None, from_app: bool = False) -> dict:
    """Version the document as it is. A document open in PhotoCraft or VectorCraft is versioned with from_app: the app saves it to its own path first, so the snapshot holds the app's state."""
    doc = doc or pick_doc(job_dir)
    if not doc.exists():
        raise Failure(f"{doc} does not exist; make the document first")
    _inside_work(job_dir, doc)
    app = app_of(doc)
    if (kind == "grade") != (app == "lightcraft"):
        raise Usage(f"--kind {kind} does not fit a {app} document: grade is a LightCraft library, composite/layout a .pcraft, vector a .vectorcraft")
    if app == "vectorcraft" and kind != "vector" or app == "photocraft" and kind not in ("composite", "layout"):
        raise Usage(f"--kind {kind} does not fit a {app} document")
    fields = {"kind": kind, "direction": direction, "app": app, "source": paths.stored(job_dir, doc)}
    if parent is not None:
        fields["parent"] = parent
    if change:
        fields["change"] = change
    saved = None
    pending_warning = None
    if from_app:
        if app == "lightcraft":
            raise Usage("--from-app is for PhotoCraft and VectorCraft documents; LightCraft saves its library as it goes")
        saved = {"photocraft": photocraft, "vectorcraft": vectorcraft}[app].app_save(doc)
        fields["from_app"] = True
    elif app != "lightcraft":
        held = {"photocraft": photocraft, "vectorcraft": vectorcraft}[app].app_holds(doc)
        if held:
            raise Conflict(f"{app} has {doc.name} open, so the file on disk may lack edits made in the app since its last save; version it with --from-app (the app saves to its own path first)")
        if held is None:
            pending_warning = f"{app} is running without a control port: if it has {doc.name} open, this snapshot may lack edits made there since its last save"
    if app == "lightcraft":
        if photo is None or photo_file is None:
            raise Usage("a LightCraft version needs --photo-id (the photo's id in the library) and --photo (its original file)")
        if not photo_file.is_file():
            raise Failure(f"{photo_file} does not exist")
        settings = lightcraft.settings(doc, photo)
        fields.update({"photo": photo, "photo_file": paths.stored(job_dir, photo_file)})
        entry, warnings = _record(job_dir, fields, lambda snap: paths.place_new(snap, lambda tmp: tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=1))), ".json")
    else:
        entry, warnings = _record(job_dir, fields, lambda snap: _copy_new(doc, snap), doc.suffix)
    out = _result(job_dir, entry, warnings + ([pending_warning] if pending_warning else []))
    if saved:
        out["saved_in_app"] = saved
    return out


def _result(job_dir: Path, entry: dict, warnings: list[str]) -> dict:
    large = paths.large_files(job_dir)
    warnings = list(warnings) + [f"{f['file']} is {f['mib']} MiB; GitHub refuses files over 100 MiB and the vault is pushed there (link photos instead of embedding them, keep developed photos 8-bit at the size needed)" for f in large]
    sheet_path = sheet.ensure_opened(job_dir)
    out = {"summary": f"v{entry['v']} {entry['kind']} {entry['size'][0]}x{entry['size'][1]}" + (f", {len(warnings)} warning(s)" if warnings else ""), "version": entry["v"], "snapshot": str(job_dir / entry["snapshot"]), "render": str(job_dir / entry["render"]), "sheet": str(sheet_path)}
    if warnings:
        out["warnings"] = warnings
    return out


def _replace(dest: Path, src: Path) -> None:
    """Overwrite the working document with a snapshot's bytes, atomically."""
    tmp = dest.with_name(f".{dest.stem}.{uuid.uuid4().hex[:8]}{dest.suffix}")
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)


def _held_by_app(app: str, doc: Path) -> str | None:
    """Why the document must not be written on disk now, or None: a running app that has it open saves over a disk edit, and one running without a control port cannot be asked."""
    system = {"photocraft": photocraft, "vectorcraft": vectorcraft, "lightcraft": lightcraft}[app]
    held = system.app_holds(doc)
    if held is True:
        return f"{app} has {doc.name} open: a change on disk would be overwritten by the app's next save. Make the change through the app (apps-send), or ask 성진 to save and close it"
    if held is None:
        return f"{app} is running without a control port, so whether it has {doc.name} open cannot be told; ask 성진 to save and close it, or reopen it with apps-open"
    return None


def restore(job_dir: Path, *, v: int) -> dict:
    """Make vN the current document again, as a new version."""
    job = ledger.read(job_dir)
    old = ledger.version(job, v)
    if old["kind"] not in ledger.DOC_KINDS:
        raise Failure(f"v{v} is a generated version; there is no document to restore (use its image as material instead)")
    doc = paths.from_stored(job_dir, old["source"])
    held = _held_by_app(old["app"], doc)
    if held:
        raise Conflict(held)
    saved = None
    latest = [e for e in job["versions"] if e.get("source") == old["source"] and (old["app"] != "lightcraft" or e.get("photo") == old.get("photo"))][-1]
    if old["app"] == "lightcraft":
        now = lightcraft.settings(doc, old["photo"])
        before = json.loads(paths.from_stored(job_dir, latest["snapshot"]).read_text())
        if now != before:
            saved = snapshot(job_dir, kind=old["kind"], direction=latest["direction"], change=f"edits no version had, kept before restoring v{v}", parent=latest["v"], doc=doc, photo=old["photo"], photo_file=paths.from_stored(job_dir, old["photo_file"]))
        lightcraft.restore_settings(doc, old["photo"], json.loads(paths.from_stored(job_dir, old["snapshot"]).read_text()))
        fields = {"kind": old["kind"], "direction": old["direction"], "app": "lightcraft", "source": old["source"], "parent": v, "restored_from": v, "change": f"restored v{v}", "photo": old["photo"], "photo_file": old["photo_file"]}
        entry, warnings = _record(job_dir, fields, lambda snap: _copy_new(paths.from_stored(job_dir, old["snapshot"]), snap), ".json")
    else:
        if doc.exists() and doc.read_bytes() != paths.from_stored(job_dir, latest["snapshot"]).read_bytes():
            saved = snapshot(job_dir, kind=latest["kind"], direction=latest["direction"], change=f"edits no version had, kept before restoring v{v}", parent=latest["v"], doc=doc, photo=None, photo_file=None)
        _replace(doc, paths.from_stored(job_dir, old["snapshot"]))
        fields = {"kind": old["kind"], "direction": old["direction"], "app": old["app"], "source": old["source"], "parent": v, "restored_from": v, "change": f"restored v{v}"}
        entry, warnings = _record(job_dir, fields, lambda snap: _copy_new(doc, snap), doc.suffix)
    out = _result(job_dir, entry, warnings)
    if saved:
        out["kept_first"] = {"version": saved["version"], "why": "the document held edits no version had; they are in this version"}
    return out


def _aspect_ok(a: tuple[int, int] | list[int], b: tuple[int, int] | list[int]) -> bool:
    return abs((a[0] / a[1]) / (b[0] / b[1]) - 1) <= platforms.ASPECT_TOLERANCE


def export(job_dir: Path, *, name: str, target: str | None, size: list[int] | None, fmt: str, to: Path | None) -> dict:
    """Write version `name` (vN, or an attempt vN-k) as a delivery file, rendered from its snapshot at the delivery size, and check it against the target platform."""
    job = ledger.read(job_dir)
    v, k = ledger.parse_name(name)
    entry = ledger.version(job, v)
    platform = platforms.get(target) if target else None
    folder = to or job_dir / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    ext = {"png": ".png", "jpg": ".jpg", "pdf": ".pdf"}[fmt]
    dest = folder / f"{job['id']}_{name}{'_' + target if target else ''}{ext}"
    if dest.exists():
        raise Failure(f"{dest} already exists; exports never overwrite (give --to another folder, or remove it)")
    native = list(entry["size"]) if entry.get("size") else None
    if k is not None:
        if name not in ledger.ok_attempts(entry):
            raise Failure(f"{name} is not an ok attempt of v{v}")
        with Image.open(job_dir / "versions" / f"{name}.png") as im:
            native = list(im.size)
    elif entry["kind"] not in ledger.DOC_KINDS:
        raise Failure(f"v{v} is a generated version; export one of its attempts (v{v}-k)")
    want = size or (list(platform.size) if platform else native)
    if fmt == "pdf" and entry.get("app") != "vectorcraft":
        raise Usage("pdf export is for VectorCraft documents (print and vector deliveries); export png or jpg otherwise")
    if fmt == "pdf" and size:
        raise Usage("a pdf is written at the artboard's own size; --size is for png and jpg")
    if native and want and not _aspect_ok(want, native) and fmt != "pdf":
        raise Usage(f"{name} is {native[0]}x{native[1]} and the delivery is {want[0]}x{want[1]}: a different aspect. Export does not crop; make the document in the delivery's aspect (or give --size in its own aspect)")
    tmp = dest.with_name(f".{dest.stem}.{uuid.uuid4().hex[:8]}{'.png' if fmt == 'jpg' else ext}")
    warnings: list[str] = []
    try:
        if k is not None:
            with Image.open(job_dir / "versions" / f"{name}.png") as im:
                im.resize(tuple(want), Image.LANCZOS).save(tmp)
        elif entry["app"] == "photocraft":
            snap = paths.from_stored(job_dir, entry["snapshot"])
            warnings += [f"linked file missing, rendered from the document's cache: {l['path']}" for l in photocraft.links(photocraft.info(snap)) if not l["exists"]]
            photocraft.render(snap, tmp, size=tuple(want) if want != native else None)
        elif entry["app"] == "vectorcraft":
            snap = paths.from_stored(job_dir, entry["snapshot"])
            boards = vectorcraft.info(snap).get("artboards") or []
            if not boards:
                raise Failure(f"{snap.name} has no artboard to export")
            board = boards[0]["rect"]
            warnings += vectorcraft.render(snap, tmp, scale=1 if fmt == "pdf" else want[0] / (board[2] - board[0]))
        else:
            lightcraft.render(paths.from_stored(job_dir, entry["photo_file"]), tmp, settings_file=paths.from_stored(job_dir, entry["snapshot"]), long_edge=max(want) if size or platform else 0)
        if fmt == "jpg":
            with Image.open(tmp) as im:
                flat = Image.new("RGB", im.size, (255, 255, 255))
                rgba = im.convert("RGBA")
                flat.paste(rgba, mask=rgba.getchannel("A"))
                jpg = tmp.with_suffix(".jpg")
                flat.save(jpg, quality=95, subsampling=0)
            tmp.unlink()
            tmp = jpg
        paths.place_new(dest, lambda t: shutil.copyfile(tmp, t))
    finally:
        tmp.unlink(missing_ok=True)
    if fmt == "pdf":
        board = vectorcraft.info(paths.from_stored(job_dir, entry["snapshot"]))["artboards"][0]["rect"]
        final_size = [round(board[2] - board[0]), round(board[3] - board[1])]  # points
    else:
        with Image.open(dest) as im:
            final_size = list(im.size)
    nbytes = dest.stat().st_size
    violations, soft = platforms.violations(platform, final_size[0], final_size[1], nbytes, fmt) if platform and fmt != "pdf" else ([], [])
    warnings += soft
    row = {"path": str(dest), "of": name, "format": fmt, "at": ledger.now(), "size": final_size, "bytes": nbytes}
    if target:
        row["target"] = target
    if violations:
        row["violations"] = violations
    if warnings:
        row["warnings"] = warnings
    with ledger.edit(job_dir) as job:
        job["exports"].append(row)
    sheet.rebuild(job_dir)
    out = {"summary": f"{dest.name} {final_size[0]}x{final_size[1]} {nbytes / 1024 / 1024:.1f} MB" + (f", {len(violations)} violation(s)" if violations else "") + (f", {len(warnings)} warning(s)" if warnings else ""), **row}
    if platform:
        out["platform_notes"] = list(platform.notes)
    return out
