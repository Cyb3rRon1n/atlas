"""Accessibility pass, keyboard shortcuts and the leftover review items (sightings IDs, empty sections, Activity days)."""

import json
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta

import pytest

from lanxang.config.models import DisplayConfig
from lanxang.web import render
from lanxang.web.alerts_page import render_alerts_page
from lanxang.web.network_page import render_network_page
from lanxang.web.render import KEYS_SCRIPT, render_history_page, render_page
from tests.test_web_devices_pages import device

NOW = datetime(2026, 11, 19, 12)


def lum(hex_):
    rgb = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def tokens(text):
    return dict(re.findall(r"--([\w-]+):(#[0-9a-f]{6})", text))


# --- status never by colour alone ----------------------------------------------------------------------------

def test_every_status_dot_state_has_a_glyph():
    css = render.PAGE_STYLE
    for state, glyph in ((".dot.ok", "2713"), (".ddot.seen", "2713"), (".dot.warn", '"!"'), (".dot.review", '"!"'),
                         (".ddot.quiet", '"!"'), (".dot.down", "00d7")):
        rule = next(line for line in css.splitlines() if state in line and "::after" in line)
        assert glyph in rule and '/ ""' in rule, state     # alt text "": the label already says it in words
    assert ':is(.dot, .ddot)::after { content:"\\2013"; content:"\\2013" / ""; }' in css   # unknown / no state


def _alert(id, title):
    return {"id": id, "title": title, "detail": "", "source": "certs", "href": "/posture", "device_id": None,
            "acked_at": None, "opened_at": NOW - timedelta(hours=2), "resolved_at": NOW - timedelta(minutes=30)}


def test_alert_rows_say_their_severity_in_words_and_an_icon():
    page = render_alerts_page({"open": [_alert(1, "a")], "watch": [_alert(2, "b")], "resolved": [_alert(3, "c")]}, NOW)
    for word in ("Problem", "Watching", "Resolved"):
        assert re.search(r'<span class="sev"><svg class="ic"[^>]*>.*?</svg>' + word + "</span>", page), word


def test_posture_strip_and_boxes_carry_a_mark_besides_colour():
    from lanxang.web import posture_page
    css = posture_page.POSTURE_STYLE
    for state in ("ok", "warn", "review", "unknown"):
        assert re.search(rf'#strip \.chip\.{state} \.v::before \{{ content:"[^"]+"; content:"[^"]+" / ""; \}}', css), state
    assert 'n.state === "warn") box.append(el("span", "problem", "badge"))' in posture_page.POSTURE_SCRIPT


def test_uptime_states_are_words():
    from lanxang.web.uptime_page import BEAT_LABELS, _state
    assert _state({"points": []}, 2) == ("waiting", "Waiting")
    assert _state({"points": [(False, 1), (False, 1)]}, 2) == ("down", "Down")
    assert all(word for _, word in BEAT_LABELS.values())


# --- contrast -------------------------------------------------------------------------------------------------

def test_gold_text_meets_4_5_to_1_on_light_surfaces():
    for name, light, need in (("light", render.LIGHT, 4.5), ("high contrast", render.LIGHT + render.LIGHT_HC, 7)):
        t = {**tokens(render.LIGHT), **tokens(light)}
        for bg in ("bg", "surface", "surface2"):
            assert ratio(t["gold-text"], t[bg]) >= need + .1, (name, bg, ratio(t["gold-text"], t[bg]))   # with margin
    for dark, need in ((tokens(render.DARK), 4.5), ({**tokens(render.DARK), **tokens(render.DARK_HC)}, 7)):
        for bg in ("bg", "surface", "surface2"):
            assert ratio(dark["gold-text"], dark[bg]) >= need, (bg, ratio(dark["gold-text"], dark[bg]))
    from lanxang.web import login_page
    assert "var(--gold-text)" in login_page.CARD_STYLE and "color:var(--gold)" not in login_page.CARD_STYLE


def test_high_contrast_light_sets_gold_and_the_tinted_backgrounds():
    hc = tokens(render.LIGHT_HC)
    assert {"gold", "gold-text", "warn-bg", "bad-bg"} <= hc.keys()
    assert ratio(hc["warn-text"], hc["warn-bg"]) >= 7 and ratio(hc["bad-text"], hc["bad-bg"]) >= 7


# --- skip link, order, focus ----------------------------------------------------------------------------------

def test_skip_link_is_the_first_focusable_element_and_targets_main():
    html = render_page("Devices", "<p>x</p>", active="devices")
    body = html[html.index("<body>"):]
    first = re.search(r"<(a|button|input|select|textarea)\b[^>]*>", body).group(0)
    assert first == '<a class="skip" href="#main">Skip to content</a>'[:len(first)]
    assert '<main class="page" id="main" tabindex="-1">' in html
    assert ".skip:focus { top:8px;" in render.PAGE_STYLE


def test_cabling_controls_have_a_visible_focus_ring():
    assert ":focus-visible { outline:2px solid var(--accent)" in render.PAGE_STYLE   # global, so the map's buttons too


# --- keyboard shortcuts ---------------------------------------------------------------------------------------

def test_shortcuts_sheet_markup_and_preferences_entry():
    html = render_page("Home", "", active="home")
    assert ('<div id="keys" class="keys" role="dialog" aria-modal="true" aria-labelledby="keys-title" tabindex="-1" hidden>'
            in html)
    assert '<h2 id="keys-title">Keyboard shortcuts</h2>' in html and "data-keys-close" in html
    for keys in ("<kbd>g</kbd> <kbd>h</kbd>", "<kbd>g</kbd> <kbd>d</kbd>", "<kbd>g</kbd> <kbd>a</kbd>",
                 "<kbd>g</kbd> <kbd>s</kbd>", "<kbd>/</kbd>", "<kbd>?</kbd>"):
        assert keys in html, keys
    nav = render.PREFS_PANEL[render.PREFS_PANEL.index("<h3>Navigation</h3>"):]
    assert "Keyboard shortcuts — press <kbd>?</kbd>" in nav


KEYS_HARNESS = r"""
const [script, steps] = JSON.parse(process.argv[1]);
const handlers = {}, log = [];
function node(id) { return {id, hidden: true, focused: false, focus() { log.push("focus:" + id); }, select() {},
                            querySelector() { return node("close"); }}; }
const els = {keys: node("keys"), "keys-back": node("keys-back"), prefs: node("prefs")};
const search = node("search"), app = {inert: false};
global.document = {getElementById: (id) => els[id], activeElement: null,
                   addEventListener(t, f) { handlers[t] = f; },
                   querySelector(sel) { return sel === ".app" ? app : sel.includes("search") ? search : null; }};
global.location = {href: "/"};
global.window = global;
eval(script);
for (const [key, opts] of steps) {
  const e = Object.assign({key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, defaultPrevented: false,
                           target: {tagName: "BODY"}, preventDefault() { this.defaultPrevented = true; }}, opts || {});
  handlers.keydown(e);
}
console.log(JSON.stringify({href: location.href, open: !els.keys.hidden, inert: app.inert, log}));
"""


def run_keys(*steps):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    script = KEYS_SCRIPT.removeprefix("<script>").removesuffix("</script>")
    out = subprocess.run(["node", "-e", KEYS_HARNESS, json.dumps([script, [list(s) for s in steps]])],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_g_then_a_letter_goes_to_the_page():
    for letter, href in (("h", "/?home"), ("d", "/devices"), ("a", "/alerts"), ("s", "/settings")):
        assert run_keys(("g",), (letter,))["href"] == href
    assert run_keys(("d",))["href"] == "/"                   # a letter alone does nothing


def test_shortcuts_are_ignored_while_typing_or_with_modifiers():
    for tag in ("INPUT", "TEXTAREA", "SELECT"):
        assert run_keys(("g", {"target": {"tagName": tag}}), ("d", {"target": {"tagName": tag}}))["href"] == "/"
        assert not run_keys(("?", {"target": {"tagName": tag}}))["open"]
    assert run_keys(("g", {"target": {"isContentEditable": True}}), ("d",))["href"] == "/"
    for mod in ("ctrlKey", "metaKey", "altKey"):
        assert run_keys(("g", {mod: True}), ("d", {mod: True}))["href"] == "/"
    assert run_keys(("g",), ("x",), ("d",))["href"] == "/"   # the g only counts for the very next key


def test_question_mark_opens_the_sheet_and_escape_closes_it():
    opened = run_keys(("?", {"shiftKey": True}))
    assert opened["open"] and opened["inert"] and "focus:keys" in opened["log"]
    closed = run_keys(("?", {"shiftKey": True}), ("Escape",))
    assert not closed["open"] and not closed["inert"]
    trapped = run_keys(("?",), ("Tab",))
    assert trapped["open"] and trapped["log"][-1] == "focus:close"
    assert run_keys(("?",), ("g",), ("d",))["href"] == "/"    # no navigation while the sheet is open


def test_slash_focuses_the_search_box():
    assert "focus:search" in run_keys(("/",))["log"]


# --- leftover review items ------------------------------------------------------------------------------------

def test_sightings_table_drops_the_id_when_it_is_just_the_mac():
    from lanxang.web.devices_pages import render_device_page
    mac_only = device(1, "pixel", sightings=[{"id": 10, "source": "lan", "external_id": "AA-BB-CC-DD-EE-01",
                                              "ip": "192.0.2.5", "mac": "aa:bb:cc:dd:ee:01", "hostname": None,
                                              "detail": {}, "last_seen": "2026-09-30T12:00:00"}])
    html = render_device_page(mac_only, [mac_only])
    assert "<th>ID</th>" not in html and "AA-BB-CC-DD-EE-01" not in html
    own = dict(mac_only["sightings"][0], id=11, source="unifi", external_id="65f0c0ffee")
    both = device(1, "pixel", sightings=[mac_only["sightings"][0], own])
    html = render_device_page(both, [both])
    assert "<th>ID</th>" in html and "<td>65f0c0ffee</td>" in html and "AA-BB-CC-DD-EE-01" not in html


def test_alerts_page_hides_empty_section_headings():
    page = render_alerts_page({"open": [_alert(1, "cert soon")], "watch": [], "resolved": []}, NOW)
    assert "Needs action" in page and "Watching <span" not in page and "Resolved in the last 7 days" not in page
    assert "Nothing watched · nothing resolved this week." in page
    clear = render_alerts_page({"open": [], "watch": [], "resolved": []}, NOW)
    assert "All clear" in clear and "<h2>" not in clear[clear.index('class="alerts"'):clear.index("</main>")]


def test_alert_times_use_the_shared_friendly_time():
    page = render_alerts_page({"open": [_alert(1, "x")], "watch": [], "resolved": [_alert(2, "y")]}, NOW)
    assert re.search(r'since <time datetime="2026-11-19T10:00:00Z" data-when="rel"[^>]*>2 h ago</time>', page)
    assert re.search(r'resolved <time [^>]*>30 min ago</time>, after 90 min', page)


def test_services_page_hides_empty_lanes():
    topo = {"generated_at": "2026-11-19T11:00:00", "host": "box", "lan": [],
            "docker": {"networks": {"bridge": [{"name": "app", "status": "running", "public": [], "ports": [80]}]}}}
    page = render_network_page(topo, [], {"nodes": [], "edges": []})
    assert "Home network only" in page
    assert "From the internet</h2>" not in page and "Background (" not in page
    assert "Nothing reachable from the internet · no background helpers." in page


class Event:
    def __init__(self, created_at, event_type="atlas.device.new"):
        self.created_at, self.event_type, self.source, self.payload = created_at, event_type, "lan", "{}"


def test_activity_groups_by_the_chosen_zone_day(monkeypatch):
    late = datetime(2026, 11, 19, 3)            # 03:00 UTC is still 18 Nov in New York
    events = [Event(late), Event(datetime(2026, 11, 18, 20), "atlas.alert.x")]
    monkeypatch.setattr(render, "DISPLAY", DisplayConfig(time_zone="America/New_York"))
    assert render_history_page(events).count('<section class="day">') == 1
    monkeypatch.setattr(render, "DISPLAY", None)                  # browser: UTC on the server, then DAY_SCRIPT
    html = render_history_page(events)
    assert html.count('<section class="day">') == 2 and '<div id="ev-log">' in html
    assert render.DAY_SCRIPT in html and '!=="browser")return;' in render.DAY_SCRIPT


def test_activity_uses_the_zone_the_browser_reported(monkeypatch):
    monkeypatch.setattr(render, "DISPLAY", None)                  # "this browser"
    events = [Event(datetime(2026, 11, 19, 3)), Event(datetime(2026, 11, 18, 23))]
    html = render_history_page(events, today=date(2026, 11, 18), viewer_zone="America/New_York")
    assert html.count('<section class="day">') == 1 and 'data-zone="America/New_York"' in html
    assert "\u00d72 today, latest" in html                       # both are 18 Nov in New York: one row, counted
    monkeypatch.setattr(render, "DISPLAY", DisplayConfig(time_zone="UTC"))
    assert "data-zone" not in render_history_page(events, viewer_zone="America/New_York")   # a chosen zone wins


def test_the_head_script_reports_the_browser_zone():
    assert 'document.cookie="lanxang-tz="' in render.THEME_SCRIPT
    assert "log.dataset.zone===" in render.DAY_SCRIPT


DAY_HARNESS = r"""
const [script, rows] = JSON.parse(process.argv[1]);
let replaced = false;
const evs = rows.map((iso) => ({iso, querySelector: () => iso ? {getAttribute: () => iso} : null}));
const log = {querySelectorAll: () => Object.assign(evs, {forEach: Array.prototype.forEach}),
             replaceChildren(...sections) { replaced = sections.map((s) => s.kids.map((e) => e.iso)); }};
global.document = {documentElement: {dataset: {tz: "browser"}}, getElementById: () => log,
  createElement: () => ({kids: [], dataset: {}, setAttribute() {}, appendChild(c) { if (c.iso !== undefined) this.kids.push(c); }})};
eval(script);
console.log(JSON.stringify(replaced));
"""


def run_days(rows):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    script = render.DAY_SCRIPT.removeprefix("<script>").removesuffix("</script>")
    return json.loads(subprocess.run(["node", "-e", DAY_HARNESS, json.dumps([script, rows])],
                                     capture_output=True, text=True, check=True).stdout)


def test_day_script_regroups_by_local_day_and_never_drops_rows():
    a, b = "2026-11-19T12:00:00Z", "2026-11-17T12:00:00Z"
    assert run_days([a, a, b]) == [[a, a], [b]]          # every row kept, two days
    assert run_days([a, None, b]) is False               # a row without a time: keep the server's grouping


def test_saving_the_time_zone_reloads_activity():
    assert 'if(document.getElementById("ev-log"))location.reload();' in render.TIME_PREFS_SCRIPT


def test_viewer_zone_cookie_must_name_a_real_zone():
    from types import SimpleNamespace
    from lanxang.web.server import AtlasWebHandler
    zone = lambda cookie: AtlasWebHandler._viewer_zone(SimpleNamespace(headers={"Cookie": cookie}))
    assert zone("lanxang-tz=America%2FNew_York") == "America/New_York"
    assert zone("lanxang-tz=Not%2FA_Zone") is None and zone("lanxang-tz=..%2F..%2Fetc") is None and zone("") is None
