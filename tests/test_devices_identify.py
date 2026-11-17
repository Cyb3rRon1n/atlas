from datetime import datetime

from atlas.devices import identify
from atlas.web.devices_pages import render_devices_page

OUI = ('Registry,Assignment,Organization Name,Organization Address\n'
       'MA-L,240AC4,Espressif Inc.,"Shanghai CN"\n'
       'MA-L,B827EB,Raspberry Pi Foundation,"Cambridge GB"\n'
       'MA-L,001CC2,PART II RESEARCH,"US"\n')


def _device(id_, mac, hostname=None, name=None, state="new"):
    return {"id": id_, "name": name or f"192.0.2.{id_}", "ip": f"192.0.2.{id_}", "kind": "other", "state": state,
            "status": "seen", "last_seen": None,
            "sightings": [{"source": "lan", "mac": mac, "hostname": hostname, "first_seen": "2026-11-10T08:00:00"}]}


def test_parse_maker_private_and_hostname_clues():
    table = identify.parse_oui(OUI)
    assert table["24:0A:C4"] == "Espressif Inc." and len(table) == 3
    assert identify.short_maker("Espressif Inc.") == "Espressif"
    assert identify.short_maker("TP-LINK TECHNOLOGIES CO.,LTD.") == "TP-Link"
    assert identify.private("fe:0a:b0:11:22:33") and not identify.private("24:0a:c4:11:22:33")
    assert not identify.private("bc:24:11:00:00:01")                         # Proxmox virtual NIC
    assert identify.clean_hostname("55TCLRokuTV.localdomain") == "55TCLRokuTV"


def test_guesses_from_maker_ports_private_and_hostname():
    table = identify.parse_oui(OUI)
    esp = identify.clues(_device(1, "24:0a:c4:00:00:01"), table)
    assert identify.guess(esp) == ("Espressif smart device", "iot")
    phone = identify.clues(_device(2, "fe:0a:b0:00:00:02"), table)
    assert phone["maker"] is None and identify.guess(phone) == ("Phone, tablet or laptop", "phone")
    printer = identify.clues(_device(3, "00:1c:c2:00:00:03"), table, open_ports=[80, 9100])
    assert identify.guess(printer)[1] == "other" and "printer (9100)" in printer["ports"]
    named = identify.clues(_device(4, "b8:27:eb:00:00:04", "pihole.lan"), table)
    assert identify.guess(named) == ("pihole", "server")


def test_place_from_cabling_map_and_page_shows_clues():
    devices = [_device(1, "24:0a:c4:00:00:01"), _device(2, "fe:0a:b0:00:00:02"),
               _device(9, "aa:00:00:00:00:09", name="Office PC", state="known")]
    snapshot = {"nodes": [{"id": "s:core", "name": "core-switch", "kind": "switch"},
                          {"id": "h:1", "name": "x", "kind": "host", "mac": "24:0A:C4:00:00:01"},
                          {"id": "b:ap", "name": "house Wi-Fi", "kind": "bridge", "behind": ["192.0.2.2"]}],
                "links": [{"a": "s:core", "a_port": "gi9", "b": "h:1", "b_port": None}]}
    hints = identify.for_devices(devices, identify.parse_oui(OUI), {"1": {"open": [80]}}, snapshot)
    assert set(hints) == {1, 2}
    assert hints[1]["clues"]["place"] == "core-switch port gi9" and hints[2]["clues"]["place"] == "behind house Wi-Fi"
    page = render_devices_page(devices, hints)
    assert 'value="Espressif smart device"' in page and '<option value="iot" selected>' in page
    assert "made by <b>Espressif</b>" in page and "on <b>core-switch port gi9</b>" in page
    assert "private Wi-Fi address" in page and "first seen 2026-11-10" in page and 'data-kind-from="kind-1"' in page


def test_refresh_downloads_monthly_and_never_raises(tmp_path):
    path = tmp_path / "oui.csv"
    big = OUI + "".join(f"MA-L,{i:06X},Maker {i},x\n" for i in range(1200))

    class Reply:
        text = big
        def raise_for_status(self):
            pass

    now = datetime(2026, 11, 16)
    assert identify.refresh(now, path, get=lambda *a, **k: Reply()) and len(identify.makers(path)) > 1000
    assert not identify.refresh(now, path, get=lambda *a, **k: 1 / 0)          # fresh: not fetched again
    assert not identify.refresh(now, tmp_path / "x.csv", get=lambda *a, **k: 1 / 0)   # offline: just no names
