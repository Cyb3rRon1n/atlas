from atlas.intelligence.providers.base import (
    ACTION_SCHEMA,
    ANALYSIS_SCHEMA,
    CHAT_SCHEMA,
    chat_reply_from_dict,
    recommendation_from_dict,
)


def test_action_schema_includes_cpus_and_memory_as_required_nullable():

    action_object_schema = ACTION_SCHEMA["anyOf"][0]

    assert "cpus" in action_object_schema["properties"]
    assert "memory" in action_object_schema["properties"]
    assert "cpus" in action_object_schema["required"]
    assert "memory" in action_object_schema["required"]

    assert action_object_schema["properties"]["cpus"]["anyOf"] == [
        {"type": "string"}, {"type": "null"}
    ]


def test_action_schema_includes_resize_container_in_type_enum():

    action_object_schema = ACTION_SCHEMA["anyOf"][0]

    assert "resize_container" in action_object_schema["properties"]["type"]["enum"]


def test_analysis_schema_and_chat_schema_reuse_the_same_action_schema():

    recommendation_action_schema = (
        ANALYSIS_SCHEMA["properties"]["recommendations"]["items"]
        ["properties"]["action"]
    )
    chat_action_schema = CHAT_SCHEMA["properties"]["action"]

    assert recommendation_action_schema is ACTION_SCHEMA
    assert chat_action_schema is ACTION_SCHEMA


def test_recommendation_from_dict_carries_cpus_and_memory():

    item = {
        "title": "Container 'plex' is throttled",
        "detail": "Pinned near its own CPU limit.",
        "severity": "warning",
        "action": {
            "type": "resize_container",
            "target": "plex",
            "cpus": "1.5",
            "memory": None
        }
    }

    recommendation = recommendation_from_dict(item)

    assert recommendation.action.cpus == "1.5"
    assert recommendation.action.memory is None


def test_chat_reply_from_dict_carries_cpus_and_memory():

    item = {
        "text": "I'd bump plex's memory limit.",
        "action": {
            "type": "resize_container",
            "target": "plex",
            "cpus": None,
            "memory": "512m"
        }
    }

    reply = chat_reply_from_dict(item)

    assert reply.action.cpus is None
    assert reply.action.memory == "512m"
