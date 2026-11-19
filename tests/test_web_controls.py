"""One control system: shared button/input styles in the base CSS, and one segmented control for every switch."""

import re
from datetime import datetime

from lanxang.web import changes_feed
from lanxang.web.access_page import render_access_page
from lanxang.web.cabling_page import render_cabling_page
from lanxang.web.posture_page import render_posture_page
from lanxang.web.render import PAGE_STYLE, render_history_page, segmented
from lanxang.web.trends_page import render_trends_page
from lanxang.web.uptime_page import render_uptime_page
from tests.test_web_cabling import _latest

NOW = datetime(2026, 1, 1, 12)


def _seg(html, label):
    match = re.search(r'<div class="[^"]*\bseg\b[^"]*" role="group" aria-label="' + label + r'">(.*?)</div>', html)
    assert match, label
    return match.group(1)


def test_base_styles_define_one_control_system():
    css = PAGE_STYLE.replace("\n", " ")
    assert "--control-h:36px" in css
    button = css.split(":where(button:not(.port, .box, .chip, [role=tab], .side button), .btn) {")[1].split("}")[0]
    assert "min-height:var(--control-h)" in button and "margin:0" in button
    for variant in (".primary {", ".secondary {", ".danger {", ":disabled"):
        assert variant in css, variant
    assert "{ min-height:var(--control-h); }" in css                   # inputs and selects share the height
    assert "outline:2px solid var(--accent)" in css                     # a brand-coloured focus ring
    assert ".seg > [aria-current], .seg > [aria-pressed=\"true\"]" in css
    assert ".sm { min-height:30px;" in css
    # a disabled button never takes a hover colour; hovering the current segment keeps its highlight
    assert ".danger:not(:disabled):hover" in css and ".primary:not(:disabled):hover" in css
    assert ".danger:hover" not in css and ".primary:hover" not in css
    assert '.seg > a:not([aria-current]):hover, .seg > button:not([aria-pressed="true"]):hover' in css


def test_segmented_links_mark_the_current_one():
    html = segmented(("24h", "7d"), "7d", "/x?w={key}")
    assert html.startswith('<div class="seg" role="group" aria-label="Time window">')
    assert '<a href="/x?w=24h">24 hours</a><a href="/x?w=7d" aria-current="page">7 days</a>' in html


def test_time_windows_share_the_control_and_labels():
    trends = _seg(render_trends_page([], [], "30d", NOW), "Time window")
    assert '<a href="/trends?window=30d" aria-current="page">30 days</a>' in trends and ">24 hours<" in trends
    access = _seg(render_access_page({"visitors": [], "logins": []}, "24h"), "Time window")
    assert '<a href="/access?window=24h" aria-current="page">24 hours</a>' in access
    feed_html = changes_feed.render([], NOW, "24h")
    assert '<div class="changes-head"><h2>What changed</h2><div class="seg"' in feed_html   # switch beside, not inside, the h2
    feed = _seg(feed_html, "Time window")
    assert '<a href="/history?changes=24h" aria-current="page">24 hours</a>' in feed and ">7 days<" in feed
    posture = _seg(render_posture_page(), "Time window")
    assert 'data-window="24h" aria-pressed="true"' in posture and ">1 hour<" in posture and ">1 h<" not in posture


def test_view_switches_use_the_control_and_keep_their_hooks():
    views = _seg(render_cabling_page(_latest(), [], True, now=NOW), "View")
    assert 'data-view="faceplates" aria-pressed="true"' in views and 'data-view="diagram" aria-pressed="false"' in views
    filters = _seg(render_history_page([type("E", (), {"created_at": NOW, "event_type": "x.y", "source": "s",
                                                       "payload": "{}"})()]), "Show")
    assert 'data-filter="important" aria-pressed="true"' in filters


def test_pages_use_the_shared_button_classes():
    cabling = render_cabling_page(_latest(), [], True, now=NOW)
    assert '<button class="primary" id="wiring-refresh"' in cabling and '<a class="btn" href="/cabling.csv"' in cabling
    uptime = render_uptime_page([], {}, NOW, suggestions=[("Photos", "https://photos.example.org")])
    assert '<button class="primary" type="submit">Add</button>' in uptime
    assert 'class="secondary sm" type="button" data-name="Photos"' in uptime
    for page in (cabling, uptime):
        assert "cab-btn" not in page and "up-btn" not in page


def test_compact_controls_in_rows():
    from lanxang.web.alerts_page import render_alerts_page
    alert = {"id": 3, "title": "Printer is offline", "detail": "", "href": "/devices/1", "source": "devices",
             "device_id": 1, "opened_at": NOW, "acked_at": None, "resolved_at": None, "kind": "problem"}
    page = render_alerts_page({"open": [alert], "watch": [], "resolved": [], "muted": []}, NOW)
    acts = page.split('<div class="acts">')[1].split("</div>")[0]
    assert 'class="btn primary sm"' in acts and '<button class="sm" data-post="/api/alerts/3/ack"' in acts
    assert '<select class="sm"' in acts and '<button class="sm" data-post="/api/alerts/3/mute"' in acts
