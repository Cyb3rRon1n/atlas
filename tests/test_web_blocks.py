import re
from datetime import datetime

from lanxang.web.blocks import bar_chart, check_row, day_strip, nice_top, sparkline, status_hero, timeline, trend_tile


def test_nice_top():

    assert nice_top(0) == 1
    assert nice_top(-3) == 1
    assert nice_top(7) == 10
    assert nice_top(23) == 25
    assert nice_top(51) == 100
    assert nice_top(1.6) == 2
    assert nice_top(10) == 10
    assert nice_top(0.3) == 0.5


def test_bar_chart_axes():

    html = bar_chart([0, 5, 23], ["a", "b", "c"], {0: "06:00", 2: "18:00"}, unit=" MB")

    for text in ("0 MB", "12.5 MB", "25 MB", "06:00", "18:00", "<title>c</title>"):
        assert text in html
    assert html.count("<rect") == 3
    for element in re.findall(r"<[^>]*preserveAspectRatio=\"none\"[^>]*>.*?</svg>", html, re.S):
        assert "<text" not in element
    assert "peak 23 MB" in html and "total 28 MB" in html     # the text equivalent


def test_bar_chart_all_zero_and_single():

    zeros = bar_chart([0, 0], ["a", "b"], {})
    assert ">1<" in zeros
    single = bar_chart([4], ["only"], {0: "Mon"}, fmt=lambda v: f"{v:g} hits")
    assert single.count("<rect") == 1 and "4 hits" in single and "Mon" in single
    assert bar_chart([], [], {}) == ""


def test_sparkline_skips_short_and_none():

    assert sparkline([], "x") == ""
    assert sparkline([5], "x") == ""
    assert sparkline([5, None], "x") == ""

    points = re.search(r'points="([^"]*)"', sparkline([1, None, 3], "x")).group(1).split()
    assert len(points) == 2

    long = sparkline(list(range(300)), "x")
    assert len(re.search(r'points="([^"]*)"', long).group(1).split()) <= 30
    assert "<title>x: min 0, max 299, now 299</title>" in long

    flat = sparkline([4, 4, 4], "y")      # a flat line still draws, mid-height
    assert "polyline" in flat


def test_day_strip_text():

    assert 'aria-label="2 of 3 days ok"' in day_strip(["ok", "bad", "none", "ok"])
    assert "no data" in day_strip(["none"] * 7)
    assert day_strip(["ok", "bad", "none"]).count('class="d ') == 3


def test_status_hero_states():

    unknown = status_hero(0, "No recent scan", "last scan 2 h ago", "unknown")
    assert "?" in unknown and "hero unknown" in unknown

    ok = status_hero(0, "All good", "last scan 2 min ago", "ok")
    assert not re.search(r">\d+<", ok)

    attention = status_hero(2, "2 things need a look", "", "attention")
    assert ">2<" in attention and "hero attention" in attention

    assert "&lt;i&gt;" in status_hero(1, "<i>", "", "attention")


def test_trend_tile():

    tile = trend_tile("CPU", "12", "%", points=[1, 2, 3], href="/hosts")
    assert tile.startswith('<a class="trend ok"') and 'href="/hosts"' in tile and "polyline" in tile

    plain = trend_tile("Internet", "99.9", "%", points=None, state="attention", note="1 outage")
    assert plain.startswith('<div class="trend attention"') and "polyline" not in plain and "1 outage" in plain

    strip = trend_tile("Services", "7 of 7", strip=day_strip(["ok"] * 7), points=[1, 2])
    assert "7 of 7 days ok" in strip and "polyline" not in strip


def test_check_row_and_timeline():

    row = check_row("eye", "T", "d", ("See them", "/devices?f=1"))
    assert 'href="/devices?f=1"' in row and 'class="btn' in row and "See them" in row
    assert "&lt;b&gt;" in check_row("x", "<b>")
    assert 'class="checkrow done"' in check_row("check", "Done", state="done")

    html = timeline([(datetime(2026, 11, 19, 6, 12), "New device", "Galaxy-Tab", "attention")])
    assert "New device" in html and "Galaxy-Tab" in html and "06:12" in html
    old = timeline([(datetime(2020, 1, 2, 9, 30), "Back online", "NAS", "ok")])
    assert "2020-01-02" in old and "09:30" in old                       # not today: the date is shown too
    from lanxang.clock import utcnow
    shown = re.search(r"<time[^>]*>([^<]*)</time>", timeline([(utcnow(), "Now", "", "info")])).group(1)
    assert re.fullmatch(r"\d\d:\d\d", shown)                                # today: the time only
    assert timeline([]) == ""


def test_render_page_includes_block_style_once():

    from lanxang.web.render import render_page

    assert render_page("x", "").count("/* blocks */") == 1
