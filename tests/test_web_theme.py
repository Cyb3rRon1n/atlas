import re
from pathlib import Path

from lanxang.web.render import render_page

WEB = Path(__file__).resolve().parents[1] / "lanxang" / "web"


def test_pages_use_theme_tokens_not_raw_colours():
    """Light and dark only work if every page colour is a var(--token); render.py defines the tokens."""

    for path in WEB.glob("*.py"):
        if path.name == "render.py":
            continue
        found = re.findall(r"#[0-9a-fA-F]{6}\b", path.read_text())
        assert not found, f"{path.name}: {found}"


def test_shell_has_side_menu_sub_pages_and_both_themes():
    html = render_page("Cabling", "<p>x</p>", active="cabling")
    assert '<aside class="side">' in html and 'href="/devices" aria-current="page">Network<' in html
    assert 'class="tabs"' in html and 'href="/cabling" aria-current="page">Cabling<' in html
    assert ':root[data-theme="dark"]' in html and "atlasTheme()" in html and "atlas-theme" in html
    assert 'class="to-dark"' in html and "Light mode" in html and html.count('class="ic"') >= 2
    assert render_page("Setup", "", active="settings").count('class="tabs"') == 0    # no sub-pages, no list


def test_pages_have_an_inline_icon():
    from lanxang.web.login_page import _page
    for html in (render_page("Home", ""), _page("Sign in", "")):
        assert "<link rel=\"icon\" href=\"data:image/svg+xml," in html


def test_light_is_default_dark_only_via_data_theme():
    """The OS colour scheme is ignored: dark applies only when the viewer chose it (data-theme=dark)."""

    html = render_page("Home", "")
    assert "prefers-color-scheme" not in html and "matchMedia" not in html
    assert html.count("color-scheme:dark") == 1 and ':root[data-theme="dark"] {' in html
    for path in (Path(__file__).resolve().parents[1] / "lanxang").rglob("*"):
        if path.suffix in {".py", ".js", ".html", ".css"}:
            assert "prefers-color-scheme" not in path.read_text(), path
