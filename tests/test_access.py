from datetime import datetime, timedelta

from atlas.access.collect import jellyfin_logins
from atlas.access.parse import parse_line, read_new
from atlas.access.store import AccessStore
from atlas.web.access_page import render_access_page

LINE = ('97.102.129.35 - - [11/Oct/2026:02:23:12 +0000] "GET /web/index.html HTTP/1.1" {status} 7 "-" "Mozilla" '
        '148676 "jellyfin@docker" "http://172.18.0.6:8096" 9ms')


def test_parse_line_and_bad_lines():
    e = parse_line(LINE.format(status=200))
    assert e == {"ip": "97.102.129.35", "time": datetime(2026, 10, 11, 2, 23, 12), "method": "GET",
                 "path": "/web/index.html", "status": 200, "service": "jellyfin"}
    assert parse_line("garbage") is None and parse_line(LINE.replace("97.102.129.35", "not-an-ip").format(status=200)) is None


def test_read_new_tracks_offset_partial_lines_and_rotation(tmp_path):
    f = tmp_path / "access.log"
    f.write_text("a\nb\npart")
    lines, off = read_new(f, 0)
    assert lines == ["a", "b"] and off == 4                 # half-written last line waits
    f.write_text("a\nb\npartial\nc\n")
    assert read_new(f, off) == (["partial", "c"], 14)
    f.write_text("x\n")                                       # rotated / truncated -> start over
    assert read_new(f, 14) == (["x"], 2)


def test_jellyfin_logins_parse_users_ips_and_failures():
    items = [{"Id": 1, "Type": "AuthenticationSucceeded", "Name": "oneil successfully authenticated",
              "ShortOverview": "IP address: 97.102.129.35", "Date": "2026-10-10T20:08:01.1234567Z"},
             {"Id": 2, "Type": "SessionStarted", "Name": "palma is online from Garage TV", "ShortOverview": "IP address: 192.168.10.66",
              "Date": "2026-10-10T23:29:00Z"},
             {"Id": 3, "Type": "AuthenticationFailed", "Name": "Failed login attempt from bobby", "ShortOverview": "IP address: 1.2.3.4",
              "Date": "2026-10-10T19:00:00Z"},
             {"Id": 4, "Type": "VideoPlayback", "Name": "x", "Date": "2026-10-10T19:00:00Z"}]
    out = jellyfin_logins(items)
    assert [(l["user"], l["ip"], l["ok"], l["client"]) for l in out] == [
        ("oneil", "97.102.129.35", True, ""), ("palma", "192.168.10.66", True, "Garage TV"), ("bobby", "1.2.3.4", False, "")]
    assert out[0]["time"] == datetime(2026, 10, 10, 20, 8, 1)


def test_store_summary_page_map_people_and_anonymous(temp_db):
    store = AccessStore(temp_db)
    entries = [parse_line(LINE.format(status=s)) for s in (200, 200, 403)]
    entries.append(parse_line(LINE.replace("97.102.129.35", "85.240.1.9").format(status=200)))
    geo = {"97.102.129.35": {"cc": "US", "country": "United States", "city": "Tampa", "region": "Florida", "lat": 27.9, "lon": -82.4,
                           "org": "Spectrum"},
           "85.240.1.9": {"cc": "PT", "country": "Portugal", "city": "Lisbon", "region": "", "lat": 38.7, "lon": -9.1, "org": "<b>x"}}
    store.touch_ips(store.record_hits(entries), geo.get)
    store.record_logins([{"app": "jellyfin", "external_id": "1", "time": datetime(2026, 10, 11, 2), "user": "oneil",
                          "ip": "97.102.129.35", "ok": True, "client": ""}])
    assert store.record_logins([{"app": "jellyfin", "external_id": "1", "time": datetime(2026, 10, 11, 2), "user": "oneil",
                                 "ip": "97.102.129.35", "ok": True, "client": ""}]) == 0   # idempotent
    s = store.summary(datetime(2026, 10, 10))
    v = {x["ip"]: x for x in s["visitors"]}
    assert v["97.102.129.35"]["requests"] == 3 and v["97.102.129.35"]["denied"] == 1 and v["97.102.129.35"]["city"] == "Tampa"
    html = render_access_page(s, "7d")
    assert "oneil" in html and "Tampa, Florida, US" in html and 'class="user"' in html     # signed-in place drawn green
    assert "Anonymous visitors (1 IPs)" in html and "Lisbon, PT" in html and "&lt;b&gt;x" in html and "<b>x" not in html
    assert 'href="/access?window=24h"' in html and "DB-IP" in html and 'data-ask="Who signed in' in html
    assert store.prune(datetime(2026, 10, 12)) > 0 and store.summary(datetime(2026, 1, 1))["visitors"] == []
    assert "access.enabled" in render_access_page({"visitors": [], "logins": []}, "7d", enabled=False)


def test_places_learn_then_review_confirm_and_alert(temp_db):
    from atlas.access.collect import AccessCollector
    from atlas.config.models import AccessConfig, PostureConfig, SignalNotifyConfig
    store = AccessStore(temp_db)
    t0 = datetime(2026, 10, 1)
    geo = {"97.102.129.35": {"cc": "US", "country": "United States", "city": "Tampa", "region": "Florida", "org": "Spectrum"},
           "85.240.1.9": {"cc": "PT", "country": "Portugal", "city": "Lisbon", "region": "", "org": "MEO"},
           "192.168.10.66": {"country": "Home network"}}
    store.touch_ips({ip: t0 for ip in geo}, geo.get)
    login = lambda i, ip, when, ok=True: {"app": "jellyfin", "external_id": str(i), "time": when, "user": "corn", "ip": ip,
                                          "ok": ok, "client": ""}
    store.record_logins([login(1, "97.102.129.35", t0), login(2, "192.168.10.66", t0)])
    assert store.classify_logins(t0) == []                                   # learning window
    store.record_logins([login(3, "85.240.1.9", t0 + timedelta(days=20)), login(4, "85.240.1.9", t0 + timedelta(days=21), False)])
    new = store.classify_logins(t0 + timedelta(days=21))
    assert [n["label"] for n in new] == ["Lisbon, PT · MEO"]                 # new place after learning -> review
    places = {p["place_key"]: p["status"] for p in store.places()}
    assert places == {"US/Spectrum": "learned", "PT/MEO": "review"}            # home network never becomes a place

    sent = []
    c = AccessCollector(AccessConfig(), PostureConfig(), store, signal=SignalNotifyConfig(url="http://signal"),
                        send=lambda cfg, text: (sent.append(text) or True, ""))
    assert c._alert() == 1 and "corn" in sent[0] and "Lisbon" in sent[0] and c._alert() == 0   # alerted once

    html = render_access_page({"visitors": [], "logins": []}, "7d", user_places=store.places())
    assert "New sign-in places (1)" in html and 'data-confirm-key="PT/MEO"' in html and "Normal places (1)" in html
    assert store.confirm_place("corn", "PT/MEO")["ok"] and not store.confirm_place("x", "y")["ok"]
    assert "New sign-in places" not in render_access_page({"visitors": [], "logins": []}, "7d", user_places=store.places())


def test_ipv6_place_uses_the_providers_prefix_not_the_city():
    from types import SimpleNamespace
    from atlas.access.store import place_of
    row = lambda city: SimpleNamespace(ip="2601:201:8f01:f52b::1", org="", asn=None, city=city, region="CA", cc="US", country="US")
    assert place_of(row("Fresno"))[0] == place_of(row("Clovis"))[0] == "US/IPv6 2601:201::/32"
