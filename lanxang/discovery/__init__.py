from lanxang.discovery.system import collect_system
from lanxang.discovery.hardware import collect_hardware
from lanxang.discovery.storage import collect_storage
from lanxang.discovery.network import collect_network


def run_discovery():

    return {
        "system": collect_system(),
        "hardware": collect_hardware(),
        "storage": collect_storage(),
        "network": collect_network(),
    }

