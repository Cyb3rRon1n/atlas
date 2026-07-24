from atlas.plugins.base import AtlasPlugin


class PluginManager:
    """
    Registers and manages Atlas plugins.
    """

    def __init__(self):
        self._plugins = []

    def register(self, plugin: AtlasPlugin):
        self._plugins.append(plugin)

    def get_plugins(self):
        return self._plugins
