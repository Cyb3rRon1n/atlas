from atlas.discovery.system import collect_system
from atlas.discovery.hardware import collect_hardware
from atlas.discovery.storage import collect_storage
from atlas.discovery.network import collect_network


def run_discovery():

    return {
        "system": collect_system(),
        "hardware": collect_hardware(),
        "storage": collect_storage(),
        "network": collect_network(),
    }

