from atlas.web.devices_pages import (ACTIONS_SCRIPT, render_coverage_page, render_device_page, render_devices_page,
                                     render_triage_page)


def device(id, name, state="new", status="seen", sightings=None, **extra):

    return {"id": id, "name": name, "kind": "other", "tags": [], "notes": "", "important": False,
            "state": state, "suggested_merge_id": None, "status": status, "ip": f"192.168.10.{id}",
            "last_seen": "2026-09-30T12:00:00",
            "sightings": sightings or [{"id": id * 10, "source": "lan", "external_id": f"aa:{id}",
                                        "ip": f"192.168.10.{id}", "mac": f"aa:{id}", "hostname": None,
                                        "detail": {}, "first_seen": "2026-09-30T11:00:00",
                                        "last_seen": "2026-09-30T12:00:00"}], **extra}


def test_triage_page_has_keep_merge_ignore_and_escapes():

    html = render_triage_page({
        "new": [device(2, "<script>x</script>", suggested_merge_id=1, suggested_merge_name="mediabox")],
        "quiet": [device(3, "pixel", state="known", status="quiet")],
    })

    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert 'data-post="/api/devices/2"' in html and 'data-name-from="name-2"' in html
    assert 'data-post="/api/devices/2/merge"' in html and "Merge into mediabox" in html
    assert "&quot;ignored&quot;" in html
    assert 'href="/devices/3"' in html


def test_empty_triage_says_so():

    assert "Nothing to triage" in render_triage_page({"new": [], "quiet": []})


def test_devices_page_lists_with_filter_box():

    html = render_devices_page([device(1, "mediabox", state="known"), device(2, "pixel")])

    assert 'id="filter"' in html and 'href="/devices/1"' in html and "pixel" in html


def test_actions_script_tolerates_a_non_json_body_and_flags_session_expiry():

    assert "response.json().catch(() => ({}))" in ACTIONS_SCRIPT
    assert "session expired? reload the page" in ACTIONS_SCRIPT
    assert "response.status === 401 || response.status === 403 || response.redirected" in ACTIONS_SCRIPT


def test_device_page_split_only_with_several_sightings_and_merge_targets():

    single = render_device_page(device(1, "pixel"), [device(1, "pixel"), device(2, "router")])
    assert "/split" not in single
    assert '<option value="2">router</option>' in single
    assert '<option value="1">' not in single
    assert 'id="edit"' in single and 'data-form="edit"' in single
    assert 'onsubmit="this.querySelector(\'[data-form]\').click(); return false"' in single

    two = device(1, "mediabox", sightings=[device(1, "a")["sightings"][0], device(9, "b")["sightings"][0]])
    assert 'data-post="/api/sightings/10/split"' in render_device_page(two, [two])


def test_coverage_page_shows_source_failures():

    html = render_coverage_page({
        "sources": [{"source": "proxmox", "last_run": "2026-09-30T12:00:00", "ok": False,
                     "error": "could not connect to Proxmox", "seen_count": 0, "last_ok": None}],
        "quiet": [], "invisible": [device(4, "garage-tv", state="known", status="invisible")],
    })

    assert "could not connect to Proxmox" in html and "garage-tv" in html
