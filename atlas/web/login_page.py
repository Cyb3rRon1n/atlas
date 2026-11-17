"""Sign-in and first-run setup pages: plain HTML forms, no script, no nav."""

from atlas.web.auth import MIN_PASSWORD
from atlas.web.render import FAVICON, PAGE_STYLE, _esc


CARD_STYLE = """
.auth { max-width:360px; margin:12vh auto 0; padding:28px 24px; background:var(--surface);
        border:1px solid var(--line); border-radius:12px; }
.auth h1 { margin:0 0 6px; font-size:1.3rem; }
.auth label { display:block; margin:14px 0 6px; color:var(--muted); font-size:.9rem; }
.auth input { width:100%; box-sizing:border-box; padding:10px 12px; border-radius:8px; font:inherit;
              border:1px solid var(--line); background:var(--surface2); color:var(--text); }
.auth button { margin-top:20px; width:100%; padding:10px 12px; border-radius:8px; border:0; font:inherit;
               font-weight:600; cursor:pointer; background:var(--blue); color:var(--on-accent); }
.auth .error { margin:12px 0 0; color:var(--red); }
.auth .hint { color:var(--muted); font-size:.85rem; margin:8px 0 0; }
"""


def _page(title, body):

    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Atlas - {_esc(title)}</title>{FAVICON}<style>{PAGE_STYLE}{CARD_STYLE}</style></head><body>"
            f"<main class=\"auth\">{body}</main></body></html>")


def render_login_page(error="", next_path="/"):

    return _page("Sign in", (
        "<h1>Sign in to Atlas</h1>"
        "<form method=\"post\" action=\"/login\">"
        f"<input type=\"hidden\" name=\"next\" value=\"{_esc(next_path)}\">"
        "<label for=\"password\">Password</label>"
        "<input id=\"password\" name=\"password\" type=\"password\" autocomplete=\"current-password\" required autofocus>"
        + (f"<p class=\"error\" role=\"alert\">{_esc(error)}</p>" if error else "") +
        "<button type=\"submit\">Sign in</button></form>"
        "<p class=\"hint\">Forgot it? On the host: <code>docker compose exec -it atlas atlas auth password</code></p>"))


def render_setup_page(error=""):

    return _page("Set up", (
        "<h1>Welcome to Atlas</h1>"
        "<p class=\"hint\">Set the admin password. The setup code is in the atlas log "
        "(<code>docker compose logs atlas</code>) or from <code>docker compose exec atlas atlas auth setup-code</code>.</p>"
        "<form method=\"post\" action=\"/setup\">"
        "<label for=\"code\">Setup code</label>"
        "<input id=\"code\" name=\"code\" autocomplete=\"off\" required autofocus>"
        "<label for=\"password\">New password</label>"
        f"<input id=\"password\" name=\"password\" type=\"password\" autocomplete=\"new-password\" minlength=\"{MIN_PASSWORD}\" required>"
        "<label for=\"confirm\">Confirm password</label>"
        f"<input id=\"confirm\" name=\"confirm\" type=\"password\" autocomplete=\"new-password\" minlength=\"{MIN_PASSWORD}\" required>"
        + (f"<p class=\"error\" role=\"alert\">{_esc(error)}</p>" if error else "") +
        "<button type=\"submit\">Save and sign in</button></form>"))
