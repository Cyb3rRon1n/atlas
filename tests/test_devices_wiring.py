from atlas.devices.wiring import effective_connection


def device(connection="unknown", kind="other", name="device", sightings=None):

    return {"connection": connection, "kind": kind, "name": name, "sightings": sightings or []}


def test_operator_value_always_wins():

    assert effective_connection(device(connection="wired", sightings=[{"mac": "da:a1:19:00:00:01"}])) == \
        ("wired", False)


def test_locally_administered_mac_is_guessed_wireless():

    assert effective_connection(device(sightings=[{"mac": "da:a1:19:00:00:01"}])) == ("wireless", True)


def test_globally_unique_mac_on_other_kind_is_unknown():

    assert effective_connection(device(sightings=[{"mac": "00:11:32:aa:bb:cc"}])) == ("unknown", False)


def test_phone_kind_is_guessed_wireless_even_with_a_global_mac():

    assert effective_connection(device(kind="phone", sightings=[{"mac": "00:11:32:aa:bb:cc"}])) == \
        ("wireless", True)


def test_iot_kind_is_guessed_wireless_even_with_a_global_mac():

    assert effective_connection(device(kind="iot", sightings=[{"mac": "00:11:32:aa:bb:cc"}])) == \
        ("wireless", True)


def test_wlan_in_device_name_is_guessed_wireless():

    assert effective_connection(device(name="wlan0", sightings=[{"mac": "00:11:32:aa:bb:cc"}])) == \
        ("wireless", True)


def test_wlan_in_a_sighting_hostname_is_guessed_wireless():

    assert effective_connection(device(sightings=[{"mac": "00:11:32:aa:bb:cc", "hostname": "iot-WLAN-bridge"}])) == \
        ("wireless", True)


def test_proxmox_guest_with_a_locally_administered_mac_stays_unknown():
    """VMs/LXCs can have locally administered MACs by nature of being virtual -
    that's never evidence of wireless, so a proxmox sighting short-circuits the
    guess entirely, even if some other sighting on the same device would qualify."""

    assert effective_connection(device(sightings=[{"source": "proxmox", "mac": "da:a1:19:00:00:01"}])) == \
        ("unknown", False)


def test_junk_or_missing_mac_never_raises():

    assert effective_connection(device(sightings=[{"mac": "zz"}, {"mac": None}])) == ("unknown", False)


def test_qemu_virtual_nic_prefix_is_not_guessed_wireless():
    """52:54:00 is QEMU/libvirt's default MAC prefix - its locally administered bit
    comes from being virtual, same reasoning as the proxmox-sighting short-circuit."""

    assert effective_connection(device(sightings=[{"mac": "52:54:00:12:34:56"}])) == ("unknown", False)


def test_docker_virtual_nic_prefix_is_not_guessed_wireless():

    assert effective_connection(device(sightings=[{"mac": "02:42:ac:11:00:02"}])) == ("unknown", False)


def test_virtual_nic_prefix_match_is_case_insensitive():

    assert effective_connection(device(sightings=[{"mac": "52:54:00:AB:CD:EF".upper()}])) == ("unknown", False)
    assert effective_connection(device(sightings=[{"mac": "02:42:AC:11:00:02".lower()}])) == ("unknown", False)
