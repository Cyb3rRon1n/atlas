from atlas.web.posture_page import render_posture_page
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
    assert "innerHTML" not in html.split("<script>")[-1]
