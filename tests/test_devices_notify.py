import json

import atlas.devices.notify as notify
from atlas.config.models import SignalNotifyConfig


ITEMS = [{"id": 1, "device": "Pixel-7", "ip": "192.168.10.88", "last_seen": "2026-09-29T12:00:00"},
         {"id": 2, "device": "192.168.10.90", "ip": "192.168.10.90", "last_seen": None}]


def test_format_new_message_is_bold_headline_and_short_lines():

    text = notify.format_message("new", ITEMS)

    assert text.splitlines()[0] == "**🆕 2 new devices on the network**"
    assert "• Pixel-7 (192.168.10.88)" in text
    assert text.rstrip().endswith("Triage them in atlas.")


def test_format_offline_message():

    text = notify.format_message("offline", ITEMS[:1])

    assert text.splitlines()[0] == "**🔴 Important device offline**"
    assert "last seen 2026-09-29 12:00" in text


def test_send_signal_posts_styled_json(monkeypatch):

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"], captured["body"] = request.full_url, json.loads(request.data)

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    config = SignalNotifyConfig(url="http://signal-cli:8080/", number="+1555", recipients=["+1555"])

    assert notify.send_signal(config, "hi") == (True, "")
    assert captured["url"] == "http://signal-cli:8080/v2/send"
    assert captured["body"] == {"message": "hi", "number": "+1555", "recipients": ["+1555"], "text_mode": "styled"}


def test_send_signal_failure_is_returned_not_raised(monkeypatch):

    def boom(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)

    assert notify.send_signal(SignalNotifyConfig(url="http://x"), "hi") == (False, "connection refused")


class FakeStore:

    def __init__(self):
        self.sent = []

    def due_notifications(self, now=None):
        return {"new": ITEMS}

    def mark_sent(self, ids, now=None):
        self.sent += ids


def test_deliver_marks_sent_only_on_success(monkeypatch):

    store = FakeStore()
    monkeypatch.setattr(notify, "send_signal", lambda config, text: (False, "down"))
    assert notify.deliver(store, SignalNotifyConfig(url="http://x")) == ["down"]
    assert store.sent == []

    monkeypatch.setattr(notify, "send_signal", lambda config, text: (True, ""))
    assert notify.deliver(store, SignalNotifyConfig(url="http://x")) == []
    assert store.sent == [1, 2]


def test_deliver_without_url_does_nothing():

    store = FakeStore()

    assert notify.deliver(store, SignalNotifyConfig()) == []
    assert store.sent == []
