from atlas.core.context import AtlasContext
from atlas.config import load_config
from atlas.events import EventBus
from atlas.intelligence.context import AtlasEnvironmentContext
from atlas.listeners import DatabaseListener


class AtlasRuntime:
    """
    Central runtime object.
    """

    def __init__(self):

        self.context = AtlasContext()

        self.context.config = (
            load_config().model_dump()
        )

        self.environment = AtlasEnvironmentContext()

        self.events = EventBus()

        DatabaseListener().register(self.events)


    def get_context(self):

        return self.context


    def get_environment(self):

        return self.environment
