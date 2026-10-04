from atlas.devices.wiring import effective_connection


def device(connection="unknown", kind="other", sightings=None):

    return {"connection": connection, "kind": kind, "sightings": sightings or []}


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


def test_junk_or_missing_mac_never_raises():

    assert effective_connection(device(sightings=[{"mac": "zz"}, {"mac": None}])) == ("unknown", False)
