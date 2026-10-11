from atlas.web.posture_page import POSTURE_SCRIPT, render_posture_page
from atlas.web.render import NAV, render_page


def test_nav_has_four_sections_and_marks_active():
    html = render_page("Devices", "<p>x</p>", active="devices")
    for href, label, _ in NAV:
        assert f'href="{href}"' in html and label in html
    assert 'aria-current="page" href="/devices"' in html or 'href="/devices" aria-current="page"' in html


def test_tabs_render_with_current_marked():
    html = render_page("Triage", "", active="devices",
                       tabs=[("/devices", "Devices", False), ("/triage", "Triage", True)])
    assert 'class="tabs"' in html and ">Triage<" in html


def test_posture_page_shell():
    html = render_posture_page()
    for marker in ('id="strip"', 'id="posture-map"', 'data-window="live"', 'data-window="1h"',
                   'data-window="24h"', 'id="posture-panel"', 'id="exposure"'):
        assert marker in html
    assert "cytoscape" not in html   # plain HTML lanes: nothing is scaled down to fit a canvas


def test_posture_script_contract():
    html = render_posture_page()
    for marker in ('fetch("/api/posture?window="', "/api/posture/node?id=", "/api/posture/known",
                   "function lanes(data)", ".lane .cols", "textContent", "atlasAsk", "setInterval"):
        assert marker in html
    assert "innerHTML" not in POSTURE_SCRIPT


def test_posture_side_lists_are_tabs_and_map_click_shows_details():
    html = render_posture_page()
    for tab in ("posture-panel", "exposure-tab", "review-tab"):
        assert f'data-tab="{tab}"' in html and f'id="{tab}"' in html
    assert 'id="exposure-tab" role="tabpanel" hidden' in html and 'id="review-count"' in html
    select = POSTURE_SCRIPT.split("async function select")[1]
    assert 'if (id === "dst:review-more") { showTab("review-tab"); return; }\n  showTab("posture-panel")' in select
    assert 'class="tabs"' not in html


def test_nav_order_and_hosts_tabs():
    from datetime import datetime
    from atlas.web.trends_page import render_trends_page
    assert [label for _, label, _ in NAV] == ["Home", "Posture", "Hosts", "Devices", "Network", "Access", "History"]
    html = render_trends_page([], [], "24h", datetime(2026, 10, 11))
    assert 'href="/overview"' in html and ">Trends<" in html


def test_docked_chat_shell_and_collapse_state():
    html = render_page("Devices", "", active="devices")
    assert '<div class="shell docked">' in html and 'id="chat-fab"' in html
    assert 'id="chat-drawer" hidden' not in html and "atlasChatCollapsed" in html
    assert 'dispatchEvent(new Event("resize"))' in html
    assert '<div class="shell">' in render_page("Chat", "", drawer=False)


def test_tabs_wrap_on_narrow_screens():
    html = render_page("x", "", tabs=[("/a", "A", True)])
    assert "flex-wrap:wrap" in html.split(".tabs {")[1].split("}")[0].replace(" ", "")


def test_posture_page_review_list_banner_and_live_label():
    html = render_posture_page()
    script = POSTURE_SCRIPT
    assert 'id="review"' in html and "Needs review" in html
    assert "renderReview(data.review)" in script and "data.enabled" in script
    assert "atlas posture watch" in script and "posture.enabled: true" in script
    assert ">This hour<" in html and 'data-window="live"' in html and ">Live<" not in html
    assert "removeClass(\"dim\")" not in script
    assert "msg.textContent = DEFAULT_MSG" in script


def test_posture_page_network_errors_are_caught():
    script = POSTURE_SCRIPT
    select = script.split("async function select")[1].split("async function load")[0]
    mark = script.split("async function markExpected")[1].split("function renderReview")[0]
    assert "try {" in select and "catch (error)" in select
    assert "try {" in mark and "button.disabled = false" in mark and "markExpected(mark" in select


def test_review_items_have_investigate_buttons_and_chips():
    html = render_posture_page()
    review = POSTURE_SCRIPT.split("function renderReview")[1].split("async function investigate")[0]
    assert '"Investigate"' in review and '"Investigate all "' in review and "markExpected(mark" in review
    inv = POSTURE_SCRIPT.split("async function investigate")[1]
    assert "/api/posture/node?id=" in inv and "Should I mark this as expected?" in inv and "catch (error)" in inv
    assert 'data-ask="Which new destinations look suspicious?"' in html
    assert "innerHTML" not in POSTURE_SCRIPT


def test_posture_and_network_scripts_are_valid_javascript(tmp_path):
    import re, shutil, subprocess
    import pytest
    if not shutil.which("node"):
        pytest.skip("node not installed")
    from atlas.web.home_page import render_home_page, build_hosts
    from types import SimpleNamespace
    from atlas.web.render import render_history_page
    from atlas.web.devices_pages import render_devices_page
    ev = SimpleNamespace(created_at="2026-01-01 00:00:00", event_type="atlas.scan.completed", source="x", payload="{}")
    pages = {"posture": render_posture_page(), "home": render_home_page(None, build_hosts(None, None, None), []),
             "history": render_history_page([ev]), "devices": render_devices_page([]),
             "access": __import__("atlas.web.access_page", fromlist=["x"]).render_access_page(
                 {"visitors": [], "logins": []}, "7d", user_places=[{"user": "u", "place_key": "US/x", "label": "l", "status": "review",
                 "first_seen": "", "last_seen": "", "ip": "", "app": "jellyfin"}])}
    for name, html in pages.items():
        for i, script in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
            f = tmp_path / f"{name}{i}.js"
            f.write_text(script)
            result = subprocess.run([shutil.which("node"), "--check", str(f)], capture_output=True, text=True)
            assert result.returncode == 0, f"{name} script {i}: {result.stderr[:300]}"
