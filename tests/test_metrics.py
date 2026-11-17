import threading
import urllib.error
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer

from atlas.config.models import AtlasConfig
from atlas.web.metrics import collect, render

NOW = datetime(2026, 11, 17, 12)


def _sources():
    statuses = {
        "ups": {"detail": {"upses": {"rack": {"state": "battery", "charge": 87.0}}}},
        "heartbeats": {"detail": {"Backup": {"state": "late"}, "New": {"state": "waiting"}}},
        "dns": {"detail": {"info": {"kind": "Pi-hole", "blocking": True, "queries": 1000, "blocked": 160}}}}
    return {"uptime": lambda name: {"Media": (NOW, True, 12.5), "Internet": (NOW, False, None)}.get(name),
            "devices": lambda: [{"state": "known", "status": "seen"}] * 3 + [{"state": "new", "status": "seen"}],
            "alerts": lambda: [{"level": "problem"}, {"level": "watch"}, {"level": "watch"}],
            "statuses": lambda: statuses,
            "disks": lambda s: [("pve", [{"dev": "/dev/sda", "model": 'Odd "name"', "health": "PASSED", "temp": 36,
                                          "life": 92}, {"dev": "/dev/sdb", "health": "FAILED", "temp": None}])]}


def test_prometheus_text_from_what_atlas_saved():
    settings = AtlasConfig(uptime={"checks": [{"name": "Media", "target": "https://media.example.org"}]},
                           dns_filter={"enabled": True, "url": "http://192.0.2.53"})
    text = render(collect(settings, NOW, _sources()))
    for line in ('atlas_uptime_up{check="Media"} 1', 'atlas_uptime_response_ms{check="Media"} 12.5',
                 'atlas_uptime_up{check="Internet"} 0', 'atlas_devices{state="known",status="seen"} 3',
                 'atlas_alerts_open{level="watch"} 2', 'atlas_ups_on_battery{ups="rack"} 1',
                 'atlas_ups_charge_percent{ups="rack"} 87', 'atlas_heartbeat_ok{name="Backup"} 0',
                 'atlas_disk_healthy{host="pve",disk="/dev/sdb",model=""} 0',
                 'atlas_disk_temperature_celsius{host="pve",disk="/dev/sda",model="Odd \\"name\\""} 36',
                 'atlas_dns_blocking{server="Pi-hole"} 1', "# TYPE atlas_uptime_up gauge"):
        assert line in text, line
    assert 'name="New"' not in text and 'check="Internet"} 0\natlas_uptime_response_ms{check="Internet"}' not in text
    assert "/dev/sdb" not in text.split("atlas_disk_temperature_celsius")[1].split("#")[0]   # no temp = no line


def test_broken_sources_are_left_out():
    def boom(*a):
        raise RuntimeError("db gone")
    text = render(collect(AtlasConfig(), NOW, {"uptime": boom, "devices": boom, "alerts": boom, "statuses": boom,
                                               "disks": boom}))
    assert text.strip() == ""


def test_metrics_needs_sign_in_or_the_api_token(temp_db, isolated_cwd):
    from atlas.web.auth import Auth
    from atlas.web.server import AtlasWebHandler

    auth = Auth(isolated_cwd / "auth.json")
    auth.set_password("correct horse battery staple")
    handler = type("Handler", (AtlasWebHandler,), {"auth": auth})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_port}/metrics"

    def get(token=None):
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.headers["Content-Type"], response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, "", ""

    try:
        assert get()[0] == 401 and get("wrong")[0] == 401
        status, kind, body = get(auth.token())
        assert status == 200 and kind.startswith("text/plain; version=0.0.4") and "atlas_alerts_open" in body
    finally:
        httpd.shutdown()
        httpd.server_close()
