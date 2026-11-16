"""
The Setup page (/settings): connect alerts and an AI model from the browser instead of editing atlas.yaml.

Each card is one integration: Test checks the values as typed without saving them (alerts send a real test
message; the AI card only lists models, which costs nothing), Save stores them through atlas.config.local,
Turn off removes them. A field atlas.yaml sets is shown read-only ("set in atlas.yaml") and never written; a
secret the real environment (.env) sets is shown as "set in .env". Secret values are never put in the page.
"""

import json
import os
import re
import urllib.request
from collections import namedtuple

from pydantic import ValidationError

from atlas.config import local
from atlas.config.loader import build_config, load_config
from atlas.web.render import _esc, render_page

Field = namedtuple("Field", "key label kind path secret hint options", defaults=(None, None, "", ()))

CARDS = {
    "ntfy": ("ntfy - phone push", "The quickest way to get alerts on your phone: install the ntfy app, pick a "
             "hard-to-guess topic name and subscribe to it.", [
                 Field("url", "Server", "text", ("notify", "ntfy", "url"), hint="https://ntfy.sh, or your own"),
                 Field("topic", "Topic", "text", ("notify", "ntfy", "topic")),
                 Field("token", "Access token (only for a protected topic)", "secret", ("notify", "ntfy", "token"),
                       "ATLAS_NTFY_TOKEN")]),
    "webhooks": ("Discord, Slack or a webhook", "Paste a Discord or Slack webhook URL, or any URL that accepts "
                 "JSON. One per line.", [
                     Field("urls", "Webhook URLs", "lines", ("notify", "webhooks"), "ATLAS_WEBHOOK_")]),
    "email": ("Email", "Alerts by email through any SMTP server (your mail provider's, with an app password).", [
        Field("host", "SMTP server", "text", ("notify", "email", "host"), hint="smtp.example.org"),
        Field("port", "Port", "number", ("notify", "email", "port"), hint="587, or 465 for TLS"),
        Field("starttls", "Use STARTTLS (port 587)", "bool", ("notify", "email", "starttls")),
        Field("user", "Username", "text", ("notify", "email", "user")),
        Field("password", "Password", "secret", ("notify", "email", "password"), "ATLAS_SMTP_PASSWORD"),
        Field("sender", "From address (blank = username)", "text", ("notify", "email", "sender")),
        Field("to", "Send to (comma separated)", "list", ("notify", "email", "to"))]),
    "ai": ("AI assistant", "Optional: powers Chat and the daily check-up. Ollama runs on your own hardware; "
           "Claude needs an Anthropic API key.", [
               Field("provider", "Provider", "select", ("intelligence", "provider"),
                     options=("none", "ollama", "anthropic")),
               Field("ollama_host", "Ollama address", "text", ("intelligence", "ollama_host"),
                     hint="http://192.168.1.10:11434"),
               Field("model", "Model", "text", ("intelligence", "model"), hint="qwen3:8b or claude-opus-5"),
               Field("api_key", "Anthropic API key", "secret", None, "ANTHROPIC_API_KEY")]),
}

ACTIONS = re.compile(r"^/api/settings/([a-z]+)/(test|save|off)$")
TEST_TEXT = "**✅ Test alert from Atlas**\nIf you can read this, alerts reach you here."


def _get(data, path):

    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]

    return data


def _put(settings, path, value):
    """Set settings[path] = value in place; None marks the setting for removal when saved."""

    node = settings
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _from_env(name):
    """A secret the real environment sets - .env wins over the Setup page, so the page can't change it."""

    return bool(name) and bool(os.environ.get(name)) and name not in local._APPLIED


def _locked(field):

    return bool(field.path) and local.locked(field.path)


def _webhook_names():

    return sorted((n for n in local.secret_names() if n.startswith("ATLAS_WEBHOOK_")),
                  key=lambda n: int(n.rsplit("_", 1)[1]) if n.rsplit("_", 1)[1].isdigit() else 0)


def _changes(card, body, off=False):
    """(settings patch, secrets) a Save (or Turn off) of this card would write; locked fields are left alone."""

    settings, secrets = {}, {}
    for field in CARDS[card][2]:
        if _locked(field) or (field.kind == "secret" and _from_env(field.secret)):
            continue
        value = None if off else body.get(field.key)
        if field.kind == "lines":
            old = _webhook_names()
            if off or (value is not None and str(value).strip()):
                urls = [] if off else [u.strip() for u in str(value).splitlines() if u.strip()]
                for url in urls:
                    if not re.match(r"^https?://", url):
                        raise ValueError(f"not a web address: {url[:40]}")
                names = [f"{field.secret}{i}" for i in range(1, len(urls) + 1)]
                secrets.update({name: None for name in old}, **dict(zip(names, urls)))
                _put(settings, field.path, ["${%s}" % n for n in names] or None)
            continue
        if field.kind == "secret":
            if off:
                secrets[field.secret] = None
                if field.path:
                    _put(settings, field.path, None)
            elif value:
                secrets[field.secret] = str(value)
                if field.path:
                    _put(settings, field.path, "${%s}" % field.secret)
            continue
        if value is None and not off:
            continue
        if off:
            value = None
        elif field.kind == "bool":
            value = bool(value)
        elif field.kind == "number":
            if str(value).strip() == "":
                value = None
            elif not str(value).strip().isdigit():
                raise ValueError(f"{field.label} must be a number")
            else:
                value = int(value)
        elif field.kind == "list":
            value = [part.strip() for part in str(value).split(",") if part.strip()] or None
        else:
            value = str(value).strip() or None
            if field.kind == "select" and value not in field.options:
                raise ValueError(f"{field.label} must be one of: {', '.join(field.options)}")
        _put(settings, field.path, value)      # None (an emptied field) removes it: the default applies

    return settings, secrets


def _candidate(card, body):
    """The config these unsaved values would give, with their secrets visible only to this check."""

    settings, secrets = _changes(card, body)
    environ = {**os.environ, **{name: value for name, value in secrets.items() if value}}
    for name, value in secrets.items():
        if value is None:
            environ.pop(name, None)

    return build_config(local._merge(local.read_settings(), settings), environ), environ


def _test_ai(config, environ):

    intelligence = config.intelligence
    if intelligence.provider == "none":
        return False, "No AI selected - choose ollama or anthropic first."
    if intelligence.provider == "ollama":
        url = intelligence.ollama_host.rstrip("/") + "/api/tags"
        with urllib.request.urlopen(url, timeout=8) as response:
            models = [m.get("name", "") for m in json.load(response).get("models", [])]
        if not models:
            return False, "Ollama answered but has no models - run: ollama pull qwen3:8b"
        if intelligence.model not in models and f"{intelligence.model}:latest" not in models:
            return False, f"Ollama is reachable, but {intelligence.model or 'no model'} isn't installed. " \
                          f"It has: {', '.join(models[:8])}"
        return True, f"Connected to Ollama: {intelligence.model} is installed ({len(models)} models)."

    import anthropic

    key = environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return False, "Enter an Anthropic API key."
    try:
        ids = [model.id for model in anthropic.Anthropic(api_key=key).models.list(limit=100, timeout=10).data]
    except anthropic.AuthenticationError:
        return False, "Anthropic refused the key - check it, or create a new one in the Anthropic Console."
    if intelligence.model and intelligence.model not in ids:
        return False, f"The key works, but model {intelligence.model} isn't available to it. " \
                      f"Available: {', '.join(ids[:6])}"
    return True, "The key works" + (f" and {intelligence.model} is available." if intelligence.model else ".")


def _test(card, body):

    from atlas import notify

    config, environ = _candidate(card, body)
    alerts = config.notify
    if card == "ntfy":
        if not (alerts.ntfy.url and alerts.ntfy.topic):
            return False, "Enter the server and topic."
        notify.send_ntfy(alerts.ntfy, TEST_TEXT)
        return True, f"Sent - it should appear on every device subscribed to {alerts.ntfy.topic}."
    if card == "webhooks":
        if not alerts.webhooks:
            return False, "Enter at least one webhook URL."
        for url in alerts.webhooks:
            notify.send_webhook(url, TEST_TEXT)
        return True, f"Sent to {len(alerts.webhooks)} webhook{'s' * (len(alerts.webhooks) != 1)}."
    if card == "email":
        if not (alerts.email.host and alerts.email.to):
            return False, "Enter the SMTP server and at least one address to send to."
        notify.send_email(alerts.email, TEST_TEXT)
        return True, f"Sent to {', '.join(alerts.email.to)} - check the inbox (and spam)."

    return _test_ai(config, environ)


def handle_post(path, body):
    """(status, payload) for POST /api/settings/<card>/<test|save|off>, or None when the path isn't ours."""

    match = ACTIONS.match(path)
    if not match:
        return None
    card, action = match.groups()
    if card not in CARDS:
        return 404, {"error": "no such setting"}
    body = body if isinstance(body, dict) else {}

    try:
        if action == "test":
            try:
                ok, message = _test(card, body)
            except ValueError:
                raise
            except Exception as error:      # couldn't reach it: say why, plainly
                ok, message = False, f"Couldn't connect: {getattr(error, 'reason', None) or error}"
            return (200 if ok else 400), ({"ok": True, "message": message} if ok else {"error": message})
        settings, secrets = _changes(card, body, off=action == "off")
        build_config(local._merge(local.read_settings(), settings),
                     {**os.environ, **{name: value for name, value in secrets.items() if value}})
    except ValidationError as error:
        problem = error.errors()[0]
        return 400, {"error": f"{'.'.join(map(str, problem['loc']))}: {problem['msg']}"}
    except ValueError as error:
        return 400, {"error": str(error)}

    if secrets:
        local.save_secrets(secrets)
    if settings:
        local.save_settings(settings)

    return 200, {"ok": True, "message": "Turned off." if action == "off" else "Saved."}


def _field_html(card, field, config):

    name = f"{card}-{field.key}"
    locked = _locked(field)
    note = ' <span class="lock">set in atlas.yaml</span>' if locked else ""
    disabled = " disabled" if locked else ""
    value = _get(config.model_dump(), field.path) if field.path else None

    if field.kind == "secret":
        env = _from_env(field.secret)
        saved = field.secret in local.secret_names() or env or (locked and value)
        placeholder = "set in .env" if env else "saved - leave blank to keep it" if saved else "not set"
        return (f'<label for="{name}">{_esc(field.label)}{note}</label>'
                f'<input id="{name}" name="{field.key}" type="password" autocomplete="new-password" '
                f'placeholder="{_esc(placeholder)}"{" disabled" if env or locked else ""}>')
    if field.kind == "lines":
        count = len(value or [])
        placeholder = (f"{count} saved - paste new ones to replace them" if count else "https://discord.com/api/webhooks/...")
        return (f'<label for="{name}">{_esc(field.label)}{note}</label>'
                f'<textarea id="{name}" name="{field.key}" placeholder="{_esc(placeholder)}"{disabled}></textarea>')
    if field.kind == "bool":
        return (f'<label><input type="checkbox" name="{field.key}"{" checked" if value else ""}{disabled}> '
                f'{_esc(field.label)}{note}</label>')
    if field.kind == "select":
        options = "".join(f'<option{" selected" if option == value else ""}>{_esc(option)}</option>'
                          for option in field.options)
        return f'<label for="{name}">{_esc(field.label)}{note}</label><select id="{name}" name="{field.key}"{disabled}>{options}</select>'
    shown = ", ".join(value or []) if field.kind == "list" else "" if value is None else value
    kind = "number" if field.kind == "number" else "text"

    return (f'<label for="{name}">{_esc(field.label)}{note}</label>'
            f'<input id="{name}" name="{field.key}" type="{kind}" value="{_esc(shown)}" '
            f'placeholder="{_esc(field.hint)}" size="40"{disabled}>')


def _on(card, config):

    alerts = config.notify
    return {"ntfy": bool(alerts.ntfy.url and alerts.ntfy.topic), "webhooks": bool(alerts.webhooks),
            "email": bool(alerts.email.host and alerts.email.to),
            "ai": config.intelligence.provider != "none"}[card]


SCRIPT = """
<script>
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-act]");
  if (!button) return;
  event.preventDefault();
  const form = button.closest("form"), status = form.querySelector(".status");
  const body = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    body[el.name] = el.type === "checkbox" ? el.checked : el.value;
  }
  status.className = "status muted"; status.textContent = button.dataset.act === "test" ? "Testing..." : "Saving...";
  try {
    const response = await fetch("/api/settings/" + form.dataset.card + "/" + button.dataset.act, {method: "POST",
      credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json().catch(() => ({}));
    status.className = "status " + (response.ok ? "ok" : "bad");
    status.textContent = response.ok ? data.message : (data.error || ("Failed: " + response.status +
      (response.status === 401 || response.status === 403 ? " (session expired? reload the page)" : "")));
    if (response.ok && button.dataset.act !== "test") setTimeout(() => location.reload(), 900);
  } catch (error) { status.className = "status bad"; status.textContent = "Request failed: " + error; }
});
</script>
"""

STYLE = """<style>
.setup { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:1rem; }
.setup form input[type=text], .setup form input[type=number], .setup form input[type=password],
.setup form select, .setup form textarea { width:100%; box-sizing:border-box; }
.setup .badge { font-size:.75rem; border-radius:999px; padding:1px 8px; margin-left:.4rem; vertical-align:middle;
  border:1px solid #30363d; color:#8b949e; }
.setup .badge.on { border-color:#238636; color:#3fb950; }
.setup .status { min-height:1.5em; margin:.6rem 0 .2rem; }
.setup .status.ok { color:#3fb950; } .setup .status.bad { color:#f85149; }
.setup .lock { font-size:.75rem; border:1px solid #30363d; border-radius:999px; padding:0 6px; margin-left:.3rem; }
.setup input:disabled, .setup select:disabled, .setup textarea:disabled { opacity:.55; cursor:not-allowed; }
.setup .buttons { display:flex; gap:.5rem; flex-wrap:wrap; }
</style>"""


def render_settings_page():

    config = load_config()
    cards = []
    for card, (title, intro, fields) in CARDS.items():
        on = _on(card, config)
        cards.append(
            f'<section class="card"><h2>{_esc(title)}<span class="badge{" on" if on else ""}">{"on" if on else "off"}'
            f'</span></h2><p class="muted">{_esc(intro)}</p><form data-card="{card}">'
            + "".join(_field_html(card, field, config) for field in fields) +
            '<p class="status muted" role="status"></p><div class="buttons">'
            f'<button data-act="test">{"Send test" if card != "ai" else "Test"}</button>'
            '<button class="primary" data-act="save">Save</button>'
            + ('<button data-act="off">Turn off</button>' if on else "") + '</div></form></section>')

    body = (STYLE + '<p class="muted">Changes here take effect within a minute, no restart. Anything set in '
            'atlas.yaml or .env stays read-only here - edit it there. Passwords and keys are stored privately '
            'on this machine and never shown again.</p><div class="setup">' + "".join(cards) + "</div>" + SCRIPT)

    return render_page("Setup", body, active="settings")
