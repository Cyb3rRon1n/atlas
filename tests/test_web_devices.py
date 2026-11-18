

def test_triage_buttons_update_the_row_in_place_instead_of_reloading():
    """Keep / Ignore used to reload the page, folding the "Show N more" list shut every time."""

    from lanxang.web.devices_pages import ACTIONS_SCRIPT, render_devices_page

    device = {"id": 7, "name": "192.0.2.7", "ip": "192.0.2.7", "kind": "other", "state": "new", "status": "seen",
              "important": False, "tags": [], "notes": "", "connection": "unknown", "uplink_id": None,
              "suggested_merge_id": None, "last_seen": None, "sightings": []}
    html = render_devices_page([device])
    assert 'data-label="192.0.2.7"' in html
    assert "doneInPlace(row, button)" in ACTIONS_SCRIPT and "keepPlace()" in ACTIONS_SCRIPT
