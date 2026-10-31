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

from design import fonts, paths
from design.errors import Failure, Usage

TOP_EPILOG = """\
<job> is a short name under data/ (a new one must read <kind>_<YYMMDD>_<title>) or a path (/, ~, .).
Every command prints one JSON document on stdout, progress on stderr.
exit: 0 success · 1 ran but produced no result · 2 bad arguments · 3 environment cannot run (an ArtCraft CLI or app, codex, macOS Vision, the network) · 4 an input file cannot be read · 5 going on would lose 성진's work (the document is open in an app, or holds changes no version has)
Environment: DESIGN_DATA overrides data/; DESIGN_FONTS_DIR overrides ~/Library/Fonts.
Run `<command> --help` for each command's arguments, output and failures."""

COMMANDS = {
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


# ---- parser ----------------------------------------------------------------------------------

def build_parser() -> Parser:
    commands = "\n".join(f"  {name:<14} {summary}" for name, summary in COMMANDS.items())
    ap = Parser(prog="cli.py", usage="cli.py <command> [options]", description=f"{__doc__}\n\ncommands:\n{commands}", epilog=TOP_EPILOG, formatter_class=formatter)
    sub = ap.add_subparsers(dest="command", metavar="<command>", parser_class=Parser, help=argparse.SUPPRESS)

    def command(name: str, epilog: str, details: str | None = None) -> Parser:
        summary = COMMANDS[name] + "."
        return sub.add_parser(name, prog=f"cli.py {name}", description=f"{summary}\n\n{details}" if details else summary, epilog=epilog, formatter_class=formatter)

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
