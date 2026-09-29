from datetime import datetime, timedelta

from atlas.devices import Sighting
from atlas.devices.linking import match
from atlas.devices.status import device_status


def known(device_id, name, source, ip=None, mac=None, hostname=None):

    return {"device_id": device_id, "device_name": name, "source": source, "ip": ip, "mac": mac, "hostname": hostname}


def test_same_mac_from_another_source_links():

    assert match(Sighting("proxmox", "pve:200", mac="aa:01"), [known(1, "x", "lan", mac="aa:01")]) == ("link", 1)


def test_lan_ip_matching_a_configured_host_links():

    assert match(Sighting("lan", "aa:57", ip="192.168.10.57"),
                 [known(3, "mediabox", "manual", ip="192.168.10.57")]) == ("link", 3)


def test_proxmox_ip_matching_lan_links():

    assert match(Sighting("proxmox", "pve:110", ip="192.168.10.134"),
                 [known(4, "media-tools", "lan", ip="192.168.10.134")]) == ("link", 4)


def test_two_lan_sightings_on_one_ip_do_not_link():

    # DHCP reuse: a different MAC on a known lan IP is a different device.
    assert match(Sighting("lan", "aa:02", ip="192.168.10.50"),
                 [known(5, "old", "lan", ip="192.168.10.50", mac="aa:01")]) == ("new", None)


def test_name_match_is_only_a_suggestion():

    assert match(Sighting("proxmox", "pve:200", hostname="mediabox"),
                 [known(3, "mediabox", "manual", ip="192.168.10.57")]) == ("suggest", 3)


def test_hostname_domain_is_ignored_for_suggestions():

    assert match(Sighting("lan", "aa:09", hostname="MediaBox.lan"),
                 [known(3, "x", "proxmox", hostname="mediabox")]) == ("suggest", 3)


def test_unknown_is_new():

    assert match(Sighting("lan", "aa:77", ip="192.168.10.77"), []) == ("new", None)


def test_ip_named_device_does_not_suggest_match_on_split_octet():
    """Two different IP-named devices in the same /8 (e.g. 192.x and 192.y) used
    to both split down to "192" and wrongly suggest a merge with each other."""

    assert match(Sighting("lan", "aa:88", hostname="192.168.10.88"),
                 [known(6, "192.168.10.200", "lan", hostname="192.168.10.200")]) == ("new", None)


NOW = datetime(2026, 9, 29, 12, 0)
RUNS = {"lan": [NOW, NOW - timedelta(minutes=15), NOW - timedelta(minutes=30)]}


def test_seen_in_latest_run():

    assert device_status([{"source": "lan", "last_seen": NOW}], RUNS) == "seen"


def test_missing_only_latest_run_is_still_seen():

    assert device_status([{"source": "lan", "last_seen": NOW - timedelta(minutes=15)}], RUNS) == "seen"


def test_missing_last_two_runs_is_quiet():

    assert device_status([{"source": "lan", "last_seen": NOW - timedelta(minutes=30)}], RUNS) == "quiet"


def test_seen_by_any_source_wins():

    sightings = [{"source": "lan", "last_seen": NOW - timedelta(hours=5)},
                 {"source": "proxmox", "last_seen": NOW}]

    assert device_status(sightings, {**RUNS, "proxmox": [NOW]}) == "seen"


def test_source_without_two_runs_cannot_call_quiet():

    assert device_status([{"source": "lan", "last_seen": NOW - timedelta(hours=5)}], {"lan": [NOW]}) == "seen"


def test_manual_only_is_invisible():

    assert device_status([{"source": "manual", "last_seen": NOW}], RUNS) == "invisible"
