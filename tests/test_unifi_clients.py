from atlas.config.models import AtlasConfig
from atlas.devices import Sighting
from atlas.devices import identify
from atlas.devices.store import InventoryStore
from atlas.web.devices_pages import _clues
from atlas.wiring.scan import run_scan
from atlas.wiring.store import WiringStore
from atlas.wiring.unifi import parse_unifi, sightings

AP = {"mac": "02:00:00:00:00:a1", "name": "office-ap", "type": "uap", "model": "U6-Lite", "ip": "192.0.2.3"}
CLIENTS = [
    {"mac": "02:00:00:00:00:41", "ip": "192.0.2.41", "name": "Den TV", "hostname": "android-1234", "is_wired": False,
     "essid": "home", "ap_mac": "02:00:00:00:00:a1", "signal": -61, "radio": "na", "network": "Default"},
    {"mac": "02:00:00:00:00:42", "ip": "192.0.2.42", "hostname": "printer", "is_wired": True, "network": "Default",
     "sw_mac": "02:00:00:00:00:10", "sw_port": 4},
    {"mac": "02:00:00:00:00:43", "hostname": "", "is_wired": False, "essid": "visitors", "is_guest": True}]


def test_every_client_is_kept_with_wifi_details():
    found = parse_unifi([AP], CLIENTS)
    assert [c["mac"] for c in found["clients"]] == ["02:00:00:00:00:42"]             # the map's wired list as before
    tv = found["everyone"][0]
    assert tv["name"] == "Den TV" and tv["wifi"] == {"ssid": "home", "ap": "office-ap", "signal": -61,
                                                     "band": "5 GHz"}
    assert found["everyone"][1]["wifi"] is None and found["everyone"][2]["guest"]
    seen = sightings(found)
    assert seen[0] == Sighting("unifi", "02:00:00:00:00:41", ip="192.0.2.41", mac="02:00:00:00:00:41",
                               hostname="Den TV", detail={"unifi": {
                                   "name": "Den TV", "hostname": "android-1234", "network": "Default",
                                   "wifi": tv["wifi"]}})
    assert seen[2].hostname is None and seen[2].ip is None


def test_wiring_scan_links_unifi_clients_to_devices_by_mac(temp_db, tmp_path):
    inventory = InventoryStore(temp_db)
    inventory.record_run("lan", [Sighting("lan", "02:00:00:00:00:41", ip="192.0.2.41", mac="02:00:00:00:00:41")])
    settings = AtlasConfig(wiring={"enabled": True, "cabling_file": str(tmp_path / "cabling.yaml"),
                                   "unifi": {"enabled": True, "url": "https://192.0.2.1"}})
    run_scan(settings, WiringStore(temp_db), [], env={}, fetch=lambda *a, **k: parse_unifi([AP], CLIENTS))
    devices = {d["ip"]: d for d in inventory.devices()}
    tv = devices["192.0.2.41"]
    assert {s["source"] for s in tv["sightings"]} == {"lan", "unifi"}             # one device, not two
    hint = identify.for_devices([tv], {}, {}, None)[tv["id"]]
    assert hint["name"] == "Den TV"                                             # UniFi's name wins
    line = _clues(tv, hint)
    assert "UniFi calls it <b>Den TV</b>" in line and "on Wi-Fi <b>home</b> via office-ap (5 GHz, -61 dBm)" in line
