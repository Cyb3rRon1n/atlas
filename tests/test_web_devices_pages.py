import json
from html import unescape

from lanxang.web.devices_pages import (ACTIONS_SCRIPT, render_coverage_page, render_device_page, render_devices_page,
                                     render_triage_page)


def device(id, name, state="new", status="seen", sightings=None, **extra):

    return {"id": id, "name": name, "kind": "other", "tags": [], "notes": "", "important": False,
            "state": state, "connection": "unknown", "connection_guessed": False, "uplink_id": None, "suggested_merge_id": None, "status": status, "ip": f"192.168.50.{id}",
            "last_seen": "2026-09-30T12:00:00",
            "sightings": sightings or [{"id": id * 10, "source": "lan", "external_id": f"aa:{id}",
                                        "ip": f"192.168.50.{id}", "mac": f"aa:{id}", "hostname": None,
                                        "detail": {}, "first_seen": "2026-09-30T11:00:00",
                                        "last_seen": "2026-09-30T12:00:00"}], **extra}


def test_triage_page_has_keep_merge_ignore_and_escapes():

    html = render_triage_page({
        "new": [device(2, "<script>x</script>", suggested_merge_id=1, suggested_merge_name="fileserver")],
        "quiet": [device(3, "pixel", state="known", status="quiet")],
    })

    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert 'data-post="/api/devices/2"' in html and 'data-name-from="name-2"' in html
    assert 'data-post="/api/devices/2/merge"' in html and "Merge into fileserver" in html
    assert "&quot;ignored&quot;" in html
    assert 'href="/devices/3"' in html


def test_empty_triage_says_so():

    assert "Nothing to triage" in render_triage_page({"new": [], "quiet": []})


def test_devices_page_lists_with_filter_box():

    html = render_devices_page([device(1, "fileserver", state="known"), device(2, "pixel")])

    assert 'id="filter"' in html and 'href="/devices/1"' in html and "pixel" in html


def test_actions_script_tolerates_a_non_json_body_and_flags_session_expiry():

    assert "response.json().catch(() => ({}))" in ACTIONS_SCRIPT
    assert "session expired? reload the page" in ACTIONS_SCRIPT
    assert "response.status === 401 || response.status === 403 || response.redirected" in ACTIONS_SCRIPT


def test_actions_script_sends_only_changed_form_fields():

    assert "formEl.dataset.original" in ACTIONS_SCRIPT
    assert "Nothing changed." in ACTIONS_SCRIPT
    assert 'original[key] || []).join(",")' in ACTIONS_SCRIPT


def test_device_page_form_carries_data_original_with_device_values():

    dev = device(1, "pixel", state="known", kind="network", tags=["a", "b"], notes="hello", important=True)

    html = render_device_page(dev, [dev])

    assert 'data-original="' in html
    start = html.index('data-original="') + len('data-original="')
    end = html.index('"', start)
    original = json.loads(unescape(html[start:end]))

    assert original == {"name": "pixel", "kind": "network", "state": "known",
                        "tags": ["a", "b"], "notes": "hello", "important": True,
                        "connection": "unknown", "uplink_id": None}


def test_device_page_split_only_with_several_sightings_and_merge_targets():

    single = render_device_page(device(1, "pixel"), [device(1, "pixel"), device(2, "router")])
    assert "/split" not in single
    assert '<option value="2">router</option>' in single
    assert '<option value="1">' not in single
    assert 'id="edit"' in single and 'data-form="edit"' in single
    assert 'onsubmit="this.querySelector(\'[data-form]\').click(); return false"' in single

    two = device(1, "fileserver", sightings=[device(1, "a")["sightings"][0], device(9, "b")["sightings"][0]])
    assert 'data-post="/api/sightings/10/split"' in render_device_page(two, [two])


def test_device_page_connection_and_uplink_fields():

    switch = device(2, "switch", kind="network")
    nas = device(3, "nas", kind="server")
    phone = device(4, "phone")
    dev = device(1, "pc", kind="server", connection="wired", uplink_id=2)

    html = render_device_page(dev, [dev, switch, nas, phone])

    assert 'name="connection">' in html and '<option value="wired" selected>Wired</option>' in html
    assert 'name="uplink">' in html and '<option value="">Router / not set</option>' in html
    assert '<option value="2" selected>switch</option>' in html and '<option value="3">nas</option>' in html
    assert '<option value="4">phone</option>' not in html.split('name="uplink"')[1].split("</select>")[0]
    assert '<option value="1"' not in html.split('name="uplink"')[1].split("</select>")[0]

    start = html.index('data-original="') + len('data-original="')
    original = json.loads(unescape(html[start:html.index('"', start)]))
    assert original["connection"] == "wired" and original["uplink_id"] == 2


def test_device_page_shows_stored_connection_when_guessed():

    dev = device(1, "pixel", connection="wireless", connection_guessed=True)

    html = render_device_page(dev, [dev])

    assert '<option value="unknown" selected>Unknown</option>' in html and "Guessed wireless" in html
    assert '<option value="" selected>Router / not set</option>' in html


def test_device_page_uplink_choices_include_the_router_regardless_of_kind():

    router = device(2, "router", kind="workstation",
                    sightings=[{"id": 20, "source": "lan", "external_id": "aa:2", "ip": "192.168.50.1",
                                "mac": "aa:2", "hostname": None, "detail": {"gateway": True},
                                "first_seen": "2026-09-30T11:00:00", "last_seen": "2026-09-30T12:00:00"}])
    dev = device(1, "pc", kind="server")

    html = render_device_page(dev, [dev, router])
    uplink_options = html.split('name="uplink"')[1].split("</select>")[0]

    assert '<option value="2">router</option>' in uplink_options


def test_actions_script_diffs_connection_and_uplink():

    assert 'field("connection").value' in ACTIONS_SCRIPT
    assert "String(original.uplink_id ?? \"\")" in ACTIONS_SCRIPT


def test_coverage_page_shows_source_failures():

    data = coverage_data(invisible=[device(4, "garage-tv", state="known", status="invisible")])
    data["sources"].append({"source": "proxmox", "last_run": "2026-09-30T12:00:00", "ok": False,
                            "error": "could not connect to Proxmox", "seen_count": 0, "last_ok": None})
    html = render_coverage_page(data)

    assert "could not connect to Proxmox" in html and "1 known device has never been seen" in html
    assert 'href="/triage"' in html and "garage-tv" not in html      # Triage is the one place that lists them


def test_devices_page_attention_groups_and_ignored():
    devices = [device(1, "fileserver", state="known"), device(2, "192.168.1.9", state="new"),
               device(3, "old-tv", state="ignored"), device(4, "laptop", state="known")]
    devices[0]["kind"], devices[3]["kind"] = "server", "workstation"
    devices[3]["status"] = "quiet"
    html = render_devices_page(devices)
    assert "Needs attention (2)" in html and 'id="name-2"' in html and "gone quiet" in html
    assert "Servers (1)" in html and "Computers (1)" in html and "Ignored (1)" in html
    assert html.count("data-row") >= 4 and 'id="filter"' in html
    assert 'data-ask="Which devices are new' in html


def test_device_page_shows_wiring_model_and_links_its_front_panel():

    dev = device(1, "core-switch")
    snapshot = {"nodes": [{"id": "s:core-switch", "name": "core-switch", "kind": "switch", "ip": "192.168.50.1",
                           "mac": None, "model": "ACME-28 28-Port Gigabit Managed Switch"},
                          {"id": "h:aa:00:00:00:00:02", "name": "nas", "kind": "host", "ip": "",
                           "mac": "AA:00:00:00:00:02"}]}

    html = render_device_page(dev, [dev], wiring=snapshot)
    assert '<div class="model">ACME-28 28-Port Gigabit Managed Switch</div>' in html
    assert '<a class="btn secondary" href="/cabling#fp-s%3Acore-switch">View on front panel</a>' in html

    nas = device(2, "nas", sightings=[{"id": 20, "source": "lan", "external_id": "x", "ip": "192.168.50.9",
                                        "mac": "aa-00-00-00-00-02", "hostname": None, "detail": {},
                                        "first_seen": None, "last_seen": None}])
    html = render_device_page(nas, [nas], wiring=snapshot)
    assert 'href="/cabling"' in html and "Where it plugs in" in html          # matched by MAC, no front panel

    assert 'class="btn secondary" href="/cabling' not in render_device_page(device(3, "pixel"), [device(3, "pixel")], wiring=snapshot)
    assert 'class="btn secondary" href="/cabling' not in render_device_page(dev, [dev])


def test_device_page_matches_the_gateway_by_role():

    router = device(5, "router", sightings=[{"id": 50, "source": "lan", "external_id": "x", "ip": "192.168.50.254",
                                              "mac": "aa:00:00:00:00:6d", "hostname": None,
                                              "detail": {"gateway": True}, "first_seen": None, "last_seen": None}])
    snapshot = {"nodes": [{"id": "u:aa:00:00:00:00:68", "name": "gw", "kind": "gateway", "ip": "",
                           "mac": "aa:00:00:00:00:68"}]}
    assert 'href="/cabling#fp-u%3Aaa%3A00%3A00%3A00%3A00%3A68"' in render_device_page(router, [router], wiring=snapshot)


def test_device_page_status_header_grid_and_proper_case_labels():

    dev = device(1, "pixel", state="known", kind="container-host", status="quiet")
    html = render_device_page(dev, [dev])

    head = html.split('class="card dhead"')[1].split("</div></div>")[0]
    assert '<span class="schip warn">Gone quiet</span>' in head and "Container host" in head
    assert '<span class="mono">192.168.50.1</span>' in head and '<span class="mono">aa:1</span>' in head
    assert 'class="dform"' in html and ".dform { display:grid; grid-template-columns:repeat(2" in html
    assert "@media (max-width: 700px) { .dform { grid-template-columns:1fr; } }" in html
    assert '<div class="field full"><label for="dev-notes">Notes</label><textarea id="dev-notes" name="notes">' in html
    # labels proper case, stored values unchanged
    assert '<option value="container-host" selected>Container host</option>' in html
    assert '<option value="known" selected>Known</option>' in html and '<option value="new">New</option>' in html
    assert '<option value="wireless">Wireless</option>' in html
    for name in ("name", "kind", "state", "connection", "uplink", "tags", "notes", "important"):
        assert f'name="{name}"' in html, name


def test_device_page_danger_zone_merge_starts_unchosen_and_confirms_in_page():

    dev, other = device(1, "pixel"), device(2, "router")
    html = render_device_page(dev, [dev, other])
    zone = html.split('class="card danger-zone"')[1]

    assert '<option value="" selected disabled>Choose a device\u2026</option><option value="2">router</option>' in zone
    assert '<button type="button" class="danger" id="merge-ask" disabled>Merge\u2026</button>' in zone
    confirm = zone.split('id="merge-confirm"')[1].split("</section>")[0]
    assert 'role="group" aria-label="Confirm merge" hidden>' in zone and "alertdialog" not in html
    assert 'getElementById("merge-cancel").focus()' in html and 'button.danger").focus()' not in html
    assert 'event.key === "Escape") { close(); ask.focus(); }' in html
    assert 'data-post="/api/devices/1/merge"' in confirm and 'data-into-from="merge-into"' in confirm
    assert 'data-after="goto"' in confirm and ">Yes, merge</button>" in confirm and 'id="merge-cancel"' in confirm
    assert 'ask.disabled = !pick.value' in html and "box.hidden = false" in html
    assert "confirm(" not in html                                         # no browser dialogs in the viewer
    assert 'data-post="/api/devices/1/merge"' not in html.split('class="card danger-zone"')[0]

    alone = render_device_page(dev, [dev])
    assert 'class="card danger-zone"' not in alone and 'id="merge-into"' not in alone


def latest(runs):
    """coverage()["sources"] for these runs: each source's latest run."""

    return [{"source": source, "last_run": items[-1]["started_at"], "ok": items[-1]["ok"], "error": items[-1]["error"],
             "seen_count": items[-1]["seen_count"], "last_ok": None} for source, items in runs.items()]


def coverage_data(runs=None, devices_seen=3, **extra):
    """A coverage() result: lan and unifi counted, runs keyed by source, 1 of 3 devices on two sources."""

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def week(source, bad=(), error=""):
        return [{"source": source, "started_at": (now - timedelta(days=6 - day)).isoformat(), "ok": day not in bad,
                 "error": error if day in bad else "", "seen_count": devices_seen} for day in range(7)]

    runs = runs if runs is not None else {"lan": week("lan"), "unifi": week("unifi")}
    data = {
        "sources": latest(runs),
        "quiet": [], "invisible": [], "runs": runs, "counted": list(runs), "multi": 1, "total": 3,
        "single_source": [{"id": 2, "name": "printer", "source": "lan"}, {"id": 3, "name": "nas", "source": "lan"}],
        "unknown_connection": 0, "off_map": None,
    }
    data.update(extra)
    data["week"] = week
    return data


def test_coverage_page_headline():

    html = render_coverage_page(coverage_data())

    assert "<b>1 of 3</b>" in html and "devices are seen by two or more sources" in html
    assert "so one source failing won&#x27;t hide them" in html


def test_coverage_one_source_headline():

    data = coverage_data()
    data.update(runs={"lan": data["runs"]["lan"]}, counted=["lan"], multi=0, total=4,
                single_source=[{"id": i, "name": f"d{i}", "source": "lan"} for i in (1, 2, 3)])
    data["sources"] = latest(data["runs"])

    html = render_coverage_page(data)

    assert "All 3 devices come from one source (LAN scan)" in html     # the 4th (config only) isn't seen by it
    assert "Add another source" in html


def test_source_card_day_strip_and_failing():

    data = coverage_data()
    data["runs"]["unifi"] = data["week"]("unifi", bad=(1, 4), error="bad gateway")
    data["sources"] = latest(data["runs"])

    html = unescape(render_coverage_page(data))
    unifi = html.split("UniFi</b>")[1].split("</article>")[0]

    assert "2 bad days" in unifi and 'aria-label="5 of 7 days ok"' in unifi

    data["runs"]["unifi"] = data["week"]("unifi", bad=(6,), error="login timed out")
    data["sources"] = latest(data["runs"])
    unifi = unescape(render_coverage_page(data)).split("UniFi</b>")[1].split("</article>")[0]

    assert "failing" in unifi and "login timed out" in unifi and ">ok<" not in unifi


def test_ways_to_see_more_rows():

    data = coverage_data(unknown_connection=14, off_map=20)

    html = unescape(render_coverage_page(data, setup={"snmp": False, "cabling": True}))

    assert "2 devices rely on one source" in html and "printer, nas" in html
    assert "Add your switch (SNMP)" in html and 'href="/settings"' in html
    assert "20 devices aren't on the cabling map" in html and 'href="/cabling"' in html

    html = unescape(render_coverage_page(data, setup={"snmp": True, "cabling": True}))
    assert "Add your switch (SNMP)" not in html and "14 devices have an unknown connection" in html

    html = unescape(render_coverage_page(data, setup={"snmp": True, "cabling": False}))
    assert "cabling map" not in html

    data["off_map"] = None                                  # no wiring snapshot yet: no row, even with cabling on
    assert "cabling map" not in unescape(render_coverage_page(data, setup={"snmp": True, "cabling": True}))


def test_done_rows_and_quiet_link():

    html = render_coverage_page(coverage_data())

    assert "Every known device has been seen" in html and "No device has gone quiet" in html

    html = render_coverage_page(coverage_data(quiet=[device(9, "garden-camera", state="known", status="quiet")]))

    assert "1 device has gone quiet" in html and 'href="/triage"' in html and "garden-camera" not in html


def test_failed_run_note_kept():

    assert "A failed run never makes devices look quiet" in render_coverage_page(coverage_data())


def test_headline_never_all_clear_while_a_source_is_failing():

    data = coverage_data(multi=3, single_source=[])
    assert 'class="hero cov-head ok"' in render_coverage_page(data)

    data["runs"]["unifi"] = data["week"]("unifi", bad=(6,), error="login timed out")
    data["sources"] = latest(data["runs"])
    html = unescape(render_coverage_page(data))

    assert 'class="hero cov-head attention"' in html
    assert "UniFi is failing, so some devices may be missing" in html
