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
    assert '<aside class="side">' in html and 'href="/devices" aria-current="page" title="Network"' in html
    assert 'class="tabs"' in html and 'href="/cabling" aria-current="page">Cabling<' in html
    assert ':root[data-theme="dark"]' in html and "atlasTheme()" in html and "atlas-theme" in html
    assert html.count('class="ic"') >= 8      # every main nav item carries an icon (the collapsed sidebar needs it)
    assert render_page("Setup", "", active="settings").count('class="tabs"') == 0    # no sub-pages, no list


def test_pages_have_an_inline_icon():
    from lanxang.web.login_page import _page
    for html in (render_page("Home", ""), _page("Sign in", "")):
        assert "<link rel=\"icon\" href=\"data:image/svg+xml," in html


def test_light_is_default_system_only_when_chosen():
    """Light whatever the OS prefers: the OS colour scheme counts only under data-theme="system"."""

    html = render_page("Home", "")
    css = html.split("<style>")[1].split("</style>")[0]
    media = css.split("@media (prefers-color-scheme: dark) {")[1].split("\n}")[0]
    assert css.count("prefers-color-scheme") == 1 and ':root[data-theme="system"] {' in media
    assert media.count(":root") == 2 and all('[data-theme="system"]' in line for line in media.splitlines() if ":root" in line)
    assert html.count("color-scheme:dark") == 2 and ':root[data-theme="dark"] {' in html
    for path in (Path(__file__).resolve().parents[1] / "lanxang").rglob("*"):
        if path.suffix in {".py", ".js", ".html", ".css"} and path.name != "render.py":
            assert "prefers-color-scheme" not in path.read_text(), path
