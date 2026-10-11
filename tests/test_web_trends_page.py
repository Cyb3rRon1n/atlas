from datetime import datetime, timedelta

from atlas.web.trends_page import _growth, render_trends_page

NOW = datetime(2026, 10, 11, 12)


def test_trends_charts_from_samples_and_proxmox_scans():
    samples = [(NOW - timedelta(hours=h), {"cpu": 20 + h, "mem": 5, "disk": 43, "temp": 55, "storage": {"media array": 58 + (10 - h) * 0.1},
                                           "containers": {"total": 48, "running": 48 - (h == 3), "unhealthy": 0}})
               for h in range(10, -1, -1)]
    node = lambda h: {"name": "proxmox", "cpu": 0.05, "mem": 40, "maxmem": 100, "disk": 25, "maxdisk": 100,
                      "zfs": [{"name": "bulk", "alloc": 70 + (10 - h) * 0.2, "size": 100}]}
    scans = [(NOW - timedelta(hours=h), {"nodes": [node(h)], "guests": [
        {"name": "mediabox", "status": "running", "cpu": 0.1, "mem": 2, "maxmem": 8, "template": False},
        {"name": "tpl", "status": "stopped", "template": True}]}) for h in range(10, -1, -1)]
    html = render_trends_page(samples, scans, "24h", NOW, "cyberpac", {"proxmox": "cyberbox"})
    for text in ("cyberpac", "cyberbox (Proxmox)", "Storage growth", "media array", "cyberbox bulk", "<ellipse", "Containers",
                 "mediabox", 'href="/trends?window=7d"', "full in", 'data-ask="Will any disk', "<polyline"):
        assert text in html, text
    assert ">tpl<" not in html and "Hottest sensor" in html and "°C" in html


def test_trends_empty_and_growth_estimates():
    html = render_trends_page([], [], "7d", NOW)
    assert "No history yet" in html and 'aria-current=page>7d' in html
    rising = [(NOW - timedelta(days=d), 90 - d) for d in range(10, -1, -1)]     # +1%/day from 90%
    assert "full in ~10 days" in _growth(rising) and "soon" in _growth(rising)
    assert "not growing" in _growth([(NOW - timedelta(hours=h), 50) for h in range(11, -1, -1)])
    assert "needs a few more hours" in _growth([(NOW, 50)] * 3)
