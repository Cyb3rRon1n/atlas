from datetime import datetime


class AtlasEnvironmentContext:
    """
    Represents Atlas' current understanding
    of an environment.
    """

    def __init__(self):

        self.timestamp = datetime.utcnow()

        self.system = {}
        self.hardware = {}
        self.storage = {}
        self.network = {}
        self.services = {}
        self.containers = {}
        self.virtualization = {}


    def ingest_discovery(self, data):
        """
        Load discovery results into context.
        """

        if "system" in data:
            self.system = data["system"]

        if "hardware" in data:
            self.hardware = data["hardware"]

        if "storage" in data:
            self.storage = data["storage"]

        if "network" in data:
            self.network = data["network"]

        self.timestamp = datetime.utcnow()


    def update(self, category, data):

        if hasattr(self, category):

            setattr(
                self,
                category,
                data
            )


    def summary(self):

        return {
            "timestamp": str(self.timestamp),
            "system": self.system,
            "hardware": self.hardware,
            "storage": self.storage,
            "network": self.network,
            "services": self.services,
            "containers": self.containers,
            "virtualization": self.virtualization,
        }
