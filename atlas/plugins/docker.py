from atlas.plugins import AtlasPlugin
from atlas.docker import collect_containers


class DockerPlugin(AtlasPlugin):
    """
    Atlas Docker Plugin
    """

    name = "Docker"
    version = "0.1.0"

    def __init__(self):
        self.runtime = None

    def initialize(self, runtime):
        self.runtime = runtime

    def discover(self):
        return collect_containers()
