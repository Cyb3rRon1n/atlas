import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from atlas.config import local
from atlas.config.loader import load_config
from atlas.web import settings_page
from atlas.web.settings_page import handle_post, render_settings_page


@pytest.fixture
def env(isolated_cwd, monkeypatch):
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("ATLAS_", "ANTHROPIC_"))}
    monkeypatch.setattr(os, "environ", environ)
    monkeypatch.setattr(local, "_APPLIED", set())
    return environ


@pytest.fixture
def receiver():
    """A local HTTP server standing in for ntfy / a webhook / Ollama: records what it was sent."""

    got = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append({"path": self.path, "auth": self.headers.get("Authorization"),
                        "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            self.send_response(200); self.end_headers()

        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({"models": [{"name": "qwen3:8b"}, {"name": "llama3.1:latest"}]}).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", got
    server.shutdown()


def test_ntfy_test_sends_without_saving_then_save_and_turn_off(env, receiver, isolated_cwd):
    url, got = receiver
    body = {"url": url, "topic": "atlas-home", "token": "tk_secret"}

    status, data = handle_post("/api/settings/ntfy/test", body)
    assert status == 200 and "atlas-home" in data["message"]
    assert got[0]["body"]["topic"] == "atlas-home" and got[0]["auth"] == "Bearer tk_secret"
    assert local.read_settings() == {} and local.secret_names() == set()          # a test saves nothing

    assert handle_post("/api/settings/ntfy/save", body)[0] == 200
    config = load_config()
    assert config.notify.ntfy.topic == "atlas-home" and config.notify.ntfy.token == "tk_secret"
    assert "tk_secret" not in (isolated_cwd / "inventory" / "settings.yaml").read_text()
    assert stat.S_IMODE((isolated_cwd / "inventory" / "secrets.json").stat().st_mode) == 0o600

    page = render_settings_page()
    assert "tk_secret" not in page and "saved - leave blank to keep it" in page and 'class="badge on"' in page

    assert handle_post("/api/settings/ntfy/save", {"url": url, "topic": "renamed", "token": ""})[0] == 200
    assert load_config().notify.ntfy.token == "tk_secret"                         # blank keeps the secret

    assert handle_post("/api/settings/ntfy/off", {})[0] == 200
    assert load_config().notify.ntfy.topic == "" and local.secret_names() == set()


def test_atlas_yaml_fields_are_read_only_and_never_written(env, isolated_cwd):
    (isolated_cwd / "atlas.yaml").write_text("notify:\n  ntfy:\n    topic: mine\n")
    handle_post("/api/settings/ntfy/save", {"url": "https://ntfy.example.org", "topic": "theirs"})
    assert load_config().notify.ntfy.topic == "mine"
    assert local.read_settings() == {"notify": {"ntfy": {"url": "https://ntfy.example.org"}}}
    page = render_settings_page()
    assert 'name="topic" type="text" value="mine"' in page and "set in atlas.yaml" in page


def test_env_secret_wins_and_an_empty_one_does_not_count(env):
    env["ANTHROPIC_API_KEY"] = ""                                   # compose's ${ANTHROPIC_API_KEY:-}
    assert "set in .env" not in render_settings_page()
    handle_post("/api/settings/ai/save", {"provider": "anthropic", "model": "claude-opus-5", "api_key": "sk-web"})
    load_config()
    assert env["ANTHROPIC_API_KEY"] == "sk-web"
    env["ANTHROPIC_API_KEY"] = "sk-dotenv"
    local._APPLIED.discard("ANTHROPIC_API_KEY")
    assert "set in .env" in render_settings_page()


def test_webhooks_are_secrets_and_get_a_test(env, receiver, isolated_cwd):
    url, got = receiver
    hooks = f"{url}/one\n{url}/two\n"
    assert handle_post("/api/settings/webhooks/test", {"urls": hooks})[0] == 200
    assert [g["path"] for g in got] == ["/one", "/two"]
    handle_post("/api/settings/webhooks/save", {"urls": hooks})
    assert load_config().notify.webhooks == [f"{url}/one", f"{url}/two"]
    assert url not in (isolated_cwd / "inventory" / "settings.yaml").read_text()
    handle_post("/api/settings/webhooks/save", {"urls": f"{url}/three"})
    assert load_config().notify.webhooks == [f"{url}/three"] and local.secret_names() == {"ATLAS_WEBHOOK_1"}
    assert handle_post("/api/settings/webhooks/save", {"urls": "not a url"})[0] == 400


def test_ollama_test_checks_the_model_is_installed(env, receiver):
    url, _ = receiver
    ok = handle_post("/api/settings/ai/test", {"provider": "ollama", "ollama_host": url, "model": "qwen3:8b"})
    assert ok[0] == 200 and "qwen3:8b is installed" in ok[1]["message"]
    assert handle_post("/api/settings/ai/test", {"provider": "ollama", "ollama_host": url, "model": "llama3.1"})[0] == 200
    missing = handle_post("/api/settings/ai/test", {"provider": "ollama", "ollama_host": url, "model": "mistral"})
    assert missing[0] == 400 and "isn't installed" in missing[1]["error"] and "qwen3:8b" in missing[1]["error"]
    down = handle_post("/api/settings/ai/test", {"provider": "ollama", "ollama_host": "http://127.0.0.1:9", "model": "x"})
    assert down[0] == 400 and down[1]["error"].startswith("Couldn't connect")


def test_bad_input_is_refused_and_nothing_saved(env):
    assert handle_post("/api/settings/email/save", {"host": "smtp.example.org", "port": "abc"})[0] == 400
    assert handle_post("/api/settings/ai/save", {"provider": "gpt"})[0] == 400
    assert handle_post("/api/settings/nope/save", {})[0] == 404
    assert handle_post("/api/elsewhere", {}) is None
    assert local.read_settings() == {}


def test_email_save_types(env):
    handle_post("/api/settings/email/save", {"host": "smtp.example.org", "port": "465", "starttls": False,
                                             "user": "me@example.org", "password": "pw", "to": "a@example.org, b@example.org"})
    email = load_config().notify.email
    assert (email.port, email.starttls, email.to, email.password) == (465, False, ["a@example.org", "b@example.org"], "pw")


def test_anthropic_key_check_lists_models_only(env, monkeypatch):
    import anthropic

    class Models:
        def __init__(self, key):
            self.key = key

        def list(self, **kwargs):
            if self.key != "sk-good":
                raise anthropic.AuthenticationError("bad", response=__import__("httpx2").Response(
                    401, request=__import__("httpx2").Request("GET", "https://api.anthropic.com/v1/models")), body=None)
            return type("Page", (), {"data": [type("M", (), {"id": "claude-opus-5"})()]})()

    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key: type("C", (), {"models": Models(api_key)})())
    good = handle_post("/api/settings/ai/test", {"provider": "anthropic", "model": "claude-opus-5", "api_key": "sk-good"})
    assert good[0] == 200 and "claude-opus-5 is available" in good[1]["message"]
    bad = handle_post("/api/settings/ai/test", {"provider": "anthropic", "model": "claude-opus-5", "api_key": "sk-bad"})
    assert bad[0] == 400 and "refused the key" in bad[1]["error"]
    assert local.secret_names() == set()
