from collections import defaultdict

from atlas.events.event import AtlasEvent


class EventBus:
    """
    Publish/subscribe event bus.
    """

    def __init__(self):

        self._subscribers = defaultdict(list)


    def subscribe(
        self,
        event_type,
        callback
    ):

        self._subscribers[event_type].append(
            callback
        )


    def publish(
        self,
        event: AtlasEvent
    ):

        listeners = (
            self._subscribers.get(
                event.event_type,
                []
            )
            +
            self._subscribers.get(
                "*",
                []
            )
        )

        for callback in listeners:

            callback(event)
