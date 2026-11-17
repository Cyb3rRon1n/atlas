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


def test_diagram_gets_physical_faces():
    page = render_cabling_page(_latest(), [], True, now=datetime(2026, 1, 1, 13))
    data = json.loads(page.split('id="wiring-data">', 1)[1].split("</script>", 1)[0])
    face = data["faces"]["s:core-switch"]
    assert face["rows"] == 1 and [p["name"] for p in face["ports"]] == ["gi1", "gi2", "gi5", "gi6"]
    assert 'style="left:calc(0 * var(--pw));top:calc(0 * var(--ph))"' in page


def test_cable_health_on_faceplate_and_list():
    latest = _latest()
    assert "Cable health" not in render_cabling_page(latest, [], True)       # scan from before cable health
    latest["snapshot"]["health"] = [
        {"device": "core-switch", "port": "gi5", "kind": "crc", "level": "bad",
         "reason": "Likely bad cable or jack", "detail": "520 CRC errors since the last scan (0.52% of packets)"},
        {"device": "core-switch", "port": "gi6", "kind": "speed", "level": "watch",
         "reason": "Speed dropped", "detail": "links at 100 Mbit/s, ran at 1 Gbit/s before"}]
    page = render_cabling_page(latest, [], True, now=datetime(2026, 1, 1, 13))
    assert 'class="port h-bad ' in page and 'class="port h-watch ' in page
    assert "Likely bad cable or jack: 520 CRC errors" in page
    assert page.index("Problem</span><b>core-switch gi5") < page.index("Watch</span><b>core-switch gi6")
    latest["snapshot"]["health"] = []
    assert "every connected port is clean" in render_cabling_page(latest, [], True)


def test_front_panels_first_with_port_detail_and_map_toggle(tmp_path):
    import html as html_lib
    import re
    import shutil
    import subprocess

    latest = _latest()
    latest["snapshot"]["health"] = [{"device": "core-switch", "port": "gi5", "kind": "crc", "level": "bad",
                                     "reason": "Likely bad cable or jack", "detail": "520 CRC errors"}]
    page = render_cabling_page(latest, [], True, now=datetime(2026, 1, 1, 13))
    assert ".pd dd" not in re.sub(r"<style>.*?</style>", "", page, flags=re.S)     # styles stay inside <style>
    assert page.index('id="faceplates"') < page.index('id="diagram" hidden')
    assert 'data-view="faceplates" aria-pressed="true"' in page and 'id="port-detail"' in page
    assert "3 to check" in page and "<details open" in page and 'data-box="core-switch"' in page
    cell = re.search(r'data-detail="([^"]*)"[^>]*title="gi5 ', page)
    pairs = json.loads(html_lib.unescape(cell.group(1)))
    assert pairs[0] == ["Port", "Port 5 → nas"] and ["Status", "1G"] in pairs
    assert ["Problem", "Likely bad cable or jack: 520 CRC errors"] in pairs
    if shutil.which("node"):
        for i, script in enumerate(re.findall(r"<script>(.*?)</script>", page, re.S)):
            path = tmp_path / f"cabling{i}.js"
            path.write_text(script)
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            assert result.returncode == 0, result.stderr[:300]
