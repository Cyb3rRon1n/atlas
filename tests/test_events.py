from atlas.events import AtlasEvent, EventBus


def test_subscriber_receives_matching_event():

    bus = EventBus()
    received = []

    bus.subscribe(
        "atlas.discovery.completed",
        received.append
    )

    event = AtlasEvent(
        event_type="atlas.discovery.completed",
        source="test",
        payload={"ok": True}
    )

    bus.publish(event)

    assert received == [event]


def test_subscriber_does_not_receive_other_event_types():

    bus = EventBus()
    received = []

    bus.subscribe(
        "atlas.discovery.completed",
        received.append
    )

    bus.publish(
        AtlasEvent(
            event_type="atlas.plugin.loaded",
            source="test",
            payload={}
        )
    )

    assert received == []


def test_wildcard_subscriber_receives_every_event():

    bus = EventBus()
    received = []

    bus.subscribe("*", received.append)

    first = AtlasEvent(event_type="a", source="test", payload=1)
    second = AtlasEvent(event_type="b", source="test", payload=2)

    bus.publish(first)
    bus.publish(second)

    assert received == [first, second]


def test_event_gets_default_timestamp():

    event = AtlasEvent(
        event_type="atlas.plugin.loaded",
        source="test",
        payload={}
    )

    assert event.timestamp is not None
