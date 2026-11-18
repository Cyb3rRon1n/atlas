import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lanxang.config import local
from lanxang.config.loader import load_config
from lanxang.web import settings_page
from lanxang.web.settings_page import handle_post, render_settings_page


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
    assert load_config().notify.webhooks == [f"{url}/three"] and local.secret_names() == {"LANXANG_WEBHOOK_1"}
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


SWITCH = {"name": "core switch", "host": "192.0.2.2", "snmp_user": "atlas", "priv": "des",
          "auth": "auth-pass", "priv_pass": "priv-pass"}


def test_switches_add_update_remove_and_turn_wiring_on(env, isolated_cwd):
    assert handle_post("/api/settings/switches/save", {**SWITCH, "auth": ""})[0] == 400     # a new switch needs both
    assert handle_post("/api/settings/switches/save", SWITCH)[0] == 200
    assert handle_post("/api/settings/switches/save", {**SWITCH, "name": "spare", "host": "192.0.2.3"})[0] == 200
    # updating by name keeps the saved passphrases when left blank
    assert handle_post("/api/settings/switches/save", {**SWITCH, "host": "192.0.2.9", "auth": "", "priv_pass": ""})[0] == 200

    config = load_config()
    assert config.wiring.enabled is True
    assert [(s.name, s.host, s.priv) for s in config.wiring.switches] == [("spare", "192.0.2.3", "des"),
                                                                         ("core switch", "192.0.2.9", "des")]
    assert env["LANXANG_SNMP_CORE_SWITCH_AUTH"] == "auth-pass" and env["LANXANG_SNMP_CORE_SWITCH_PRIV"] == "priv-pass"
    assert "pass" not in (isolated_cwd / "inventory" / "settings.yaml").read_text()
    page = render_settings_page()
    assert "core switch" in page and "auth-pass" not in page and "Remove this switch" in page

    handle_post("/api/settings/switches/off", {"name": "spare"})
    handle_post("/api/settings/switches/off", {"name": "core switch"})
    assert local.read_settings() == {} and local.secret_names() == set()      # last one out turns the map off


def test_switches_in_atlas_yaml_lock_the_card(env, isolated_cwd):
    (isolated_cwd / "atlas.yaml").write_text("wiring:\n  switches:\n    - name: core\n      host: 192.0.2.2\n")
    status, data = handle_post("/api/settings/switches/save", SWITCH)
    assert status == 400 and "atlas.yaml" in data["error"] and local.read_settings() == {}
    assert "(from atlas.yaml)" in render_settings_page()
    assert "No switch named core switch - names: core" in handle_post("/api/settings/switches/test", SWITCH)[1]["error"]


def test_switch_test_makes_one_read_only_snmp_request(env, monkeypatch):
    from lanxang.wiring import snmp

    calls = []

    def run(argv, **kwargs):
        conf = open(kwargs["env"]["SNMPCONFPATH"] + "/snmp.conf").read()
        calls.append((argv, conf))
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": '"core"\n"SG300-28 28-Port Gigabit"\n'})()

    probe = snmp.probe_switch
    monkeypatch.setattr(snmp, "probe_switch", lambda switch, environ, timeout: probe(
        switch, environ, timeout, run=run, which=lambda tool: f"/usr/bin/{tool}"))
    status, data = handle_post("/api/settings/switches/test", SWITCH)
    assert status == 200 and data["message"] == "Connected to core: SG300-28 28-Port Gigabit"
    (argv, conf), = calls
    assert argv[0] == "/usr/bin/snmpget" and "auth-pass" not in " ".join(argv)    # passphrases never in argv
    assert "defPrivType DES" in conf and "defAuthPassphrase auth-pass" in conf
    assert local.read_settings() == {} and local.secret_names() == set()


def test_unifi_test_signs_in_and_counts_devices(env, monkeypatch):
    from lanxang.wiring import WiringError, unifi

    seen = {}

    def session(config, environ, timeout, opener_factory, read):
        seen.update(url=config.url, user=environ["LANXANG_UNIFI_USER"])
        return read(lambda path: [{"mac": "a"}, {"mac": "b"}] if path == "stat/device" else [])

    monkeypatch.setattr(unifi, "_session", session)
    body = {"url": "https://192.0.2.1", "site": "", "verify_ssl": False, "user": "viewer", "password": "pw"}
    status, data = handle_post("/api/settings/unifi/test", body)
    assert status == 200 and "2 UniFi devices" in data["message"] and seen["user"] == "viewer"

    def refused(*args):
        raise WiringError("UniFi login refused - check LANXANG_UNIFI_USER/PASS (a local, read-only account)")

    monkeypatch.setattr(unifi, "_session", refused)
    assert handle_post("/api/settings/unifi/test", body)[1]["error"].startswith("UniFi login refused")

    assert handle_post("/api/settings/unifi/save", body)[0] == 200
    config = load_config()
    assert config.wiring.enabled and config.wiring.unifi.enabled and config.wiring.unifi.site == "default"
    handle_post("/api/settings/unifi/off", {})
    assert local.read_settings() == {} and local.secret_names() == set()


def test_proxmox_test_reads_version_and_nodes(env, monkeypatch):
    import lanxang.proxmox.client as client

    class Api:
        version = type("V", (), {"get": staticmethod(lambda: {"version": "8.4.1"})})()
        nodes = type("N", (), {"get": staticmethod(lambda: [{"node": "pve"}])})()

    got = {}
    monkeypatch.setattr(client, "connect", lambda host, user, **kw: got.update(host=host, **kw) or Api())
    body = {"host": "192.0.2.10", "user": "atlas@pve", "token_name": "atlas", "token_value": "uuid-secret",
            "verify_ssl": False}
    status, data = handle_post("/api/settings/proxmox/test", body)
    assert status == 200 and data["message"] == "Connected: Proxmox VE 8.4.1, 1 node."
    assert got["token_value"] == "uuid-secret"

    assert handle_post("/api/settings/proxmox/save", body)[0] == 200
    config = load_config()
    assert config.proxmox.enabled and config.proxmox.token_value == "uuid-secret"
    assert "uuid-secret" not in render_settings_page()


def test_network_test_errors_are_plain_words(env, monkeypatch):
    import lanxang.proxmox.client as client
    from requests.exceptions import ConnectionError as Refused

    from lanxang.config.models import WiringSwitch
    from lanxang.wiring.snmp import _failure

    switch = WiringSwitch(name="lab", host="192.0.2.2", priv="des")
    timeout = type("R", (), {"stderr": "snmpget: Timeout\n"})()
    assert str(_failure(switch, timeout)).startswith("lab: no answer from 192.0.2.2")
    assert "(DES) doesn't match" in str(_failure(switch, type("R", (), {"stderr": "Decryption error"})()))
    assert str(_failure(switch, type("R", (), {"stderr": "odd thing\nmore"})())) == "lab: odd thing"

    def down():
        raise Refused("HTTPSConnectionPool(host='192.0.2.1', port=8006): Max retries exceeded")

    api = type("A", (), {"version": type("V", (), {"get": staticmethod(down)})()})()
    monkeypatch.setattr(client, "connect", lambda *a, **k: api)
    body = {"host": "192.0.2.1", "user": "atlas@pve", "token_name": "t", "token_value": "x"}
    status, data = handle_post("/api/settings/proxmox/test", body)
    assert status == 400 and data["error"] == "No answer from Proxmox at 192.0.2.1:8006 - check the host and that it's on."


def test_snmp_v2c_switch_saves_a_community_and_drops_v3_secrets(env, isolated_cwd):
    assert handle_post("/api/settings/switches/save", SWITCH)[0] == 200
    v2 = {"name": "core switch", "host": "192.0.2.9", "version": "2c", "community": ""}
    assert handle_post("/api/settings/switches/save", v2)[1]["error"] == "Enter the read-only community."
    assert handle_post("/api/settings/switches/save", {**v2, "community": "ro-community"})[0] == 200

    switch = load_config().wiring.switches[0]
    assert (switch.version, switch.host) == ("2c", "192.0.2.9")
    assert local.secret_names() == {"LANXANG_SNMP_CORE_SWITCH_COMMUNITY"}          # the v3 passphrases are gone
    page = render_settings_page()
    assert "SNMPv2c (community)" in page and "ro-community" not in page


def test_snmp_session_file_for_each_version(tmp_path):
    from lanxang.config.models import WiringSwitch
    from lanxang.wiring import WiringError
    from lanxang.wiring.snmp import _snmp

    def conf(switch, env):
        with _snmp(switch, env, lambda tool: "/usr/bin/" + tool) as (_, child):
            return open(child["SNMPCONFPATH"] + "/snmp.conf").read()

    v2 = WiringSwitch(name="nas", host="192.0.2.5", version="2c")
    assert conf(v2, {"LANXANG_SNMP_NAS_COMMUNITY": "ro"}) == "defVersion 2c\ndefCommunity ro\n"
    with pytest.raises(WiringError, match="COMMUNITY"):
        conf(v2, {})
    v3 = conf(WiringSwitch(name="sw", host="192.0.2.2"), {"LANXANG_SNMP_SW_AUTH": "a" * 8, "LANXANG_SNMP_SW_PRIV": "p" * 8})
    assert v3.startswith("defVersion 3\n") and "defPrivType AES" in v3


def test_gear_chooser_shows_matching_cards_and_saves(env, isolated_cwd):
    page = render_settings_page()
    assert "What's on your network?" in page
    assert '<section class="card" id="proxmox" hidden>' in page          # nothing ticked or found yet
    assert '<section class="card" id="ntfy">' in page                    # alerts always show

    assert handle_post("/api/settings/gear/save", {"gear": ["proxmox", "plain"]}) == (200, {"ok": True})
    assert handle_post("/api/settings/gear/save", {"gear": ["toaster"]})[0] == 400
    page = render_settings_page()
    assert '<section class="card" id="proxmox">' in page and '<section class="card" id="unifi" hidden>' in page
    assert 'value="proxmox" data-cards="proxmox" checked' in page

    handle_post("/api/settings/switches/save", SWITCH)                    # a configured card always shows
    assert '<section class="card" id="switches">' in render_settings_page()
