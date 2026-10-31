# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pillow>=11",
#     "numpy>=2",
#     "fonttools>=4.50",
#     "brotli>=1.1",
#     "pyobjc-framework-Vision>=11; sys_platform == 'darwin'",
#     "pyobjc-framework-Quartz>=11; sys_platform == 'darwin'",
# ]
# ///
"""design: make promotional images with 성진 as ArtCraft documents (PhotoCraft .pcraft, VectorCraft .vectorcraft, LightCraft libraries) he can open and finish by hand — keeping every version of a job in one ledger and on one live contact sheet, generating material with Codex gpt-image, cutting people out with macOS Vision, checking fonts, strings and platform specs, and finding fonts on noonnu."""

from __future__ import annotations

import argparse
import json
import re
import sys

from design import fonts, generate, ledger, paths, platforms, sheet
from design import job as jobs
from design.errors import Failure, Usage

TOP_EPILOG = """\
<job> is a short name under data/ (a new one must read <kind>_<YYMMDD>_<title>) or a path (/, ~, .).
Every command prints one JSON document on stdout, progress on stderr.
exit: 0 success · 1 ran but produced no result · 2 bad arguments · 3 environment cannot run (an ArtCraft CLI or app, codex, macOS Vision, the network) · 4 an input file cannot be read · 5 going on would lose 성진's work (the document is open in an app, or holds changes no version has)
Environment: DESIGN_DATA overrides data/; DESIGN_FONTS_DIR overrides ~/Library/Fonts.
Run `<command> --help` for each command's arguments, output and failures."""

COMMANDS = {
    "new": "Start a job: <kind>_<YYMMDD>_<title> folder, ledger with the brief, contact sheet",
    "show": "Summarise one job, or every job's finals and reusable notes and the references (--all)",
    "add": "Record a gpt-image version's prompt (stdin) before generating it",
    "generate": "Generate recorded gpt-image versions through Codex image_gen",
    "record": "Write 성진's notes, Claude's critique, the chosen attempt and the finals",
    "sheet": "Rebuild or open the contact sheet",
    "fonts-search": "Find Korean fonts on noonnu (눈누) by name, use and style",
    "fonts-info": "One noonnu font: license per use, styles, webfont files, download page",
    "fonts-install": "Install a noonnu font (OFL only) or font files and zips into the fonts folder",
}


class Parser(argparse.ArgumentParser):
    """Argument errors go to stdout as JSON with exit 2, so the caller reads them the way it reads every other result."""

    def error(self, message: str):
        emit({"error": message, "help": f"{self.format_usage().strip()}  (run with --help for details)"})
        sys.exit(2)


def formatter(prog: str) -> argparse.HelpFormatter:
    # Wide enough that no help line is folded: each argument stays one line for grep.
    return argparse.RawDescriptionHelpFormatter(prog, width=1000, max_help_position=40)


def emit(doc: dict) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    # Arrays of plain numbers (boxes, sizes, points) on one line each.
    print(re.sub(r"\[\s*(-?[\d.]+(?:,\s*-?[\d.]+)*)\s*\]", lambda m: "[" + ", ".join(v.strip() for v in m[1].split(",")) + "]", text))


# ---- argument types --------------------------------------------------------------------------

def aspect_type(raw: str) -> str:
    if not re.fullmatch(r"[1-9]\d{0,2}:[1-9]\d{0,2}", raw):
        raise argparse.ArgumentTypeError(f"expected W:H such as 4:5, got {raw!r}")
    return raw


def aspect_or_none(raw: str) -> str:
    return raw if raw == "none" else aspect_type(raw)


def size_type(raw: str) -> list[int]:
    m = re.fullmatch(r"(\d{1,5})x(\d{1,5})", raw)
    if not m or not int(m[1]) or not int(m[2]):
        raise argparse.ArgumentTypeError(f"expected WxH in pixels such as 1080x1350, got {raw!r}")
    return [int(m[1]), int(m[2])]


def job_type(raw: str):
    """An existing job: a short name under data/ or a path to a folder holding job.json."""
    try:
        path = paths.resolve_job(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not paths.is_job(path):
        raise argparse.ArgumentTypeError(f"no job at {path} (no job.json); start one with new")
    return path


def existing_file(raw: str):
    path = paths.resolve_input(raw)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"no such file: {raw}")
    return path


# ---- parser ----------------------------------------------------------------------------------

def build_parser() -> Parser:
    commands = "\n".join(f"  {name:<14} {summary}" for name, summary in COMMANDS.items())
    ap = Parser(prog="cli.py", usage="cli.py <command> [options]", description=f"{__doc__}\n\ncommands:\n{commands}", epilog=TOP_EPILOG, formatter_class=formatter)
    sub = ap.add_subparsers(dest="command", metavar="<command>", parser_class=Parser, help=argparse.SUPPRESS)

    def command(name: str, epilog: str, details: str | None = None) -> Parser:
        summary = COMMANDS[name] + "."
        return sub.add_parser(name, prog=f"cli.py {name}", description=f"{summary}\n\n{details}" if details else summary, epilog=epilog, formatter_class=formatter)

    p = command("new", """\
output: {"job": <folder>, "sheet": <contact-sheet.html>, "brief": the brief as stored, "sources": [names copied], "next"}
The contact sheet opens in the browser (--no-open to skip).

failures: exit 2 if the name would not read <kind>_<YYMMDD>_<title>, the folder already exists (it is never touched), a file is missing, two files share a name, or there is no request.""", details="""\
The job is data/<kind>_<today as YYMMDD>_<title>, with sources/ (what was handed over, never edited), assets/ (mattes, cut-outs, generated images, developed photos, textures, chart SVGs), work/ (the current editable documents), versions/ (snapshots and renders of every version), proof/ (disposable check sheets), exports/ (deliveries) and etc/ (logs). --source and --target files are copied in byte for byte (an APFS clone where possible).
The brief holds what the work answers to and cannot be seen in an image: the request in the asker's words, the purpose and where it is posted, the size, strings that must appear exactly, areas to keep clear. --platform fills the size from that platform's default when --size is not given; the aspect follows from the size.""")
    p.add_argument("kind", help="the kind of work as the folder names say it, e.g. 썸네일, 웹포스터, 카드뉴스, 로고, 보정")
    p.add_argument("title", help="a short title, e.g. 국정감사 제보")
    p.add_argument("--request", required=True, help="what was asked for, in the asker's words")
    p.add_argument("--purpose", help="where it will be used and posted, and what happens to it afterwards")
    p.add_argument("--platform", choices=sorted(platforms.PLATFORMS), help="where the delivery goes; sets the default size and what export checks")
    p.add_argument("--size", type=size_type, metavar="WxH", help="delivery size in pixels, e.g. 1920x1080")
    p.add_argument("--aspect", type=aspect_type, metavar="W:H", help="the aspect when there is no fixed pixel size")
    p.add_argument("--text", action="append", default=[], metavar="S", help="a string that must appear exactly; repeatable")
    p.add_argument("--reserved", action="append", default=[], metavar="AREA", help="an area to keep clear, in words (e.g. 'top-left 20%% for the party logo'); repeatable")
    p.add_argument("--source", action="append", default=[], type=existing_file, metavar="FILE", help="a photo, logo or other material handed over, copied into sources/; repeatable")
    p.add_argument("--target", action="append", default=[], type=existing_file, metavar="IMG", help="an image the result is judged against (a reference), copied into sources/ and shown at the top of the sheet; repeatable")
    p.add_argument("--no-open", action="store_true", help="do not open the contact sheet")

    p = command("show", """\
output (one job): {"summary", "brief", "notes": ["[scope] text (vN)"], "versions": [{"v", "kind", "direction", "parent"?, "change"?, "render"?, "snapshot"?, "ok"?, "failed"?, "chosen"?, "critique_first_line"?}], "finals", "exports", "sheet", "unversioned"?: [{"file", "state": never versioned | changed since vN}], "large_files"?: [{"file", "mib"}]}
output (--all): {"summary", "jobs": [{"job", "kind", "date", "request", "versions", "finals": [paths], "reusable_notes"}], "earlier": [jobs the earlier skill left: {"job", "schema", "kind", "date", "finals", "reusable_notes"}], "references": {"folder", "by_folder": {folder: [files]}}}
unversioned lists documents in work/ that hold edits no version has (성진's in an app, or Claude's since the last version). large_files lists files of 90 MiB or more anywhere in the job: the vault is pushed to GitHub, which refuses files over 100 MiB.

failures: exit 2 if the job does not exist, or neither a job nor --all is given.""")
    p.add_argument("job", nargs="?", type=job_type, help="short name under data/ or a path")
    p.add_argument("--all", action="store_true", help="every job in data/ (the earlier skill's included, read only) and data/_references/")

    p = command("add", """\
output: {"version": N, "warnings"?: [...]}
warnings flags an aspect ratio missing from, or different in, the prompt's first sentence (not checked for --aspect none); the version is recorded either way.

The prompt lives only in job.json; generate reads it from there. --kind edit regenerates the whole image with the --ref images attached; it is not inpainting and keeps no pixels.

failures: exit 2 if stdin is empty or a terminal, --kind edit has no --ref, the job does not exist, or an argument is malformed; exit 1 if a --ref file is missing, --parent names no version, or neither --aspect nor the brief gives an aspect.""", details="""\
How the model behind codex's image_gen reads a prompt: tendencies observed on this path, not laws; when a result disagrees, trust the result.
  - Write the prompt as English prose.
  - State the aspect ratio as its own sentence at the start ("Portrait 4:5 aspect ratio, taller than it is wide."); the ratio is set only by the prompt, and pixel sizes add nothing. add warns when the first sentence does not state this version's aspect.
  - Whatever is named first takes more of the frame and the first look, so name the subject first.
  - Listing several media keeps only some of them; to mix, name one medium and give it another's quality ("an oil painting with the flatness of a screenprint").
  - Anything not supplied gets invented (organisation names, domains, dates, places, numbers, slogans), differently in every image: give every string the image must show, Korean included, inside double quotes exactly as it must read, and close with "no other text"; for a source, quotation or figure, give the wording or only reserve its place.
  - Asked for unreadable marks, it writes readable-looking fake Hangul; a surface that must carry no text has to be called blank.
  - Short Hangul strings come out mostly right; lettering whose strokes turn into objects breaks the letters.
  - A flat ground given as a hex colour comes out close to it; colour names and comparisons drift further.
  - A shape with one right answer (a flag's trigrams, a symbol) comes out right when its structure is described, not its name and count.
  - For material to composite (a prop, a texture, a background), describe the scene's light direction and colour so it sits in the photo, and ask for a transparent background (--transparent) or a flat ground that separates cleanly.""")
    p.add_argument("job", type=job_type, help="short name under data/ or a path")
    p.add_argument("--direction", required=True, metavar="NAME", help="short memorable name of the direction this version belongs to")
    p.add_argument("--kind", required=True, choices=list(ledger.GEN_KINDS), help="generate: from the prompt alone (refs optional, as style or content references); edit: rework the --ref image(s), at least one required; the prompt names the one change and lists everything that must stay, since \"keep everything else the same\" alone does not hold it")
    p.add_argument("--ref", action="append", default=[], metavar="IMG", help="image passed to the model with the prompt; repeatable. The model carries over a reference's palette, lettering and layout, down to its date format, even when told to use it for style only; with --kind edit keeping the composition is the point")
    p.add_argument("--aspect", type=aspect_or_none, help="W:H the result is checked against (default: the brief's aspect); none for an element whose shape does not matter")
    p.add_argument("--transparent", action="store_true", help="ask image_gen for a transparent background; generate reports whether the PNG really has alpha")
    p.add_argument("--parent", type=int, metavar="N", help="the version this one revises")
    p.add_argument("--change", metavar="T", help="what changes against the parent and why")

    p = command("generate", """\
output: {"summary": "...", "results": [{"version", "attempt", "file"?, "status", "w"?, "h"?, "aspect_ok"?, "alpha"?, "verbatim"?, "error"?}], "sheet": <path>}
Each finished variant also prints one line on stderr as it lands, with the failure kind, codex's reason and what to do next.

Every version is asked for --n images. All requests are queued and at most 6 run at once; one call takes roughly 40-180 seconds. Each try becomes an attempt row and a new file versions/v{N}-{k}.png, where k keeps counting across runs, so generating again never overwrites an earlier image or log (logs: etc/runs/<run id>/). The first generate of a job opens the contact sheet in the browser, even if it fails; the open tab refreshes itself.

status: ok | refused (codex's moderation blocked it; the line says whether the prompt or the output image was blocked) | executor_error (codex itself failed) | timeout | prompt_altered (codex changed the prompt even after one retry; image kept, cannot be chosen) | path_mismatch (image came from outside this run's thread folder; kept, cannot be chosen) | silent_no_image (no image and no reason found) | interrupted (the generating process died).
verbatim compares the prompt with what codex reports it passed (its own report, not an observation of the tool call): exact or normalized (whitespace only) pass; unverified (no report) passes with a warning; mismatch is retried once with a stronger instruction.
aspect_ok compares the PNG with the version's aspect within 1% (absent for aspect none). alpha appears for --transparent versions: whether the PNG has an alpha channel and the share of fully transparent pixels.

What image_gen cannot do whatever the prompt says: no pixel size (about 1.57 MP in every ratio), no mask, no seed, no output path.

failures: exit 3 if codex is missing or logged out (nothing is attempted); exit 1 if every image failed, or a version does not exist, is not a generate or edit version, or references an image that no longer exists; exit 2 if the job does not exist; exit 0 when at least one image succeeded.""")
    p.add_argument("job", type=job_type, help="short name under data/ or a path")
    p.add_argument("--version", type=int, action="append", required=True, metavar="N", help="a recorded version to generate; repeatable")
    p.add_argument("--n", type=int, default=1, choices=range(1, 7), metavar="K", help="images per version, 1-6 (default 1)")
    p.add_argument("--timeout", type=int, default=300, metavar="S", help="seconds before one codex call is stopped and recorded as timeout (default 300)")

    p = command("record", """\
output: {"written": [...], "finals": [names]}

failures: exit 2 if the job does not exist, --critique or --chosen come without --version, --scope without --note, or there is nothing to write; exit 1 if --version names no version, --chosen is not an ok attempt of a generated --version, a --final is not a rendered version or an ok attempt, or an --unfinal is not a final.""", details="""\
--note appends 성진's words as he said them (or a fact Claude must keep), scoped to this job unless --scope reusable (a preference that holds for later jobs; show --all lists them), tied to --version when given. --critique is Claude's current assessment of a version and replaces the previous one. --chosen picks an attempt of a generated version (v3-2). Finals are a set of what was accepted: a document version (v5) or an attempt (v3-2); --final adds, --unfinal removes.""")
    p.add_argument("job", type=job_type, help="short name under data/ or a path")
    p.add_argument("--version", type=int, metavar="N", help="the version --note, --critique and --chosen refer to")
    p.add_argument("--note", action="append", default=[], metavar="T", help="성진's words or a fact to keep; repeatable")
    p.add_argument("--scope", choices=["job", "reusable"], help="job (default): true of this job only; reusable: a preference for later jobs")
    p.add_argument("--critique", metavar="T", help="what the version actually shows and what to change; replaces the previous critique")
    p.add_argument("--chosen", metavar="vN-k", help="the attempt picked from a generated --version")
    p.add_argument("--final", action="append", default=[], metavar="NAME", help="add an accepted result: vN (document version) or vN-k (attempt); repeatable")
    p.add_argument("--unfinal", action="append", default=[], metavar="NAME", help="take a result out of the finals; repeatable")

    p = command("sheet", """\
output: {"sheet": <path>}

The sheet is rebuilt by every command that writes the ledger, and an open tab reloads itself when it changes; use this to rebuild or open it again. Click an image to enlarge it; ← and → step through every image in sheet order, Esc closes.

failures: exit 2 if the job does not exist.""")
    p.add_argument("job", type=job_type, help="short name under data/ or a path")
    p.add_argument("--open", action="store_true", help="open it in the default browser")

    p = command("fonts-search", """\
output: {"summary", "url": the noonnu page read, "fonts": [{"id", "name", "maker", "weights": number of styles | null, "url"}], "next"?}
24 fonts per page, in noonnu's popularity order. Every font noonnu lists is free for some commercial use; what each use allows is per font (fonts-info).

failures: exit 3 if noonnu cannot be reached; exit 1 if the page lists no font, noonnu answers with an error, or its page no longer looks like a listing (the message says which).""", details="""\
With a query, noonnu's own search by font or maker name (Korean or English); the filters do not apply to it. Without one, the index filtered by every --use and --style given (all must hold).""")
    p.add_argument("query", nargs="?", help="font or maker name to search for, e.g. 붓 or 프리텐다드")
    p.add_argument("--use", action="append", default=[], choices=fonts.USES, help="a use the license must allow outright; repeatable: print (인쇄), web (웹사이트), package (포장지), video (영상: YouTube, subtitles), embed (임베딩), bici (BI/CI: logos, names, slogans), ofl (the file may be modified and redistributed)")
    p.add_argument("--style", action="append", default=[], choices=fonts.STYLES, help="noonnu's style category; repeatable: gothic (고딕), serif (바탕), handwriting (손글씨), display (장식체), pixel (픽셀체), classic (고전체), unboxed (탈네모), calligraphy (캘리폰트), coding (코딩체), latin (영문)")
    p.add_argument("--page", type=int, default=1, metavar="N", help="listing page, from 1 (default 1)")

    p = command("fonts-info", """\
output: {"id", "name", "url", "maker", "style", "weights", "tags", "license": {use: allowed | conditional | not_allowed}, "license_text": the license as noonnu quotes it, "download_page": the distributor's page | null, "webfonts": [{"family", "weight", "url"}], "imports": [stylesheets], "webfont_installable": bool, "install_from"?}
Uses: print web package video embed bici ofl, as in fonts-search. conditional means the license text sets conditions (credit, no modification, public bodies only…): read license_text before relying on it. noonnu itself says its table is a guide and the rights holder's license decides.

failures: exit 3 if noonnu cannot be reached; exit 1 if the font does not exist (HTTP 404) or the page no longer has the parts read here.""")
    p.add_argument("id", type=int, help="noonnu font id, from fonts-search or a noonnu.cc/font_page/<id> URL")

    p = command("fonts-install", """\
output: {"summary", "fonts": [{"from", "family", "style", "postscript", "hangul": syllables it draws (11172 = all), "hangul_blank"?: syllables mapped to empty glyphs, "missing_ks_x_1001"?, "file"?, "status": installed | already_installed | kept_existing | refused (no usable family name, or blank Hangul glyphs: nothing written)}], "seen_by": {"photocraft": {family: [styles]}, "vectorcraft": {family: [styles]}}, "license"?: {"font", "noonnu", "license", "download_page"}, "warnings"?}
family and style are the names the apps resolve (typographic family first); seen_by is what PhotoCraft and VectorCraft actually list under them, which is what a type layer must name. A running app may need its font list rescanned or a restart to see a new font.

failures: exit 1 if a noonnu font is not OFL (the error carries its license and download page; download the file there and install it), has no webfont file in the given weights, every face was refused, or noonnu answers with an error; exit 4 if a file is not a font or a zip holding one; exit 3 if noonnu or the font host cannot be reached.""", details="""\
Web formats (woff2, woff) are converted to .otf (CFF outlines) or .ttf (TrueType) named after the PostScript name; .ttf, .otf and .ttc files go in as they are; a zip is unpacked for its font files. A file already in the fonts folder is never replaced: the same bytes count as already_installed, different bytes are kept and warned about. A face covering only some Hangul syllables is warned about: a syllable outside them renders in a fallback font, which proof's font-name check does not catch. A face with no family name, or a subsetting tool's placeholder name (WebSubsetFont), is refused: no app could select it, and two of them would answer to one name. A face that maps Hangul syllables to empty glyphs is refused too: the apps print a gap there, with no fallback font and no missing-glyph report. noonnu's web copies are often like that (cut down to KS X 1001 but keeping every syllable in the character map); their distributor's file is not.""")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--noonnu", type=int, metavar="ID", help="install this noonnu font from noonnu's webfont copy (OFL fonts only)")
    src.add_argument("--file", nargs="+", action="extend", metavar="PATH", help="font files (.ttf .otf .ttc .woff .woff2) or zips holding them, e.g. what a distributor's download page gave")
    p.add_argument("--weight", type=int, action="append", default=[], metavar="W", help="with --noonnu: only the webfont faces of this CSS weight (100-900); repeatable (default every face)")
    return ap


# ---- dispatch --------------------------------------------------------------------------------

def run(args: argparse.Namespace, ap: Parser) -> tuple[dict, int]:
    cmd = args.command
    if cmd == "new":
        brief = {"request": args.request}
        for key in ("purpose", "platform", "size", "aspect"):
            if getattr(args, key):
                brief[key] = getattr(args, key)
        if args.text:
            brief["text"] = args.text
        if args.reserved:
            brief["reserved"] = args.reserved
        return jobs.new(args.kind, args.title, brief=brief, sources=args.source, targets=args.target, open_sheet=not args.no_open), 0
    if cmd == "show":
        if args.all:
            return jobs.show_all(), 0
        if args.job is None:
            ap.error("show: give a job, or --all")
        return jobs.show(args.job), 0
    if cmd == "add":
        if sys.stdin.isatty():
            ap.error("add: the prompt is read from stdin; pipe or heredoc it in")
        prompt = sys.stdin.read().strip()
        if not prompt:
            ap.error("add: the prompt on stdin is empty")
        if args.kind == "edit" and not args.ref:
            ap.error("add: --kind edit needs at least one --ref")
        return generate.add(args.job, prompt=prompt, direction=args.direction, kind=args.kind, refs=[paths.resolve_input(r) for r in args.ref], aspect=args.aspect, transparent=args.transparent, parent=args.parent, change=args.change), 0
    if cmd == "generate":
        result = generate.run(args.job, versions=args.version, n=args.n, timeout=args.timeout)
        return result, 0 if any(r["status"] == "ok" for r in result["results"]) else 1
    if cmd == "record":
        if (args.critique is not None or args.chosen) and args.version is None:
            ap.error("record: --critique and --chosen need --version")
        if args.scope and not args.note:
            ap.error("record: --scope goes with --note")
        if not any([args.note, args.critique is not None, args.chosen, args.final, args.unfinal]):
            ap.error("record: nothing to write; give --note, --critique, --chosen, --final or --unfinal")
        return jobs.record(args.job, notes=args.note, scope=args.scope or "job", version=args.version, critique=args.critique, chosen=args.chosen, finals=args.final, unfinals=args.unfinal), 0
    if cmd == "sheet":
        return {"sheet": str(sheet.rebuild(args.job, open_it=args.open))}, 0
    if cmd == "fonts-search":
        if args.page < 1:
            ap.error("fonts-search: --page starts at 1")
        if args.query and (args.use or args.style):
            ap.error("fonts-search: noonnu's name search ignores --use and --style; give a query or filters, not both")
        result = fonts.search(args.query, args.use, args.style, args.page)
        return result, 0 if result["fonts"] else 1
    if cmd == "fonts-info":
        return fonts.info(args.id), 0
    if cmd == "fonts-install":
        if args.weight and args.noonnu is None:
            ap.error("fonts-install: --weight goes with --noonnu")
        return fonts.install(font_id=args.noonnu, files=[paths.resolve_input(f) for f in args.file or []], weights=args.weight), 0
    ap.error("a command is required")
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        doc, code = run(args, ap)
    except Usage as exc:
        ap.error(exc.message)
    except Failure as exc:
        emit(exc.payload())
        return exc.code
    except OSError as exc:
        emit({"error": f"{type(exc).__name__}: {exc}"})
        return 1
    emit(doc)
    return code


if __name__ == "__main__":
    sys.exit(main())
