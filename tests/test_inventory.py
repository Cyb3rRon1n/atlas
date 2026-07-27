from atlas.inventory import load_inventory, save_inventory


SAMPLE_DATA = {
    "system": {"hostname": "sentinel"},
    "hardware": {"cpu": {"physical_cores": 4}},
}


def test_load_inventory_returns_none_when_missing(isolated_cwd):

    assert load_inventory() is None


def test_save_then_load_inventory_round_trips(isolated_cwd):

    output = save_inventory(SAMPLE_DATA)

    assert output.exists()

    loaded = load_inventory()

    assert loaded == SAMPLE_DATA
