"""Preferences (header bar, panel, browser-side prefs): markup, CSS hooks and the early head script."""

import json
import re
import shutil
import subprocess

import pytest

from lanxang.web import render
from lanxang.web.render import PAGE_STYLE, THEME_SCRIPT, render_page


def test_header_bar_on_every_page_and_sidebar_theme_button_gone():
    html = render_page("Devices", "<p>x</p>", active="devices")
    assert html.count('class="hbar"') == 2           # page header + phone top bar
    assert 'class="page-head"><h1>Devices</h1><div class="hbar">' in html
    assert html.count('class="icon-btn theme-cycle" onclick="atlasTheme()"') == 2
    assert 'aria-label="Theme: Light. Switch to Dark"' in html
    assert html.count('class="icon-btn prefs-open" aria-haspopup="dialog" aria-controls="prefs"') == 2
    assert "Dark mode" not in html and "Light mode" not in html and "theme-btn" not in html
    for cls in ("t-light", "t-dark", "t-system"):
        assert f'class="{cls}"' in html


def test_sign_out_stays_in_the_sidebar(monkeypatch):
    monkeypatch.setattr(render, "SIGN_OUT", True)
    html = render_page("Home", "")
    side = html.split('<aside class="side">')[1].split("</aside>")[0]
    assert 'action="/logout"' in side and "Sign out" in side


def test_panel_markup_and_aria():
    html = render_page("Home", "")
    panel = html.split('<div id="prefs"')[1].split('<script>')[0]
    assert 'role="dialog" aria-modal="true" aria-labelledby="prefs-title" tabindex="-1" hidden' in panel
    assert '<h2 id="prefs-title">Preferences</h2>' in panel and "data-prefs-close" in panel
    for heading in ("Appearance", "Size &amp; density", "Navigation"):
        assert f"<h3>{heading}</h3>" in panel
    assert "Time" not in panel                        # time & date comes with the server-side prefs
    for pref, values in (("theme", "light dark system"), ("motion", "system on off"), ("contrast", "off on"),
                         ("text", "s m l"), ("density", "comfortable compact"), ("sidebar", "off on")):
        group = panel.split(f'data-pref="{pref}">')[1].split("</div>")[0]
        assert re.findall(r'data-v="(\w+)"', group) == values.split()
        assert group.count('aria-pressed="true"') == 1
        assert f'aria-labelledby="pl-{pref}"' in panel
    assert 'data-v="light" aria-pressed="true"' in panel and 'data-v="m" aria-pressed="true"' in panel
    start = panel.split('<select id="pref-start" data-pref="start">')[1].split("</select>")[0]
    assert re.findall(r'value="(\w+)"', start) == ["home", "devices", "alerts", "map", "servers", "security"]
    assert '<label for="pref-start">Start page</label>' in panel
    # outside .app so the page behind can go inert while it is open
    assert html.index('id="prefs"') > html.index("</aside>") and "app.inert=true" in html


def test_panel_script_traps_focus_escape_closes_and_returns_focus():
    script = render.PREFS_SCRIPT
    assert 'e.key==="Escape"' in script and 'e.key!=="Tab"' in script
    assert "panel.focus()" in script and "opener.focus()" in script
    assert 'localStorage.setItem(key(k),v)' in script and "try{" in script


def test_every_preference_has_a_css_hook():
    for hook in (':root[data-theme="dark"] {', ':root[data-theme="system"] {', ':root[data-contrast="on"] {',
                 ':root[data-theme="dark"][data-contrast="on"] {', ':root[data-theme="system"][data-contrast="on"] {',
                 ':root[data-text="s"] { font-size:87.5%; }', ':root[data-text="l"] { font-size:112.5%; }',
                 ':root[data-density="compact"] :is(th, td)', ':root[data-density="compact"] .card',
                 ':root[data-motion="on"] *', '@media (prefers-reduced-motion: reduce)',
                 ':root:not([data-motion="off"]) *', ':root[data-sidebar="on"] .side .lbl'):
        assert hook in PAGE_STYLE, hook
    assert "animation:none !important; transition:none !important" in PAGE_STYLE


def test_page_text_scales_with_root_font_size():
    """Text size works only if fonts are rem: no px font sizes outside SVG drawings."""

    from pathlib import Path
    for path in (Path(render.__file__).parent).glob("*.py"):
        assert not re.search(r"font-size:\s*\d+(\.\d+)?px", path.read_text()), path.name


def test_high_contrast_text_is_at_least_7_to_1():
    def lum(hex_):
        rgb = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    for tokens in (render.LIGHT_HC, render.DARK_HC):
        t = dict(re.findall(r"--([\w-]+):(#[0-9a-f]{6})", tokens))
        for fg in ("text", "muted", "accent", "ok-text", "warn-text", "bad-text", "red", "green", "orange"):
            for bg in ("bg", "surface", "surface2"):
                assert ratio(t[fg], t[bg]) >= 7, (fg, bg, ratio(t[fg], t[bg]))
        assert ratio(t["on-accent"], t["accent"]) >= 7


def test_collapsed_sidebar_has_toggle_tooltips_and_screen_reader_labels():
    html = render_page("Devices", "", active="devices")
    assert '<button type="button" class="side-toggle" aria-pressed="false" title="Collapse sidebar">' in html
    for _, label, _ in render.NAV:
        assert f'title="{label}">' in html and f'<span class="lbl">{label}</span>' in html
    assert '<nav class="subnav" aria-label="Section">' in html   # section pages stay reachable when collapsed


def test_home_link_skips_the_start_page():
    html = render_page("Devices", "", active="devices")
    assert 'class="brand" href="/?home"' in html and '<a href="/?home" title="Home">' in html


# --- the head script itself, run in node with a fake browser --------------------------------------------------

HARNESS = r"""
const [script, store, path, search, nav, throwing] = JSON.parse(process.argv[1]);
const attrs = {}, dataset = new Proxy({}, {set(o, k, v) { attrs["data-" + k] = v; return true; }});
let replaced = null, rewritten = null;
global.document = {documentElement: {dataset, setAttribute(k, v) { attrs[k] = v; }, getAttribute(k) { return attrs[k] ?? null; }}};
global.localStorage = {getItem(k) { if (throwing) throw new Error("blocked"); return store[k] ?? null; }};
global.location = {pathname: path, search, replace(u) { replaced = u; }};
global.history = {replaceState(a, b, u) { rewritten = u; }};
global.performance = {getEntriesByType() { return [{type: nav}]; }};
global.window = global;
eval(script);
console.log(JSON.stringify({attrs, replaced, rewritten}));
"""


def run_head(store=None, path="/devices", search="", nav="navigate", throwing=False):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    script = THEME_SCRIPT.removeprefix("<script>").removesuffix("</script>")
    out = subprocess.run(["node", "-e", HARNESS, json.dumps([script, store or {}, path, search, nav, throwing])],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_head_script_defaults_when_nothing_is_stored():
    result = run_head()
    assert result == {"attrs": {}, "replaced": None, "rewritten": None}   # light, system motion, M, comfortable


def test_head_script_defaults_when_storage_is_blocked():
    assert run_head(path="/", throwing=True) == {"attrs": {}, "replaced": None, "rewritten": None}


def test_head_script_applies_saved_prefs_and_ignores_junk():
    store = {"atlas-theme": "system", "lanxang-pref-motion": "on", "lanxang-pref-contrast": "on",
             "lanxang-pref-text": "l", "lanxang-pref-density": "compact", "lanxang-pref-sidebar": "on"}
    assert run_head(store)["attrs"] == {"data-theme": "system", "data-motion": "on", "data-contrast": "on",
                                        "data-text": "l", "data-density": "compact", "data-sidebar": "on"}
    assert run_head({"atlas-theme": "dark"})["attrs"] == {"data-theme": "dark"}       # the old key keeps working
    junk = {"atlas-theme": "neon", "lanxang-pref-text": "xl", "lanxang-pref-density": "<b>"}
    assert run_head(junk)["attrs"] == {}


def test_start_page_only_on_a_direct_visit_to_root():
    store = {"lanxang-pref-start": "devices"}
    assert run_head(store, path="/")["replaced"] == "/devices"
    assert run_head({"lanxang-pref-start": "map"}, path="/")["replaced"] == "/cabling"
    assert run_head(store, path="/alerts")["replaced"] is None                  # only /
    assert run_head(store, path="/", nav="reload")["replaced"] is None          # reloading Home stays
    assert run_head(store, path="/", nav="back_forward")["replaced"] is None
    home = run_head(store, path="/", search="?home")                            # the Home link
    assert home["replaced"] is None and home["rewritten"] == "/"
    assert run_head({"lanxang-pref-start": "home"}, path="/")["replaced"] is None
    assert run_head({"lanxang-pref-start": "//evil"}, path="/")["replaced"] is None
