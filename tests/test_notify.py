"""Alert channels against real local servers (HTTP + SMTP), not mocks of urllib/smtplib."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lanxang import notify
from lanxang.config.models import EmailNotifyConfig, NotifyConfig, NtfyNotifyConfig

TEXT = "**🆕 New device on the network**\n• **Pixel-7** (192.0.2.8)\n\nTriage them in atlas."


@pytest.fixture
def receiver():
    got = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            got.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": json.loads(body)})
            self.send_response(500 if self.path == "/fail" else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", got
    httpd.shutdown()
    httpd.server_close()


def test_nothing_configured():
    assert not notify.configured(NotifyConfig())
    assert notify.send(NotifyConfig(), TEXT) == (False, "no alert channels set (notify: in atlas.yaml)")


def test_ntfy_gets_title_markdown_and_token_from_env(receiver, monkeypatch):
    base, got = receiver
    monkeypatch.setenv("LANXANG_NTFY_TOKEN", "tk_secret")

    assert notify.send(NotifyConfig(ntfy=NtfyNotifyConfig(url=base + "/", topic="homelab")), TEXT) == (True, "")
    body = got[0]["body"]
    assert got[0]["auth"] == "Bearer tk_secret"
    assert body["topic"] == "homelab" and body["title"] == "🆕 New device on the network" and body["markdown"]
    assert body["message"].startswith("• **Pixel-7**")


def test_webhook_shapes():
    assert notify.webhook_payload("https://discord.com/api/webhooks/1/x", TEXT) == {"content": TEXT}
    assert notify.webhook_payload("https://hooks.slack.com/services/x", TEXT)["text"].startswith("*🆕 New device")
    plain = notify.webhook_payload("http://ha.local/api/webhook/atlas", TEXT)
    assert plain["title"] == "🆕 New device on the network" and "**" not in plain["text"]


def test_one_failing_channel_does_not_stop_the_others(receiver):
    base, got = receiver
    config = NotifyConfig(webhooks=[base + "/fail", base + "/ok"])

    results = notify.send_each(config, TEXT)
    assert [(name, ok) for name, ok, _ in results] == [("webhook", False), ("webhook", True)]
    ok, error = notify.send(config, TEXT)
    assert ok and "500" in error
    assert [g["path"] for g in got] == ["/fail", "/ok", "/fail", "/ok"]


def test_unreachable_channel_is_reported_not_raised():
    port = socket.socket(); port.bind(("127.0.0.1", 0)); dead = port.getsockname()[1]; port.close()
    ok, error = notify.send(NotifyConfig(webhooks=[f"http://127.0.0.1:{dead}/"]), TEXT)
    assert not ok and error.startswith("webhook:")


def test_email_over_a_real_smtp_conversation(monkeypatch):
    received = {}
    server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1)

    def smtp():   # just enough SMTP to accept one message
        conn, _ = server.accept()
        f = conn.makefile("rwb")
        say = lambda line: (f.write(line.encode() + b"\r\n"), f.flush())
        say("220 test")
        data = []
        while True:
            line = f.readline().decode().rstrip("\r\n")
            cmd = line.upper()
            if cmd.startswith("EHLO"):
                say("250-test"); say("250 AUTH PLAIN")
            elif cmd.startswith("AUTH"):
                received["auth"] = line; say("235 ok")
            elif cmd == "DATA":
                say("354 go")
                while (l := f.readline().decode()) != ".\r\n":
                    data.append(l)
                received["data"] = "".join(data); say("250 queued")
            elif cmd == "QUIT":
                say("221 bye"); break
            else:
                say("250 ok")
        conn.close()

    threading.Thread(target=smtp, daemon=True).start()
    monkeypatch.setenv("LANXANG_SMTP_PASSWORD", "pw")
    config = NotifyConfig(email=EmailNotifyConfig(host="127.0.0.1", port=server.getsockname()[1], starttls=False,
                                                  user="atlas@example.com", to=["me@example.com"]))

    assert notify.send(config, TEXT) == (True, "")
    assert received["auth"].startswith("AUTH PLAIN")
    assert "Subject: Atlas: =?utf-8?" in received["data"] or "Subject: Atlas:" in received["data"]
    assert "To: me@example.com" in received["data"] and "**" not in received["data"]
    server.close()


def test_apprise_missing_is_a_clear_error(monkeypatch):
    import builtins
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__",
                        lambda name, *a, **k: (_ for _ in ()).throw(ImportError()) if name == "apprise" else real(name, *a, **k))
    ok, error = notify.send(NotifyConfig(apprise=["json://localhost"]), TEXT)
    assert not ok and "apprise isn't installed" in error


def test_cli_notify_test(receiver, isolated_cwd):
    from typer.testing import CliRunner
    from lanxang.cli.main import app
    base, got = receiver
    runner = CliRunner()

    assert runner.invoke(app, ["notify", "test"]).exit_code == 1          # nothing set
    open("atlas.yaml", "w").write(f"notify:\n  webhooks: ['{base}/ok', '{base}/fail']\n")
    result = runner.invoke(app, ["notify", "test"])
    assert result.exit_code == 1 and "✓ webhook" in result.output and "✗ webhook" in result.output
    assert got[0]["body"]["title"] == "✅ Atlas test alert"


def test_apprise_delivers_through_a_real_apprise(receiver):
    pytest.importorskip("apprise")
    base, got = receiver
    url = base.replace("http://", "json://") + "/apprise"

    assert notify.send(NotifyConfig(apprise=[url]), TEXT) == (True, "")
    assert got[0]["path"] == "/apprise" and got[0]["body"]["title"] == "🆕 New device on the network"
    assert got[0]["body"]["message"].startswith("• **Pixel-7**")
