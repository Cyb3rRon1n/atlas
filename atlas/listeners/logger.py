from atlas.events import EventBus


class EventLogger:
    """
    Basic Atlas event logger.
    """

    def register(self, bus: EventBus):

        bus.subscribe(
            "atlas.plugin.loaded",
            self.plugin_loaded
        )

    def plugin_loaded(self, event):

        print(
            f"[EVENT] Plugin loaded: "
            f"{event.payload['plugin']}"
        )
