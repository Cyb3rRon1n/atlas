import pytest

from atlas.events import EventBus
from atlas.plugins.base import AtlasPlugin
from atlas.plugins.loader import discover_plugins
from atlas.plugins.manager import PluginManager


def test_atlas_plugin_cannot_be_instantiated_directly():

    with pytest.raises(TypeError):
        AtlasPlugin()


class FakeRuntime:

    def __init__(self):
        self.events = EventBus()


class FakePlugin(AtlasPlugin):

    name = "Fake"
    version = "0.0.1"

    def initialize(self, runtime):
        self.initialized_with = runtime

    def discover(self):
        return {"fake": True}


def test_plugin_manager_initialize_publishes_loaded_event():

    manager = PluginManager()
    manager.register(FakePlugin())

    runtime = FakeRuntime()
    received = []

    runtime.events.subscribe("atlas.plugin.loaded", received.append)

    manager.initialize(runtime)

    assert len(received) == 1
    assert received[0].payload == {"plugin": "Fake"}
    assert manager.get_plugins()[0].initialized_with is runtime


def test_plugin_manager_discover_all_aggregates_results():

    manager = PluginManager()
    manager.register(FakePlugin())

    assert manager.discover_all() == {"Fake": {"fake": True}}


def test_discover_plugins_finds_docker_plugin():

    plugins = discover_plugins()

    names = [p.name for p in plugins]

    assert "Docker" in names
