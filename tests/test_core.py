from atlas.core.context import AtlasContext
from atlas.core.registry import ModuleRegistry
from atlas.core.runtime import AtlasRuntime
from atlas.events import EventBus
from atlas.intelligence.context import AtlasEnvironmentContext


def test_atlas_context_defaults_are_empty_dicts():

    context = AtlasContext()

    assert context.config == {}
    assert context.inventory == {}
    assert context.docker == {}
    assert context.proxmox == {}
    assert context.services == {}
    assert context.health == {}


def test_module_registry_register_get_all():

    registry = ModuleRegistry()
    registry.register("docker", "docker-module")

    assert registry.get("docker") == "docker-module"
    assert registry.get("missing") is None
    assert registry.all() == {"docker": "docker-module"}


def test_atlas_runtime_wires_context_environment_and_events(isolated_cwd):

    runtime = AtlasRuntime()

    assert runtime.get_context().config["name"] == "atlas-node"
    assert isinstance(runtime.get_environment(), AtlasEnvironmentContext)
    assert isinstance(runtime.events, EventBus)
