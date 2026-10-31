"""noonnu's pages read through the noonnu unit's parsers, on pages saved from noonnu.cc on 2026-10-31; the expected values were read off those pages by eye."""

from __future__ import annotations

from pathlib import Path

import pytest

from design import noonnu

PAGES = Path(__file__).resolve().parents[1] / "fixtures" / "noonnu"


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def test_index_cards_in_page_order():
    cards = noonnu.parse_listing(page("index.html"))
    assert len(cards) == 24
    assert [c.id for c in cards[:4]] == [694, 1456, 366, 223]
    first, second = cards[0], cards[1]
    assert (first.name, first.maker, first.weights) == ("프리텐다드", "길형진 (orioncactus)", 9)
    assert (second.name, second.maker) == ("페이퍼로지", "이주임 X 김도균")
    assert first.url == "https://noonnu.cc/font_page/694"


def test_search_page_cards():
    assert [c.id for c in noonnu.parse_listing(page("search_brush.html"))] == [1279, 43, 1206, 886]


def test_filtered_listing_url_carries_every_filter():
    url = noonnu.listing_url(None, ["video", "bici"], ["handwriting"], 2)
    assert url == "https://noonnu.cc/index?category_use_ids%5B%5D=7&category_use_ids%5B%5D=1&category_style_ids%5B%5D=3&order_by=pd&page=2"
    assert noonnu.listing_url("붓", ["video"], [], 1) == "https://noonnu.cc/search?search=%EB%B6%93&page=1"


def test_ofl_font_page():
    f = noonnu.parse_font(page("font_page_694.html"), 694)
    assert (f.name, f.maker, f.style, f.weights) == ("프리텐다드", "길형진 (orioncactus)", "고딕", 9)
    assert f.license == {"print": "allowed", "web": "allowed", "package": "allowed", "video": "allowed", "embed": "allowed", "bici": "allowed", "ofl": "allowed"}
    assert f.download_page == "https://cactus.tistory.com/306"
    assert [w.weight for w in f.webfonts] == [100, 200, 300, 400, 500, 600, 700, 800, 900]
    assert f.webfonts[-1].url == "https://cdn.jsdelivr.net/gh/projectnoonnu/pretendard@1.0/Pretendard-Black.woff2"
    assert {w.family for w in f.webfonts} == {"Pretendard"}
    assert "SIL 오픈 폰트 라이선스" in f.license_text


def test_conditional_font_page_without_ofl():
    f = noonnu.parse_font(page("font_page_1279.html"), 1279)
    assert f.name == "가평 한석봉 큰붓" and f.maker == "가평군청 X 윤디자인그룹"
    assert f.license["print"] == "conditional" and f.license["video"] == "conditional" and f.license["ofl"] == "not_allowed"
    assert f.download_page == "https://www.gp.go.kr/portal/contents.do?key=2410"
    assert "고전체" in f.tags and "붓글씨" in f.tags
    assert "원본 글씨 형태의 변형 없이" in f.license_text
    assert len(f.webfonts) == 3


def test_webfont_through_an_imported_stylesheet():
    f = noonnu.parse_font(page("font_page_43.html"), 43)
    assert f.webfonts == [] and f.imports == ["https://fonts.googleapis.com/earlyaccess/nanumbrushscript.css"]
    assert f.license["ofl"] == "allowed"


def test_a_page_without_the_license_table_says_noonnu_changed():
    with pytest.raises(noonnu.Changed, match="license summary table"):
        noonnu.parse_font("<html><h2>이름</h2></html>", 1)


def test_the_ofl_verdict_reads_the_main_clause():
    from design.noonnu import parse_font

    page = page_with = (PAGES / "font_page_694.html").read_text(encoding="utf-8")
    page = page.replace("폰트 파일 수정·복제·배포 가능", "폰트 파일 수정·복제·배포 불가능")
    assert parse_font(page, 694).license["ofl"] == "not_allowed"
    assert parse_font(page_with, 694).license["ofl"] == "allowed"
