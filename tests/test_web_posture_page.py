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
                   'data-window="24h"', 'id="posture-panel"', 'id="exposure"', "/static/cytoscape.min.js"):
        assert marker in html


def test_posture_script_contract():
    html = render_posture_page()
    for marker in ('fetch("/api/posture?window="', "/api/posture/node?id=", "/api/posture/known",
                   "preset", "textContent", "atlasAsk", "setInterval"):
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
    from atlas.web.render import render_trends_page
    assert [label for _, label, _ in NAV] == ["Home", "Posture", "Hosts", "Devices", "LAN map", "History"]
    html = render_trends_page({"host": {}, "containers": {}, "guests": {}})
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
