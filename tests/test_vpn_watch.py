from types import SimpleNamespace

import requests

from atlas.access.store import AccessStore
from atlas.monitoring.vpn import check, probe


class FakeSession:
    """qBittorrent Web API stand-in: status None = unreachable."""

    def __init__(self, status="connected", active=0, login="Ok."):
        self.status, self.active, self.login = status, active, login

    def _resp(self, payload=None, text=""):
        if self.status is None:
            raise requests.ConnectionError("refused")
        return SimpleNamespace(text=text, json=lambda: payload, raise_for_status=lambda: None)

    def post(self, url, **_):
        return self._resp(text=self.login)

    def get(self, url, **_):
        if url.endswith("/transfer/info"):
            return self._resp({"connection_status": self.status})
        return self._resp([{}] * self.active)


CLIENT = SimpleNamespace(name="cyberbox", url="http://qb:8080", username="admin", password="x")


def test_probe_reasons():
    assert probe(CLIENT, FakeSession()) == ""
    assert probe(CLIENT, FakeSession("firewalled", active=0)) == ""   # idle: firewalled means nothing
    assert "port forward" in probe(CLIENT, FakeSession("firewalled", active=2))
    assert "tunnel" in probe(CLIENT, FakeSession("disconnected"))
    assert "unreachable" in probe(CLIENT, FakeSession(None))
    assert "login" in probe(CLIENT, FakeSession(login="Fails."))


def test_check_alerts_after_two_failures_once_then_on_recovery(temp_db):
    store, sent = AccessStore(temp_db), []
    send = lambda text: (sent.append(text) or True, "")

    check([CLIENT], store, send, FakeSession(None))
    assert sent == []                                   # one blip is not an outage
    check([CLIENT], store, send, FakeSession(None))
    assert len(sent) == 1 and "cyberbox" in sent[0] and "🔴" in sent[0]
    check([CLIENT], store, send, FakeSession(None))
    assert len(sent) == 1                               # no repeats while down
    check([CLIENT], store, send, FakeSession())
    assert len(sent) == 2 and "working again" in sent[1]


def test_check_retries_unsent_alert(temp_db):
    store, sent = AccessStore(temp_db), []

    for _ in range(2):
        check([CLIENT], store, lambda text: (False, "signal down"), FakeSession(None))
    check([CLIENT], store, lambda text: (sent.append(text) or True, ""), FakeSession(None))
    assert len(sent) == 1
