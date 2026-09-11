from atlas.web.render import render_history_page, render_overview_page, render_trends_page


class FakeEvent:

    def __init__(self, created_at, event_type, source, payload):

        self.created_at = created_at
        self.event_type = event_type
        self.source = source
        self.payload = payload


def test_render_overview_page_no_environment_shows_hint():

    html = render_overview_page(None, None)

    assert "No inventory found" in html
    assert "atlas discover" in html


def test_render_overview_page_shows_system_and_hardware():

    environment = {
        "timestamp": "2026-01-01 00:00:00",
        "system": {"hostname": "sentinel"},
        "hardware": {"cpu_model": "Test CPU"},
        "storage": {},
        "network": {},
        "containers": {},
        "virtualization": {}
    }

    html = render_overview_page(environment, None)

    assert "sentinel" in html
    assert "Test CPU" in html


def test_render_overview_page_renders_real_storage_shape():

    # collect_storage() (atlas/discovery/storage.py) always returns a list
    # of per-mount dicts, never a dict - every other test in this file seeds
    # "storage": {}, which masked a real crash (_kv_table called .items() on
    # this list) that only surfaced running `atlas discover` for real.
    environment = {
        "timestamp": "2026-01-01 00:00:00",
        "system": {}, "hardware": {}, "network": {},
        "storage": [
            {"device": "/dev/sda1", "mountpoint": "/", "filesystem": "ext4", "total_gb": 100.0, "used_percent": 50.0}
        ],
        "containers": {}, "virtualization": {}
    }

    html = render_overview_page(environment, None)

    assert "/dev/sda1" in html
    assert "ext4" in html


def test_render_overview_page_flattens_containers_dict():
    """
    containers is keyed by plugin name, not container name - each
    entry is {"available": bool, "containers": [...]} (see
    atlas.plugins.AtlasPlugin.category). A real container's own name
    lives inside that nested list, not as the dict key.
    """

    environment = {
        "timestamp": "2026-01-01 00:00:00",
        "system": {}, "hardware": {}, "storage": {}, "network": {},
        "containers": {
            "Docker": {
                "available": True,
                "containers": [{"name": "plex", "status": "running"}]
            }
        },
        "virtualization": {}
    }

    html = render_overview_page(environment, None)

    assert "plex" in html
    assert "running" in html
    assert "Docker" in html


def test_render_overview_page_shows_proxmox_guests():

    environment = {
        "timestamp": "2026-01-01 00:00:00",
        "system": {}, "hardware": {}, "storage": {}, "network": {},
        "containers": {},
        "virtualization": {"guests": [{"vmid": 100, "name": "plex", "status": "running"}]}
    }

    html = render_overview_page(environment, None)

    assert "Virtualization Guests" in html
    assert "plex" in html


def test_render_overview_page_shows_plugin_sourced_guests():
    """
    A non-Proxmox virtualization plugin (e.g. LibvirtPlugin) lands
    under "virtualization" keyed by plugin name, the same shape as
    "containers" - distinct from atlas proxmox scan's flat
    {"nodes": [...], "guests": [...]}.
    """

    environment = {
        "timestamp": "2026-01-01 00:00:00",
        "system": {}, "hardware": {}, "storage": {}, "network": {},
        "containers": {},
        "virtualization": {
            "Libvirt": {
                "available": True,
                "guests": [{"name": "test-vm", "uuid": "abc-123", "state": "running"}]
            }
        }
    }

    html = render_overview_page(environment, None)

    assert "Virtualization Guests" in html
    assert "test-vm" in html
    assert "Libvirt" in html


def test_render_overview_page_shows_latest_analysis():

    environment = {
        "timestamp": "2026-01-01 00:00:00",
        "system": {}, "hardware": {}, "storage": {}, "network": {},
        "containers": {}, "virtualization": {}
    }

    analysis = {
        "summary": "Everything looks healthy.",
        "recommendations": ["Consider restarting plex."],
        "provider": "ollama",
        "model": "llama3.1",
        "created_at": "2026-01-01 00:00:00"
    }

    html = render_overview_page(environment, analysis)

    assert "Everything looks healthy." in html
    assert "Consider restarting plex." in html
    assert "ollama" in html


def test_render_overview_page_escapes_untrusted_values():
    """
    Container names/labels come from whatever's actually running on
    the host - a real (if unlikely) injection surface if a container
    were ever named/labeled with HTML. Confirms escaping, not just
    that the page renders.
    """

    environment = {
        "timestamp": "2026-01-01 00:00:00",
        "system": {}, "hardware": {}, "storage": {}, "network": {},
        "containers": {
            "Docker": {
                "available": True,
                "containers": [{"name": "<script>alert(1)</script>", "status": "running"}]
            }
        },
        "virtualization": {}
    }

    html = render_overview_page(environment, None)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_history_page_no_events_shows_hint():

    html = render_history_page([])

    assert "No historical events found" in html


def test_render_history_page_shows_events():

    events = [FakeEvent("2026-01-01 00:00:00", "atlas.discovery.completed", "Discovery", "{}")]

    html = render_history_page(events)

    assert "atlas.discovery.completed" in html
    assert "Discovery" in html


def test_render_trends_page_no_data_shows_hint():

    html = render_trends_page({"host": {}, "containers": {}, "guests": {}})

    assert "No monitoring history found" in html


def test_render_trends_page_shows_host_and_container_summaries():

    payload = {
        "host": {
            "cpu_percent": {"latest": 30.0, "min": 10.0, "max": 30.0, "avg": 20.0, "samples": 3}
        },
        "containers": {
            "plex": {
                "cpu_percent": {"latest": 15.0, "min": 5.0, "max": 15.0, "avg": 10.0, "samples": 3}
            }
        },
        "guests": {}
    }

    html = render_trends_page(payload)

    assert "30.0%" in html
    assert "plex" in html
    assert "15.0%" in html


def test_render_trends_page_shows_guest_summaries():

    payload = {
        "host": {}, "containers": {},
        "guests": {
            "100": {
                "name": "plex",
                "cpu_percent": {"latest": 30.0, "min": 10.0, "max": 30.0, "avg": 20.0, "samples": 3}
            }
        }
    }

    html = render_trends_page(payload)

    assert "plex (100)" in html
    assert "30.0%" in html
