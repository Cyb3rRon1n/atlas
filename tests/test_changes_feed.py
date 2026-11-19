import json
from datetime import datetime, timedelta

from lanxang.web import changes_feed

NOW = datetime(2026, 11, 17, 12)


def _alert(title, opened, resolved=None, level="problem", event=False):
    return {"title": title, "detail": "", "level": level, "event": event, "href": "/x", "opened_at": opened,
            "resolved_at": resolved}


SOURCES = {
    "alerts": lambda now, days: {
        "open": [_alert("Printer is offline", NOW - timedelta(hours=2))],
        "watch": [_alert("New open port 8080 on nas", NOW - timedelta(hours=5), level="watch", event=True)],
        "resolved": [_alert("Backup hasn't checked in", NOW - timedelta(days=2), NOW - timedelta(hours=1)),
                     _alert("Old thing", NOW - timedelta(days=3), NOW - timedelta(days=2))]},
    "devices": lambda: [{"name": "Den TV", "ip": "192.0.2.41", "sightings": [{"first_seen": (NOW - timedelta(hours=3)).isoformat()}]},
                        {"name": "nas", "ip": "192.0.2.10", "sightings": [{"first_seen": "2026-01-01T00:00:00"}]}],
    "changes": lambda since: [
        (NOW - timedelta(hours=4), "atlas.proxmox.changes_detected",
         {"changes": [{"type": "guest_removed", "vmid": 110, "name": "old-vm", "guest_type": "qemu"}]}),
        (NOW - timedelta(hours=6), "atlas.proxmox.changes_detected",
         {"changes": [{"type": "guest_removed", "vmid": 110, "name": "old-vm", "guest_type": "qemu"}]})]}


def test_last_day_in_plain_words_newest_first():
    items = changes_feed.collect(NOW, "24h", SOURCES)
    assert [(mark, text) for _, mark, text, _ in items] == [
        ("check", "Cleared: Backup hasn't checked in"), ("alert", "Printer is offline"),
        ("device", "New device: Den TV (192.0.2.41)"), ("search", "New open port 8080 on nas"),
        ("server", "Guest 'old-vm' (110) removed")]                        # the repeat 2 h later isn't shown again
    week = changes_feed.collect(NOW, "7d", SOURCES)
    assert any(text == "Cleared: Old thing" for _, _, text, _ in week) and len(week) == 8


def test_broken_sources_and_empty_render():
    def boom(*a):
        raise RuntimeError
    assert changes_feed.collect(NOW, "24h", {"alerts": boom, "devices": boom, "changes": boom}) == []
    html = changes_feed.render([], NOW, "24h")
    assert "all quiet" in html and 'href="/history?changes=7d"' in html


def test_activity_page_shows_it(temp_db, isolated_cwd):
    from lanxang.web.render import render_history_page
    html = render_history_page([], changes=changes_feed.render(changes_feed.collect(NOW, "24h", SOURCES), NOW, "24h"))
    assert "What changed" in html and "Printer is offline" in html and html.index("What changed") < html.index("No historical")


def test_icons_not_emoji_and_new_devices_fold_into_one_row():
    devices = [{"name": f"dev{n}", "ip": f"192.0.2.{n}", "sightings": [{"first_seen": (NOW - timedelta(minutes=n)).isoformat()}]}
               for n in range(1, 5)]
    items = changes_feed.collect(NOW, "24h", {**SOURCES, "devices": lambda: devices})
    html = changes_feed.render(items, NOW, "24h")
    assert "<svg" in html and not any(e in html for e in ("✅", "⚠️", "📱", "🔎", "🖥️", "📦", "👀"))
    assert html.count("4 new devices") == 1 and html.count("<summary>") == 1
    assert all(f">dev{n} (192.0.2.{n})</a>" in html for n in range(1, 5))
    lone = changes_feed.render(changes_feed.collect(NOW, "24h", SOURCES), NOW, "24h")
    assert "New device: Den TV (192.0.2.41)" in lone and "new devices</summary>" not in lone
    assert 'datetime="2026-11-17T10:00:00Z"' in lone and "Times are UTC" not in lone


def test_one_malformed_change_row_never_blanks_the_feed():
    sources = {**SOURCES, "changes": lambda since: [
        (NOW - timedelta(hours=1), "atlas.proxmox.changes_detected", {"changes": ["test-vm stopped", {"type": "guest_removed"},
         {"type": "guest_removed", "vmid": 7, "name": "ok-vm", "guest_type": "lxc"}]}),
        (NOW - timedelta(hours=2), "atlas.monitoring.changes_detected", ["not", "a", "dict"]),
        (NOW - timedelta(hours=3), "atlas.monitoring.changes_detected", {"changes": "nope"})]}
    texts = [text for _, _, text, _ in changes_feed.collect(NOW, "24h", sources)]
    assert "test-vm stopped" in texts and "Guest 'ok-vm' (7) removed" in texts and "Printer is offline" in texts
    assert changes_feed.render(changes_feed.collect(NOW, "24h", sources), NOW, "24h").count("<li>") >= 6
