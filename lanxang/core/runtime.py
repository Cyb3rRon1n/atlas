from lanxang.core.context import AtlasContext
from lanxang.config import load_config
from lanxang.events import EventBus
from lanxang.intelligence.context import AtlasEnvironmentContext
from lanxang.listeners import DatabaseListener


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
