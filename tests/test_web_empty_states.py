"""The shared empty state and every page that shows it instead of a blank chart or a bare sentence."""

from datetime import datetime, timedelta

from lanxang.web.render import empty_state


NOW = datetime(2026, 10, 11, 12)


def test_empty_state_has_icon_title_why_and_an_escaped_action():

    html = empty_state("chat", "Nothing <yet>", "One sentence.", ("/settings#ai", "Turn on in Setup"))

    assert html.startswith('<div class="empty" role="status"><svg class="ic"')
    assert '<p class="empty-title">Nothing &lt;yet&gt;</p>' in html and '<p class="muted">One sentence.</p>' in html
    assert '<a class="btn primary" href="/settings#ai">Turn on in Setup →</a>' in html
    assert "<a " not in empty_state("check", "All seen", "Why.")


def test_empty_state_style_is_shared():

    from lanxang.web.render import PAGE_STYLE

    assert ".empty { display:flex;" in PAGE_STYLE and ".empty .empty-title" in PAGE_STYLE


def _trends(direct=0, new=0):
    return {"hours": [{"hour": f"2026-10-10T{h:02d}:00:00", "direct": direct, "vpn": 0} for h in range(24)],
            "new_per_day": [{"day": f"2026-10-0{d}", "count": new} for d in range(1, 8)]}


def test_home_security_trends_without_traffic_is_an_empty_state_not_a_chart():

    from lanxang.web.home_page import _trends_card

    html = _trends_card(_trends())
    assert 'class="empty"' in html and "No traffic data yet" in html and "<svg viewBox" not in html
    assert "wide" not in html.split(">")[0]                               # a normal-size card, not a 2x2 blank
    assert "<a " not in html.split(">", 1)[1]                             # the card itself is the link
    busy = _trends_card(_trends(direct=100))
    assert 'class="empty"' not in busy and "Outbound traffic" in busy
    assert "No new destinations in the last 7 days." in busy and "New destinations per day" not in busy
    assert "New destinations per day" in _trends_card(_trends(direct=100, new=2))


def test_trends_with_too_little_history_shows_collecting_not_a_dot():

    from lanxang.web.trends_page import _chart, render_trends_page

    few = [(NOW - timedelta(minutes=15 * i), {"cpu": 10, "mem": 5, "disk": 40}) for i in range(3)]
    html = render_trends_page(few, [], "24h", NOW)
    assert 'class="empty"' in html and "Collecting history" in html and "<ellipse" not in html
    lone = _chart("CPU", [("CPU", [(NOW, 10)])], NOW - timedelta(days=1), NOW)
    assert "<svg" not in lone and "collecting" in lone
    enough = [(NOW - timedelta(minutes=15 * i), {"cpu": 10}) for i in range(8)]
    assert 'class="empty"' not in render_trends_page(enough, [], "24h", NOW)


def test_visitors_off_is_an_empty_state_with_the_config_key_tucked_away():

    from lanxang.web.access_page import render_access_page

    html = render_access_page({"visitors": [], "logins": []}, "7d", enabled=False)
    assert 'class="empty"' in html and "Visitor tracking is off" in html
    assert "<details><summary>How to turn it on</summary>" in html and "access.enabled: true" in html
    assert "atlas-scan" not in html


def test_chat_without_ai_points_to_the_setup_ai_card(monkeypatch):

    from lanxang.web import render
    from lanxang.web.chat_page import render_chat_page

    monkeypatch.setattr(render, "AI_ON", False)
    html = render_chat_page("hi")
    assert 'class="empty"' in html and 'href="/settings#ai"' in html and 'id="ask"' not in html
    monkeypatch.setattr(render, "AI_ON", True)
    assert 'id="ask"' in render_chat_page("hi") and 'href="/settings#ai"' not in render_chat_page("hi")


def test_coverage_known_but_invisible_empty_state():

    from lanxang.web.devices_pages import render_coverage_page

    html = render_coverage_page({"sources": [], "quiet": [], "invisible": []})
    assert 'class="empty"' in html and "Nothing invisible" in html and "None.</p>" not in html
    assert "No scans yet" in html and "<table>" not in html


def test_sidebar_chat_link_only_with_ai(monkeypatch):

    from lanxang.web import render

    monkeypatch.setattr(render, "AI_ON", False)
    assert 'class="chat-link"' not in render.render_page("X", "", drawer=False)
    monkeypatch.setattr(render, "AI_ON", True)
    assert '<a class="chat-link" href="/chat">Chat</a>' in render.render_page("X", "", drawer=False)
