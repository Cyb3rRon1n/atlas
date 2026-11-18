from lanxang.events import EventBus
from lanxang.knowledge.store import KnowledgeStore


class DatabaseListener:
    """
    Saves Lanxang events into persistent storage.
    """

    def __init__(self):

        self.store = KnowledgeStore()


    def register(
        self,
        bus: EventBus
    ):

        bus.subscribe(
            "*",
            self.save
        )


    def save(self, event):

        self.store.save_event(
            event
        )
