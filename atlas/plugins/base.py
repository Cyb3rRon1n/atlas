from abc import ABC, abstractmethod


class AtlasPlugin(ABC):
    """
    Base class for all Atlas plugins.
    """

    name = "Unknown Plugin"
    version = "0.1.0"

    @abstractmethod
    def initialize(self, runtime):
        """Initialize the plugin with the Atlas runtime."""
        raise NotImplementedError

    @abstractmethod
    def discover(self):
        """Return structured discovery information."""
        raise NotImplementedError
