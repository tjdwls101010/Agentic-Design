"""noonnu.cc (눈누), the Korean free-font index, read as plain server-rendered HTML.

Everything noonnu owns stays in here: its URLs and query parameters, the ids behind its use and style filters, the shape of a font card on a listing and of a font page (the header, the license summary table, the webfont `<pre>`), and the webfont files it serves from jsdelivr or Google Fonts. Callers get `Card`, `Font` and `Webfont` in the skill's terms. When the HTML no longer has the anchors this reads by, `Changed` says which one went missing, so the fix lands here.

noonnu lists only fonts free for commercial use, but what is allowed differs per font and per use; the summary table says 사용 가능 (allowed), 조건부 허용 (allowed on conditions the license text states) or 사용 불가 per use. Its 다운로드 button is a link to the distributor's page, not a file; the only files noonnu itself serves are its webfont copies.
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from design.errors import Failure, Unavailable

__all__ = ["USES", "STYLES", "Card", "Font", "Webfont", "Changed", "search", "font", "webfont_files", "download", "parse_listing", "parse_font"]

BASE = "https://noonnu.cc"
AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) design-skill"

# The filter checkboxes on /index: name in the skill's terms → (noonnu's label, its id).
USES = {"print": ("인쇄", 5), "web": ("웹사이트", 6), "package": ("포장지", 3), "video": ("영상", 7), "embed": ("임베딩", 2), "bici": ("BI/CI", 1), "ofl": ("OFL", 4)}
STYLES = {"gothic": ("고딕", 1), "serif": ("바탕", 2), "handwriting": ("손글씨", 3), "display": ("장식체", 5), "pixel": ("픽셀체", 6), "classic": ("고전체", 7), "unboxed": ("탈네모", 8), "calligraphy": ("캘리폰트", 9), "coding": ("코딩체", 10), "latin": ("영문", 11)}
STATUS = {"사용 가능": "allowed", "조건부 허용": "conditional", "사용 불가": "not_allowed", "사용 불가능": "not_allowed"}
LABEL_TO_USE = {label: key for key, (label, _) in USES.items()}
TAG = r"(?:[^>\"']|\"[^\"]*\"|'[^']*')*"  # a tag's attributes, where a quoted value may hold ">" (data-action="click->…")


class Changed(Failure):
    """noonnu's HTML lost an anchor this unit reads by: the site changed, not the request."""


@dataclass
class Card:
    id: int
    name: str
    maker: str
    weights: int | None
    url: str


@dataclass
class Webfont:
    family: str
    weight: int | None
    url: str


@dataclass
class Font:
    id: int
    name: str
    url: str
    maker: str | None = None
    style: str | None = None
    weights: int | None = None
    tags: list[str] = field(default_factory=list)
    license: dict[str, str] = field(default_factory=dict)  # use → allowed | conditional | not_allowed | the label as written
    license_text: str = ""
    download_page: str | None = None
    webfonts: list[Webfont] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)  # stylesheets the webfont code pulls in (Google Fonts)


def _get(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "ko"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise Failure(f"{url} answered HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Unavailable(f"could not reach {urllib.parse.urlsplit(url).netloc} ({exc})") from exc


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace collapsed; <br> becomes a newline."""
    fragment = re.sub(r"<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"<(script|style|svg)\b.*?</\1>", "", fragment, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def listing_url(query: str | None, uses: list[str], styles: list[str], page: int) -> str:
    if query:
        return f"{BASE}/search?" + urllib.parse.urlencode({"search": query, "page": page})
    params = [("category_use_ids[]", USES[u][1]) for u in uses] + [("category_style_ids[]", STYLES[s][1]) for s in styles] + [("order_by", "pd"), ("page", page)]
    return f"{BASE}/index?" + urllib.parse.urlencode(params)


def parse_listing(page: str) -> list[Card]:
    """The font cards of an index or search page, in the page's order."""
    cards = []
    for m in re.finditer(r'<a\b' + TAG + r'href="/font_page/(\d+)"' + TAG + r'>(.*?)</a>', page, re.S):
        body = m.group(2)
        alt = re.search(r'<img[^>]*\balt="([^"]*)"', body)
        maker = re.search(r"<p\b[^>]*>(.*?)</p>", body, re.S)
        if not alt or not maker:
            continue  # a plain link to a font (similar fonts, a notice), not a card
        rest = page[m.end(): m.end() + 4000]
        weights = re.search(r'data-fonts-target="fontVariantsCount">\s*(\d+)', rest)
        fid = int(m.group(1))
        cards.append(Card(fid, html.unescape(alt.group(1)).strip(), _text(maker.group(1)), int(weights.group(1)) if weights else None, f"{BASE}/font_page/{fid}"))
    seen: set[int] = set()
    return [c for c in cards if not (c.id in seen or seen.add(c.id))]


def search(query: str | None = None, uses: list[str] = (), styles: list[str] = (), page: int = 1) -> tuple[str, list[Card]]:
    """One listing page: by name or maker (`query`, noonnu's own search, which ignores the filters) or by use and style filters, every filter required. Returns the page's URL and its cards."""
    url = listing_url(query, list(uses), list(styles), page)
    text = _get(url).decode("utf-8", "replace")
    cards = parse_listing(text)
    if not cards and "font_page" not in text and "noon-page-fonts" not in text and "search" not in text:
        raise Changed(f"{url} has no font cards and none of the markers of a listing; noonnu's page layout may have changed")
    return url, cards


def _field(page: str, label: str) -> str | None:
    m = re.search(r">\s*" + re.escape(label) + r"\s*</span>\s*<span[^>]*>(.*?)</span>", page, re.S)
    return _text(m.group(1)) if m else None


def _ofl(description: str) -> str:
    """The OFL row leaves its status cell empty and says it in the description: "폰트 파일 수정·복제·배포 가능 (단, 유료 판매는 금지)" or "… 모두 금지"."""
    if "가능" in description:
        return "allowed"
    if "금지" in description:
        return "not_allowed"
    return description


def _faces(css: str) -> list[Webfont]:
    out = []
    for block in re.findall(r"@font-face\s*\{(.*?)\}", css, re.S):
        family = re.search(r"font-family\s*:\s*['\"]?([^;'\"]+)", block)
        weight = re.search(r"font-weight\s*:\s*(\d+)", block)
        for url in re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", block):
            if re.search(r"\.(woff2|woff|ttf|otf)(\?|$)", url, re.I):
                out.append(Webfont(family.group(1).strip() if family else "", int(weight.group(1)) if weight else None, "https:" + url if url.startswith("//") else url))
                break  # one file per face: the first src the browser would take
    return out


def parse_font(page: str, font_id: int) -> Font:
    title = re.search(r"<h2\b[^>]*>(.*?)</h2>", page, re.S)
    if not title:
        raise Changed(f"font page {font_id} has no <h2> title; noonnu's page layout may have changed")
    font = Font(font_id, _text(title.group(1)), f"{BASE}/font_page/{font_id}")
    font.maker = _field(page, "제작")
    font.style = _field(page, "형태")
    weights = _field(page, "굵기")
    font.weights = int(re.match(r"\d+", weights).group(0)) if weights and re.match(r"\d+", weights) else None
    head_end = page.find("다운로드 페이지로 이동")
    head = page[title.end(): head_end if head_end > 0 else title.end() + 6000]
    font.tags = [html.unescape(t).strip() for t in re.findall(r'href="/index\?search=[^"]*"[^>]*>([^<]+)</a>', head)]
    dl = re.search(r'<a\b' + TAG + r'href="([^"]+)"' + TAG + r'>\s*<span>\s*다운로드 페이지로 이동', page)
    if dl:
        target = html.unescape(dl.group(1))
        parts = urllib.parse.urlsplit(target)
        query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if not (k == "ref" and v == "noonnu.cc")]
        font.download_page = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    table = re.search(r"라이선스 요약표.*?<tbody[^>]*>(.*?)</tbody>", page, re.S)
    if not table:
        raise Changed(f"font page {font_id} has no license summary table (라이선스 요약표); noonnu's page layout may have changed")
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table.group(1), re.S):
        cells = [_text(c) for c in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 3:
            use = LABEL_TO_USE.get(cells[0], cells[0])
            font.license[use] = _ofl(cells[1]) if use == "ofl" and not cells[2] else STATUS.get(cells[2], cells[2])
    body = re.search(r"라이선스 본문.*?<article[^>]*>(.*?)</article>", page, re.S)
    font.license_text = _text(body.group(1)) if body else ""
    pre = re.search(r'<pre[^>]*name="webfontSource"[^>]*>(.*?)</pre>', page, re.S)
    if pre:
        css = html.unescape(pre.group(1))
        font.webfonts = _faces(css)
        font.imports = ["https:" + u if u.startswith("//") else u for u in re.findall(r"@import\s+url\(\s*['\"]?([^'\")]+)", css)]
    return font


def font(font_id: int) -> Font:
    return parse_font(_get(f"{BASE}/font_page/{font_id}").decode("utf-8", "replace"), font_id)


def webfont_files(f: Font) -> list[Webfont]:
    """The font files behind a font's webfont code: its own @font-face URLs, or the faces of the stylesheets it imports (Google Fonts serves TrueType to a plain request)."""
    files = list(f.webfonts)
    for sheet in f.imports:
        files += _faces(_get(sheet).decode("utf-8", "replace"))
    unique: dict[str, Webfont] = {}
    for w in files:
        unique.setdefault(w.url, w)
    return list(unique.values())


def download(url: str) -> bytes:
    return _get(url, timeout=120)
