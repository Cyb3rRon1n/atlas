from atlas.plugins import AtlasPlugin
from atlas.libvirt import collect_guests


class LibvirtPlugin(AtlasPlugin):
    """
    Atlas libvirt/KVM Plugin
    """

    name = "Libvirt"
    version = "0.1.0"
    category = "virtualization"

    def __init__(self):
        self.runtime = None

    def initialize(self, runtime):
        self.runtime = runtime

    def discover(self):
        return collect_guests()
