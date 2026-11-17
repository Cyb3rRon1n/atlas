import struct

from atlas.devices import discover, identify


def _label(name):
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def _rr(owner, kind, rdata):
    return _label(owner) + struct.pack(">HHIH", kind, 1, 120, len(rdata)) + rdata


def _txt(**pairs):
    return b"".join(bytes([len(f"{k}={v}")]) + f"{k}={v}".encode() for k, v in pairs.items())


def test_query_and_answer_parsing():
    query = discover.mdns_query(("_googlecast._tcp",))
    assert struct.unpack(">6H", query[:12])[2] == 1 and _label("_googlecast._tcp.local") in query
    answer = (struct.pack(">6H", 0, 0x8400, 0, 2, 0, 0)
              + _rr("_googlecast._tcp.local", 12, _label("Chromecast-abc._googlecast._tcp.local"))
              + _rr("Chromecast-abc._googlecast._tcp.local", 16, _txt(md="Chromecast Ultra", fn="Living Room TV")))
    found = {"services": set()}
    discover._collect_mdns(discover.parse_mdns(answer), found)
    assert found == {"services": {"_googlecast._tcp"}, "name": "Living Room TV", "model": "Chromecast Ultra"}


def test_compressed_names_and_bad_packets():
    head = struct.pack(">6H", 0, 0x8400, 0, 1, 0, 0)
    owner = _label("_ipp._tcp.local")
    pointer = struct.pack(">H", 0xC000 | 12)                      # points back at the owner name
    packet = head + owner + struct.pack(">HHIH", 12, 1, 120, 7) + b"\x04Desk" + pointer
    assert discover.parse_mdns(packet) == [("PTR", "_ipp._tcp.local", "Desk._ipp._tcp.local")]
    loop = head + struct.pack(">H", 0xC000 | 12) + b"\x00" * 10
    try:
        discover.parse_mdns(loop)
        raise AssertionError("a pointer loop must not hang")
    except ValueError:
        pass


def test_upnp_description_and_merge():
    xml = (b'<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>'
           b'<friendlyName>55" TCL Roku TV</friendlyName><manufacturer>TCL</manufacturer>'
           b'<modelName>55R635</modelName></device></root>')
    assert discover.parse_description(xml) == {"name": '55" TCL Roku TV', "maker": "TCL", "model": "55R635"}
    merged = discover.discover(ask_mdns=lambda t: {"192.0.2.5": {"services": {"_airplay._tcp"}}},
                               ask_ssdp=lambda t: {"192.0.2.5": {"name": "Den TV", "maker": "TCL", "model": "55R635"},
                                                   "192.0.2.6": {}})
    assert merged == {"192.0.2.5": {"name": "Den TV", "model": "55R635", "maker": "TCL", "services": ["_airplay._tcp"]}}
    assert discover.discover(ask_mdns=lambda t: 1 / 0, ask_ssdp=lambda t: {}) == {}


def test_announced_name_and_services_drive_the_guess():
    device = {"id": 1, "name": "192.0.2.5", "ip": "192.0.2.5", "kind": "other", "state": "new",
              "sightings": [{"source": "lan", "mac": "fe:00:00:00:00:01", "hostname": None,
                             "detail": {"announce": {"name": "Living Room TV", "model": "Chromecast Ultra",
                                                     "maker": None, "services": ["_googlecast._tcp"]}}}]}
    found = identify.clues(device, {})
    assert found["services"] == ["Chromecast"] and identify.guess(found) == ("Living Room TV", "tv")
    printer = dict(device, sightings=[{"source": "lan", "mac": None, "hostname": None, "detail": {"announce": {
        "name": None, "model": "HP LaserJet M404", "maker": "HP", "services": ["_ipp._tcp"]}}}])
    assert identify.guess(identify.clues(printer, {})) == ("HP LaserJet M404", "other")


def test_store_keeps_what_a_device_said_when_it_sleeps(temp_db):
    from atlas.devices import Sighting
    from atlas.devices.store import InventoryStore

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:00:00:00:00:01", ip="192.0.2.9", mac="aa:00:00:00:00:01",
                                      detail={"announce": {"name": "Den TV"}})])
    store.record_run("lan", [Sighting("lan", "aa:00:00:00:00:01", ip="192.0.2.9", mac="aa:00:00:00:00:01")])
    sighting = store.devices()[0]["sightings"][0]
    assert sighting["detail"]["announce"] == {"name": "Den TV"}


def test_generic_instance_names_are_not_names():
    found = {"services": set()}
    discover._collect_mdns([("PTR", "_spotify-connect._tcp.local", "SpotifyConnect (2)._spotify-connect._tcp.local"),
                            ("PTR", "_googlecast._tcp.local", "Chromecast-6f3a9b2c1d0e._googlecast._tcp.local")], found)
    assert "name" not in found
    discover._collect_mdns([("PTR", "_hap._tcp.local", "Porch Light (2)._hap._tcp.local")], found)
    assert found["name"] == "Porch Light"
