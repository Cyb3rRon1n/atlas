from abc import ABC, abstractmethod


class AtlasPlugin(ABC):
    """
    Base class for all Atlas plugins.
    """

    name = "Unknown Plugin"
    version = "0.1.0"

    # Which AtlasEnvironmentContext field this plugin's discover()
    # result belongs under (e.g. "containers", "virtualization").
    # "unknown" is a deliberately invalid default - update() silently
    # no-ops on a category it doesn't recognize, so a plugin that
    # forgets to set this loses its data rather than clobbering
    # another plugin's category.
    category = "unknown"

    @abstractmethod
    def initialize(self, runtime):
        """Initialize the plugin with the Atlas runtime."""
        raise NotImplementedError

    @abstractmethod
    def discover(self):
        """Return structured discovery information."""
        raise NotImplementedError
