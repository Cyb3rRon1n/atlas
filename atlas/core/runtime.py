from atlas.core.context import AtlasContext
from atlas.config import load_config
from atlas.events import EventBus
from atlas.listeners import EventLogger, DatabaseListener
from atlas.listeners.database import DatabaseListener

class AtlasRuntime:
    """
    Central runtime object.
    """

    def __init__(self):

        self.context = AtlasContext()

        self.context.config = (
            load_config().model_dump()
        )

        self.events = EventBus()

        self.listeners = []

        self.register_listeners()


    def register_listeners(self):

        logger = EventLogger()

        logger.register(
            self.events
        )

        database = DatabaseListener()

        database.register(
            self.events
        )

        self.listeners.extend(
            [
                logger,
                database,
            ]
        )

    def get_context(self):

        return self.context
