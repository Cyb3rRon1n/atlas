import re
from pathlib import Path

from atlas.web.render import render_page

WEB = Path(__file__).resolve().parents[1] / "atlas" / "web"


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
    assert "prefers-color-scheme: dark" in html and ':root[data-theme="dark"]' in html and "atlasTheme()" in html
    assert 'class="to-dark"' in html and "Light mode" in html and html.count('class="ic"') >= 2
    assert render_page("Setup", "", active="settings").count('class="tabs"') == 0    # no sub-pages, no list
