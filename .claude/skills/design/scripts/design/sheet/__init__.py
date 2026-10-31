"""The contact sheet: one fixed-layout HTML page per job, rebuilt from the ledger after every write.

The layout is fixed so every job reads the same way: targets pinned at the top, the brief, then each version as a row — a document version's render, or a generated version's attempts — with its critique and 성진's notes, and its prompt, references and failures folded away. Clicking an image enlarges it; ← and → step through every image on the sheet in order, Esc closes. The page cannot fetch job.json over file://, so every rebuild also writes `.sheet-stamp.js`; an open tab loads that script every two seconds and reloads itself when the stamp changes, keeping its scroll position and waiting while an image is enlarged. Images are linked by relative path, never inlined.
"""

from __future__ import annotations

import fcntl
import hashlib
import html
import os
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import quote

from design import ledger, paths

__all__ = ["SHEET", "STAMP", "render", "rebuild", "ensure_opened"]

SHEET = "contact-sheet.html"
STAMP = ".sheet-stamp.js"

CSS = """
:root { color-scheme: light dark; --bg:#f7f6f3; --fg:#1d1b18; --muted:#6f685f; --line:#dedad3; --card:#fff; --accent:#a24a1c; --ok:#2e6b42; --warn:#986a10; --bad:#a1322b; }
@media (prefers-color-scheme: dark) { :root { --bg:#151412; --fg:#ebe7e1; --muted:#9c958b; --line:#33302b; --card:#1f1d1a; --accent:#e58a51; --ok:#80c49a; --warn:#d9ae5d; --bad:#e07d73; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }
.top { position:sticky; top:0; z-index:5; background:color-mix(in srgb, var(--bg) 94%, transparent); backdrop-filter:blur(6px); border-bottom:1px solid var(--line); padding:.6rem 1.25rem; }
.top h1 { font-size:1.1rem; margin:0; }
.top .req { color:var(--muted); font-size:.85rem; max-width:80rem; }
.targets { display:flex; gap:.5rem; margin-top:.4rem; overflow-x:auto; }
.targets img { height:120px; width:auto; border:1px solid var(--line); border-radius:6px; cursor:zoom-in; background:var(--card); }
.targets .label { font-size:.75rem; color:var(--muted); writing-mode:vertical-rl; }
main { max-width:96rem; margin:0 auto; padding:1rem 1.25rem 5rem; }
.brief { display:flex; flex-wrap:wrap; gap:.3rem .8rem; font-size:.85rem; color:var(--muted); margin-bottom:.4rem; }
.notes { font-size:.85rem; margin:.4rem 0 1rem; padding-left:1.1rem; }
.notes .scope { font-size:.7rem; border-radius:4px; padding:0 .3rem; background:var(--line); margin-right:.3rem; }
.path { font-family:ui-monospace, Menlo, monospace; font-size:.72rem; color:var(--muted); word-break:break-all; }
.version { border-top:1px solid var(--line); padding:1.2rem 0; }
.vhead { display:flex; flex-wrap:wrap; gap:.3rem .8rem; align-items:baseline; margin-bottom:.6rem; }
.vnum { font-weight:700; font-size:1.05rem; } .vdir { color:var(--accent); font-weight:600; } .vmeta { color:var(--muted); font-size:.82rem; }
.row { display:grid; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); gap:.8rem; }
figure { margin:0; background:var(--card); border:1px solid var(--line); border-radius:8px; overflow:hidden; }
figure.chosen { border-color:var(--accent); box-shadow:0 0 0 2px color-mix(in srgb, var(--accent) 40%, transparent); }
figure.final { border-color:var(--ok); box-shadow:0 0 0 3px color-mix(in srgb, var(--ok) 45%, transparent); }
figure img { display:block; width:100%; height:auto; cursor:zoom-in; background:repeating-conic-gradient(#ccc 0 25%, #fff 0 50%) 0 0/16px 16px; }
figure.pending { display:flex; align-items:center; justify-content:center; min-height:180px; color:var(--muted); font-size:.85rem; border-style:dashed; }
figcaption { padding:.4rem .55rem; font-size:.74rem; color:var(--muted); display:flex; flex-wrap:wrap; gap:.25rem .45rem; align-items:center; }
.tag { border-radius:4px; padding:0 .3rem; background:var(--line); color:var(--fg); }
.tag.ok { background:color-mix(in srgb, var(--ok) 22%, transparent); color:var(--ok); }
.tag.warn { background:color-mix(in srgb, var(--warn) 22%, transparent); color:var(--warn); }
.tag.bad { background:color-mix(in srgb, var(--bad) 22%, transparent); color:var(--bad); }
.crit { margin-top:.7rem; padding:.6rem .8rem; border-left:3px solid var(--accent); background:var(--card); border-radius:0 6px 6px 0; white-space:pre-wrap; }
details { margin-top:.5rem; } summary { cursor:pointer; color:var(--muted); font-size:.82rem; }
pre { white-space:pre-wrap; word-break:break-word; background:var(--card); border:1px solid var(--line); border-radius:6px; padding:.6rem .7rem; font-size:.8rem; }
.refs { grid-template-columns:repeat(auto-fill, minmax(130px, 170px)); margin-top:.4rem; }
table { border-collapse:collapse; font-size:.78rem; margin-top:.4rem; } td, th { border-bottom:1px solid var(--line); padding:.2rem .5rem; text-align:left; vertical-align:top; }
.fails li { font-size:.8rem; color:var(--muted); margin:.2rem 0; }
.final-box { margin-top:1.5rem; padding:.9rem 1rem; border:2px solid var(--ok); border-radius:10px; }
.swatch { display:inline-block; width:.9em; height:.9em; border-radius:2px; vertical-align:-.1em; border:1px solid var(--line); }
dialog { border:none; padding:0; background:transparent; max-width:98vw; max-height:98vh; }
dialog::backdrop { background:rgba(0,0,0,.85); }
dialog img { max-width:98vw; max-height:92vh; cursor:zoom-out; display:block; margin:0 auto; }
dialog .cap { color:#eee; font:13px/1.4 ui-monospace, Menlo, monospace; text-align:center; padding:.4rem; }
dialog .nav { position:fixed; top:50%; transform:translateY(-50%); background:rgba(0,0,0,.4); color:#fff; border:none; font-size:2rem; padding:.4rem .8rem; cursor:pointer; border-radius:6px; }
dialog .prev { left:1vw; } dialog .next { right:1vw; }
"""

JS = """
const STAMP = "%(stamp)s", KEY = "design-sheet:" + location.pathname;
const dlg = document.getElementById("zoom"), big = dlg.querySelector("img"), cap = dlg.querySelector(".cap");
const shots = Array.from(document.querySelectorAll("img[data-zoom]"));
let at = -1;
function show(i) { at = (i + shots.length) %% shots.length; big.src = shots[at].src; cap.textContent = (shots[at].dataset.name || shots[at].alt) + "  (" + (at + 1) + "/" + shots.length + ")"; }
shots.forEach((img, i) => img.addEventListener("click", () => { show(i); dlg.showModal(); }));
big.addEventListener("click", () => dlg.close());
dlg.querySelector(".prev").addEventListener("click", e => { e.stopPropagation(); show(at - 1); });
dlg.querySelector(".next").addEventListener("click", e => { e.stopPropagation(); show(at + 1); });
document.addEventListener("keydown", e => {
  if (!dlg.open) return;
  if (e.key === "ArrowRight") { e.preventDefault(); show(at + 1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); show(at - 1); }
});
function remember() { try { localStorage.setItem(KEY, String(window.scrollY)); } catch (e) {} }
function restore() { try { const y = localStorage.getItem(KEY); if (y !== null) window.scrollTo(0, Number(y)); } catch (e) {} }
restore(); window.addEventListener("load", restore);
window.addEventListener("scroll", () => { clearTimeout(window.__t); window.__t = setTimeout(remember, 150); });
window.addEventListener("beforeunload", remember);
let pending = false;
function poll() {
  const s = document.createElement("script");
  s.src = "%(stamp_file)s?" + Date.now();
  s.onload = () => { s.remove(); if (window.__sheetStamp && window.__sheetStamp !== STAMP) pending = true; maybeReload(); };
  s.onerror = () => s.remove();
  document.head.appendChild(s);
}
function maybeReload() { if (pending && !dlg.open) { remember(); location.reload(); } }
dlg.addEventListener("close", maybeReload);
setInterval(poll, 2000);
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _src(job_dir: Path, stored: str) -> str:
    return _e(quote(os.path.relpath(paths.from_stored(job_dir, stored), job_dir)))


def _img(job_dir: Path, stored: str, name: str, size: list | None = None, zoom: bool = True) -> str:
    # Known pixel size reserves the image's space before it loads, so a restored scroll position lands where it was.
    dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
    return f'<img src="{_src(job_dir, stored)}" alt="{_e(name)}" data-name="{_e(name)}"{dims} loading="lazy"{" data-zoom" if zoom else ""}>'


def _attempt(job_dir: Path, entry: dict, attempt: dict, finals: list[str]) -> str:
    name = attempt["id"]
    classes = []
    if name == entry.get("chosen"):
        classes.append("chosen")
    if name in finals:
        classes.append("final")
    tags = [f'<span class="path">{_e(name)}</span>']
    if name in finals:
        tags.append('<span class="tag ok">최종</span>')
    elif name == entry.get("chosen"):
        tags.append('<span class="tag ok">선택</span>')
    if attempt.get("w"):
        tags.append(f'<span class="tag">{attempt["w"]}×{attempt["h"]}</span>')
    if attempt.get("aspect_ok") is False:
        tags.append(f'<span class="tag bad">비율 {attempt["w"] / attempt["h"]:.3f} (요청 {_e(entry.get("aspect"))})</span>')
    if attempt["status"] != "ok":
        tags.append(f'<span class="tag bad">{_e(attempt["status"])} · 고를 수 없음</span>')
    verbatim = attempt.get("verbatim")
    if verbatim and verbatim != "exact":
        tags.append(f'<span class="tag warn">verbatim {_e(verbatim)}</span>')
    alpha = attempt.get("alpha")
    if alpha:
        tags.append(f'<span class="tag ok">투명 {alpha.get("transparent_share", 0):.0%}</span>' if alpha.get("has_alpha") else '<span class="tag bad">알파 없음</span>')
    size = [attempt["w"], attempt["h"]] if attempt.get("w") and attempt.get("h") else None
    return f'<figure class="{" ".join(classes)}">{_img(job_dir, "versions/" + attempt["file"], name, size)}<figcaption>{"".join(tags)}</figcaption></figure>'


def _render(job_dir: Path, entry: dict, finals: list[str]) -> str:
    name = f"v{entry['v']}"
    final = name in finals
    tags = [f'<span class="path">{_e(Path(entry["render"]).name)}</span>']
    if final:
        tags.append('<span class="tag ok">최종</span>')
    tags.append(f'<span class="tag">{_e(entry["app"])}</span>')
    if entry.get("size"):
        tags.append(f'<span class="tag">{entry["size"][0]}×{entry["size"][1]}</span>')
    if entry.get("from_app"):
        tags.append('<span class="tag warn">앱에서 저장</span>')
    if entry.get("restored_from"):
        tags.append(f'<span class="tag">v{entry["restored_from"]} 되살림</span>')
    tags.append(f'<a class="path" href="{_src(job_dir, entry["snapshot"])}">{_e(Path(entry["snapshot"]).name)}</a>')
    return f'<figure class="{"final" if final else ""}">{_img(job_dir, entry["render"], name, entry.get("size"))}<figcaption>{"".join(tags)}</figcaption></figure>'


def _note(n: dict) -> str:
    return f'<li><span class="scope">{"재사용" if n["scope"] == "reusable" else "이번 작업"}</span>{_e(n["text"])}</li>'


def _version(job_dir: Path, job: dict, entry: dict) -> str:
    meta = [entry["kind"]]
    if entry.get("parent") is not None:
        meta.append(f"v{entry['parent']}에서")
    if entry.get("change"):
        meta.append(entry["change"])
    parts = [f'<section class="version" id="v{entry["v"]}">']
    figures = []
    failed = []
    if entry["kind"] in ledger.DOC_KINDS:
        figures.append(_render(job_dir, entry, job["finals"]))
    else:
        attempts = entry["attempts"]
        running = [a for a in attempts if a["status"] == "running"]
        shown = [a for a in attempts if a.get("file") and a["status"] in ("ok", "prompt_altered", "path_mismatch")]
        failed = [a for a in attempts if a["status"] not in ("ok", "running") and a not in shown]
        oks = sum(1 for a in attempts if a["status"] == "ok")
        meta.append(f"성공 {oks}/{len(attempts) - len(running)}" + (f" · 생성 중 {len(running)}" if running else ""))
        figures += [_attempt(job_dir, entry, a, job["finals"]) for a in shown]
        figures += [f'<figure class="pending">{_e(a["id"])} 생성 중…</figure>' for a in running]
    parts.append(f'<div class="vhead"><span class="vnum">v{entry["v"]}</span><span class="vdir">{_e(entry["direction"])}</span><span class="vmeta">{_e(" · ".join(meta))}</span></div>')
    if figures:
        parts.append(f'<div class="row">{"".join(figures)}</div>')
    if entry.get("critique"):
        parts.append(f'<div class="crit">{_e(entry["critique"])}</div>')
    said = [n for n in job["notes"] if n.get("version") == entry["v"]]
    if said:
        parts.append(f'<ul class="notes">{"".join(_note(n) for n in said)}</ul>')
    if entry.get("prompt"):
        parts.append(f'<details><summary>프롬프트 ({len(entry["prompt"])}자)</summary><pre>{_e(entry["prompt"])}</pre></details>')
    if entry.get("refs"):
        thumbs = "".join(f'<figure>{_img(job_dir, r, Path(r).name, zoom=False)}<figcaption><span class="path">{_e(r)}</span></figcaption></figure>' for r in entry["refs"])
        parts.append(f'<details><summary>참조 {len(entry["refs"])}장</summary><div class="row refs">{thumbs}</div></details>')
    if failed:
        items = []
        for a in failed:
            d = a.get("detail") or {}
            facts = [str(x) for x in (d.get("code"), f"stage={d['moderation_stage']}" if d.get("moderation_stage") else None, ",".join(d.get("categories") or []) or None, d.get("message")) if x]
            items.append(f'<li><span class="tag bad">{_e(a["status"])}</span> {_e(a["id"])} {_e(" · ".join(facts))}</li>')
        parts.append(f'<details><summary>실패 {len(failed)}건</summary><ul class="fails">{"".join(items)}</ul></details>')
    parts.append("</section>")
    return "".join(parts)


def render(job: dict, job_dir: Path, stamp: str) -> str:
    brief = job["brief"]
    head = [f'<header class="top"><h1>{_e(job["id"])}</h1><div class="req">{_e(brief["request"])}</div>']
    if brief.get("targets"):
        thumbs = "".join(f'<img src="{_src(job_dir, t)}" alt="목표" title="{_e(t)}">' for t in brief["targets"])
        head.append(f'<div class="targets"><span class="label">목표</span>{thumbs}</div>')
    head.append("</header>")
    info = []
    if brief.get("size"):
        info.append(f'<span class="tag">{brief["size"][0]}×{brief["size"][1]}</span>')
    if brief.get("aspect"):
        info.append(f'<span class="tag">{_e(brief["aspect"])}</span>')
    if brief.get("platform"):
        info.append(f'<span class="tag">{_e(brief["platform"])}</span>')
    if brief.get("purpose"):
        info.append(f"용도: {_e(brief['purpose'])}")
    info += [f'<span class="tag">“{_e(t)}”</span>' for t in brief.get("text") or []]
    info += [f'<span class="tag warn">비울 자리: {_e(t)}</span>' for t in brief.get("reserved") or []]
    body = [f'<div class="brief">{"".join(info)}</div>']
    general = [n for n in job["notes"] if "version" not in n]
    if general:
        body.append(f'<ul class="notes">{"".join(_note(n) for n in general)}</ul>')
    body.append(f'<div class="path">{_e(job_dir)}/</div>')
    body += [_version(job_dir, job, v) for v in job["versions"]]
    if job["finals"] or job["exports"]:
        finals = " · ".join(f'<a class="path" href="#{_e(f.split("-")[0])}">{_e(f)}</a>' for f in job["finals"]) or "없음"
        exports = "".join(f'<li class="path">{_e(x["path"])} · {_e(x["format"])} · {x["size"][0]}×{x["size"][1]}{" · " + _e(x["target"]) if x.get("target") else ""} ← {_e(x["of"])}</li>' for x in job["exports"])
        body.append(f'<div class="final-box"><strong>최종</strong> {finals}{f"<ul>{exports}</ul>" if exports else ""}</div>')
    script = JS % {"stamp": stamp, "stamp_file": STAMP}
    return ("<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{_e(job['id'])}</title><style>{CSS}</style></head><body>{''.join(head)}<main>{''.join(body)}</main>"
            f'<dialog id="zoom"><button class="nav prev" aria-label="이전">‹</button><img alt=""><div class="cap"></div><button class="nav next" aria-label="다음">›</button></dialog><script>{script}</script></body></html>')


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def rebuild(job_dir: Path, open_it: bool = False) -> Path:
    out = job_dir / SHEET
    # Reading the ledger and publishing the page happen under one lock, so a rebuild that read an older ledger can never land after a newer one.
    with open(job_dir / ".sheet.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        job = ledger.read(job_dir)
        stamp = hashlib.sha1(render(job, job_dir, "").encode()).hexdigest()[:12]
        _atomic(out, render(job, job_dir, stamp))
        _atomic(job_dir / STAMP, f'window.__sheetStamp = "{stamp}";\n')
    if open_it:
        _open(out)
    return out


def ensure_opened(job_dir: Path) -> Path:
    """Open the sheet the first time anything is produced for this job, and remember that it was opened."""
    with ledger.edit(job_dir) as job:
        first = "sheet_opened" not in job
        if first:
            job["sheet_opened"] = ledger.now()
    return rebuild(job_dir, open_it=first)


def _open(path: Path) -> None:
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.run([opener, str(path)], check=False, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"could not open the sheet ({exc}); open {path} yourself", file=sys.stderr)
