from datetime import datetime, timedelta
from types import SimpleNamespace

from atlas.config.models import AtlasConfig
from atlas.monitoring import internet
from atlas.monitoring.uptime import UptimeStore
from atlas.web.uptime_page import internet_data, render_uptime_page


def test_checks_count_a_refused_router_as_up_and_need_one_internet_answer():
    answers = {("1.1.1.1", 443): (None, False), ("8.8.8.8", 443): (21.0, False), ("9.9.9.9", 443): (None, False)}
    connect = lambda host, port, timeout: answers[(host, port)]
    assert internet.check_internet(["1.1.1.1:443", "8.8.8.8:443", "9.9.9.9:443"], connect=connect) == \
        (True, 21.0, "1 of 3 answered")
    assert not internet.check_internet(["1.1.1.1:443"], connect=lambda *a: (None, False))[0]
    refused = lambda host, port, timeout: (0.8, True) if port == 80 else (None, False)
    assert internet.check_router("192.0.2.1", connect=refused) == (True, 0.8, "192.0.2.1 answered (port closed)")
    assert internet.check_router(None) is None


def test_outage_runs_and_which_side():
    t = datetime(2026, 11, 16, 12)
    rows = [(t + timedelta(minutes=i), ok, router) for i, (ok, router) in enumerate(
        [(True, True), (False, True), (False, True), (False, True), (True, True),   # 3 min, provider
         (False, False), (True, True),                                               # 1 min: too short
         (False, False), (False, True)])]                                            # still down, router was out
    assert internet.outages(rows, 2) == [(t + timedelta(minutes=1), t + timedelta(minutes=4), True),
                                         (t + timedelta(minutes=7), None, False)]


def test_run_alerts_on_the_drop_and_the_way_back(temp_db):
    store, sent = UptimeStore(temp_db), []
    settings = AtlasConfig()
    t = datetime(2026, 11, 16, 12)
    states = [True, False, False, False, True]
    for i, up in enumerate(states):
        internet.run(settings, store, t + timedelta(minutes=i), send=sent.append, gateway=lambda: "192.0.2.1",
                     internet=lambda targets, timeout: (up, 15.0 if up else None, "x"),
                     router=lambda gw: (True, 1.0, "ok"))
    assert [text.splitlines()[0] for text in sent] == ["**🌐 Internet is down**", "**✅ Internet is back**"]
    assert "provider" in sent[0] and "about 3 min" in sent[1]

    data = internet_data(store, t + timedelta(minutes=5), 2)
    assert data["outages"] == [(t + timedelta(minutes=1), t + timedelta(minutes=4), True)]
    page = render_uptime_page([], {}, t + timedelta(minutes=5), internet=data)
    assert "<h2>Internet</h2>" in page and "3 min · internet provider" in page and "your router" in page
    assert UptimeStore(temp_db).latest("Internet")[1:] == (True, 15.0)


def test_internet_and_router_names_are_reserved(isolated_cwd):
    from atlas.web.uptime_page import handle_post
    status, body = handle_post("/api/uptime/add", {"name": "Internet", "target": "https://example.org"})
    assert status == 400 and "built-in" in body["error"]
