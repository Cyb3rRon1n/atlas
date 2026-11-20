from datetime import datetime, timedelta

import pytest

from lanxang.config.models import AtlasConfig, DnsFilterConfig
from lanxang.monitoring import dnsfilter
from lanxang.web.home_page import build_hosts, render_home_page


class Reply:
    def __init__(self, status, data):
        self.status_code, self.data = status, data

    def json(self):
        if self.data is None:
            raise ValueError("not json")
        return self.data


class FakePihole:
    """Pi-hole 6: /api/auth -> sid; reads need X-FTL-SID; DELETE /api/auth ends the session."""

    def __init__(self, password="secret", blocking="enabled"):
        self.password, self.blocking, self.calls, self.open = password, blocking, [], set()

    def post(self, url, json=None, **kw):
        self.calls.append(("POST", url))
        if json.get("password") != self.password:
            return Reply(401, {"error": {"key": "unauthorized"}})
        self.open.add("sid1")
        return Reply(200, {"session": {"valid": True, "totp": False, "sid": "sid1", "validity": 300}})

    def get(self, url, headers=None, **kw):
        self.calls.append(("GET", url))
        if self.password and (headers or {}).get("X-FTL-SID") not in self.open:
            return Reply(401, {})
        if url.endswith("/api/stats/summary"):
            return Reply(200, {"queries": {"total": 20000, "blocked": 3100, "percent_blocked": 15.5},
                               "gravity": {"domains_being_blocked": 123456}})
        if url.endswith("/api/dns/blocking"):
            return Reply(200, {"blocking": self.blocking, "timer": None})
        return Reply(200, {"clients": [{"ip": "192.0.2.20", "name": "", "count": 5000},
                                       {"ip": "192.0.2.21", "name": "tv.lan", "count": 900}]})

    def delete(self, url, headers=None, **kw):
        self.calls.append(("DELETE", url))
        self.open.discard((headers or {}).get("X-FTL-SID"))
        return Reply(204, None)


def _config(**kw):
    return DnsFilterConfig(enabled=True, url="http://192.0.2.53", **kw)


def test_pihole_signs_in_reads_and_always_signs_out():
    http = FakePihole()
    info = dnsfilter.fetch(_config(), {"LANXANG_DNS_PASSWORD": "secret"}, http)
    assert info["blocking"] and info["queries"] == 20000 and info["percent"] == 15.5 and info["blocklist"] == 123456
    assert info["clients"][1] == {"ip": "192.0.2.21", "name": "tv.lan", "count": 900}
    assert http.calls[-1] == ("DELETE", "http://192.0.2.53/api/auth") and not http.open
    with pytest.raises(dnsfilter.DnsFilterError, match="wrong password"):
        dnsfilter.fetch(_config(), {"LANXANG_DNS_PASSWORD": "nope"}, FakePihole())
    open_pihole = FakePihole(password="")
    assert dnsfilter.fetch(_config(), {}, open_pihole)["blocking"]               # no password set: no sign-in
    assert not any(method == "POST" for method, _ in open_pihole.calls)


def test_adguard_home_basic_auth_and_bad_addresses():
    class FakeAdGuard:
        def get(self, url, auth=None, **kw):
            assert auth == ("admin", "pw")
            if url.endswith("/control/status"):
                return Reply(200, {"protection_enabled": False, "running": True})
            if url.endswith("/control/filtering/status"):
                return Reply(200, {"filters": [{"enabled": True, "rules_count": 190000},
                                               {"enabled": False, "rules_count": 5000}]})
            return Reply(200, {"num_dns_queries": 1000, "num_blocked_filtering": 250,
                               "top_clients": [{"192.0.2.30": 600}, {"192.0.2.31": 400}]})

    info = dnsfilter.fetch(_config(kind="adguard", user="admin"), {"LANXANG_DNS_PASSWORD": "pw"}, FakeAdGuard())
    assert info["kind"] == "AdGuard Home" and info["blocking"] is False and info["percent"] == 25.0
    assert info["blocklist"] == 190000                                           # enabled lists only
    assert info["clients"][0] == {"ip": "192.0.2.30", "name": "", "count": 600}
    with pytest.raises(dnsfilter.DnsFilterError, match="web address"):
        dnsfilter.fetch(DnsFilterConfig(url="192.0.2.53"), {}, FakeAdGuard())

    class Html:
        def get(self, url, **kw):
            return Reply(200, None)
    with pytest.raises(dnsfilter.DnsFilterError, match="not a JSON answer"):
        dnsfilter.fetch(_config(kind="adguard"), {}, Html())


def test_blocking_off_twice_alerts_once_and_again_when_back(temp_db):
    from lanxang.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    settings = AtlasConfig(dns_filter=_config())
    t = datetime(2026, 11, 17, 9)
    states = [True, False, False, False, True]
    for i, on in enumerate(states):
        dnsfilter.run(settings, store, t + timedelta(minutes=15 * i), send=sent.append,
                      get=lambda config: {"kind": "Pi-hole", "blocking": on, "queries": 1, "blocked": 0, "percent": 0,
                                          "clients": []})
    assert [s.splitlines()[0] for s in sent] == ["**🛑 Ad blocking is off on Pi-hole**", "**✅ Ad blocking is back on (Pi-hole)**"]
    assert "since 09:15 UTC" in sent[0]

    def broken(config):
        raise dnsfilter.DnsFilterError("No answer from http://192.0.2.53: ConnectTimeout")
    detail = dnsfilter.run(settings, store, t + timedelta(hours=2), get=broken, send=sent.append)
    assert detail["error"] and detail["info"]["blocking"] is True and len(sent) == 2   # last known kept, no message


def test_home_card_names_the_busiest_devices():
    dns = {"error": "", "info": {"kind": "Pi-hole", "blocking": True, "queries": 20000, "blocked": 3100,
                                 "percent": 15.5, "blocklist": 123456,
                                 "clients": [{"ip": "192.0.2.20", "name": "", "count": 5000}]}}
    page = render_home_page(None, build_hosts(None, None, None), [], dns=dns,
                            names={"192.0.2.20": "Kids tablet"})
    assert "Kids tablet" in page and "5,000" in page and "123,456 domains" in page
