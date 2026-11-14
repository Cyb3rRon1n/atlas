import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from atlas.web.cabling_page import cabling_csv, render_cabling_page
from atlas.wiring.build import build_wiring
from atlas.wiring.unifi import parse_unifi
from tests.test_web_server import running_server  # noqa: F401  (fixture)
from tests.test_wiring_build import CABLING, CLIENTS, DEVICES, INVENTORY, SWITCH


def _latest(name_override=None):
    switch = dict(SWITCH, name=name_override) if name_override else SWITCH
    snapshot = build_wiring([switch], parse_unifi(DEVICES, CLIENTS), INVENTORY, CABLING)
    return {"taken_at": datetime(2026, 1, 1, 12, 0), "snapshot": snapshot,
            "raw": {"switches": {switch["name"]: switch}, "unifi": parse_unifi(DEVICES, CLIENTS)},
            "sources": {switch["name"]: {"ok": True, "error": "", "stale": False, "note": "weak privacy (DES)"},
                        "unifi": {"ok": False, "error": "UniFi unreachable: timed out", "stale": True, "note": ""}}}


def test_disabled_and_empty_states():
    assert "cabling.example.yaml" in render_cabling_page(None, [], False)
    page = render_cabling_page(None, [], True)
    assert "No wiring scan yet" in page and 'id="wiring-refresh"' in page


def test_page_with_snapshot():
    page = render_cabling_page(_latest(), [{"type": "moved", "text": "nas moved: core-switch gi5 → core-switch gi7"}],
                               True, now=datetime(2026, 1, 1, 12, 30))
    assert 'id="wiring-data"' in page and '/static/elk.bundled.js' in page
    assert "PP1-05" in page and "Rack - nas" in page and "30 min ago" in page
    assert "gi5 · 1G · nas" in page                                  # faceplate tooltip
    assert "2 links between gateway and core-switch" in page          # warning
    assert "nas moved" in page and "chip stale" in page and "weak privacy (DES)" in page


def test_script_breakout_is_escaped():
    page = render_cabling_page(_latest("</script><b>x"), [], True, now=datetime(2026, 1, 1, 13))
    data = page.split('id="wiring-data">', 1)[1].split("</script>", 1)[0]
    assert "<\\/script>" in data and "<b>x" not in page.replace("<\\/script><b>x", "")
    json.loads(data)


def test_csv_header_and_formula_guard():
    latest = _latest()
    latest["snapshot"]["links"][0]["label"] = "=cmd()"
    text = cabling_csv(latest["snapshot"])
    assert text.splitlines()[0] == "switch,port,device,device_port,speed,up,via,patch,label"
    assert "'=cmd()" in text


def test_routes(running_server):  # noqa: F811
    with urllib.request.urlopen(running_server + "/cabling", timeout=5) as response:
        assert response.status == 200 and "Cabling" in response.read().decode()

    with urllib.request.urlopen(running_server + "/static/elk.bundled.js", timeout=5) as response:
        assert response.status == 200

    request = urllib.request.Request(running_server + "/api/wiring/refresh", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"})
    try:
        urllib.request.urlopen(request, timeout=5)
        assert False, "expected 400"
    except urllib.error.HTTPError as error:
        assert error.code == 400 and "not enabled" in error.read().decode()

    cross = urllib.request.Request(running_server + "/api/wiring/refresh", data=b"{}", method="POST",
                                   headers={"Content-Type": "application/json", "Origin": "http://evil.example"})
    try:
        urllib.request.urlopen(cross, timeout=5)
        assert False, "expected 403"
    except urllib.error.HTTPError as error:
        assert error.code == 403
