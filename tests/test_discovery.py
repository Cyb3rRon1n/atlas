from unittest.mock import patch

from atlas.discovery import run_discovery
from atlas.discovery.hardware import collect_hardware
from atlas.discovery.network import collect_network
from atlas.discovery.storage import collect_storage
from atlas.discovery.system import collect_system


def test_collect_system_returns_expected_keys():

    system = collect_system()

    for key in ("hostname", "os", "distribution", "kernel", "architecture"):
        assert key in system
        assert isinstance(system[key], str)


def test_collect_hardware_returns_expected_shape():

    hardware = collect_hardware()

    assert set(hardware.keys()) == {"cpu", "memory"}
    assert isinstance(hardware["cpu"]["physical_cores"], int)
    assert isinstance(hardware["memory"]["total_gb"], float)
    assert 0 <= hardware["memory"]["used_percent"] <= 100


def test_collect_storage_returns_list_of_drives():

    drives = collect_storage()

    assert isinstance(drives, list)

    for drive in drives:
        assert "device" in drive
        assert "mountpoint" in drive
        assert 0 <= drive["used_percent"] <= 100


def test_collect_network_uses_mocked_resolution():
    """
    Own-hostname reverse DNS resolution is unreliable in minimal CI
    network namespaces, so gethostbyname_ex is mocked while the real
    hostname is still used.
    """

    with patch(
        "atlas.discovery.network.socket.gethostbyname_ex",
        return_value=("sentinel", [], ["192.168.1.10"])
    ):

        network = collect_network()

    assert network["addresses"] == ["192.168.1.10"]
    assert isinstance(network["hostname"], str)


def test_run_discovery_merges_all_categories():

    with patch(
        "atlas.discovery.network.socket.gethostbyname_ex",
        return_value=("sentinel", [], ["192.168.1.10"])
    ):

        data = run_discovery()

    assert set(data.keys()) == {"system", "hardware", "storage", "network"}
