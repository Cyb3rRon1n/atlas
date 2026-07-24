from atlas.plugins.base import AtlasPlugin
from atlas.plugins.loader import discover_plugins
from atlas.events import AtlasEvent


class PluginManager:
    """
    Registers and manages Atlas plugins.
    """

    def __init__(self):
        self._plugins = []

    def register(self, plugin: AtlasPlugin):
        self._plugins.append(plugin)

    def initialize(self, runtime):
        """
        Initialize all registered plugins.
        """

        self.runtime = runtime

        for plugin in self._plugins:

            plugin.initialize(runtime)

            runtime.events.publish(
                AtlasEvent(
                    event_type="atlas.plugin.loaded",
                    source="PluginManager",
                    payload={
                        "plugin": plugin.name
                    }
                )
            )

    def get_plugins(self):
        return self._plugins

    def load_plugins(self):
        """
        Automatically discover and register plugins.
        """

        for plugin in discover_plugins():
            self.register(plugin)

    def discover_all(self):
        """
        Run discovery on all plugins.
        """

        data = {}

        for plugin in self._plugins:
            data[plugin.name] = plugin.discover()

        return data
