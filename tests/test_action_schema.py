from atlas.intelligence.providers.base import (
    ACTION_OBJECT_SCHEMA,
    ACTION_SCHEMA,
    ANALYSIS_SCHEMA,
    CHAT_SCHEMA,
    PLAN_SCHEMA,
    chat_reply_from_dict,
    plan_from_dict,
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


def test_action_schema_and_plan_schema_reuse_the_same_action_object_schema():

    assert ACTION_SCHEMA["anyOf"][0] is ACTION_OBJECT_SCHEMA

    plan_object_schema = PLAN_SCHEMA["anyOf"][0]
    step_schema = plan_object_schema["properties"]["steps"]["items"]

    assert step_schema["properties"]["action"] is ACTION_OBJECT_SCHEMA


def test_plan_schema_step_action_is_not_nullable():
    """
    Unlike the standalone `action` field, a plan step's action isn't
    optional - a step without one doesn't mean anything.
    """

    plan_object_schema = PLAN_SCHEMA["anyOf"][0]
    step_schema = plan_object_schema["properties"]["steps"]["items"]

    assert "anyOf" not in step_schema["properties"]["action"]
    assert step_schema["properties"]["action"]["type"] == "object"


def test_plan_schema_is_nullable_at_the_top_level():

    assert {"type": "null"} in PLAN_SCHEMA["anyOf"]


def test_analysis_schema_and_chat_schema_reuse_the_same_plan_schema():

    assert ANALYSIS_SCHEMA["properties"]["plan"] is PLAN_SCHEMA
    assert CHAT_SCHEMA["properties"]["plan"] is PLAN_SCHEMA
    assert "plan" in ANALYSIS_SCHEMA["required"]
    assert "plan" in CHAT_SCHEMA["required"]


def test_plan_from_dict_returns_none_when_missing_or_null():

    assert plan_from_dict(None) is None
    assert plan_from_dict({}) is None


def test_plan_from_dict_builds_nested_plan():

    data = {
        "summary": "Recover the media stack",
        "steps": [
            {
                "action": {
                    "type": "stop_container",
                    "target": "sonarr",
                    "cpus": None,
                    "memory": None
                },
                "rationale": "sonarr is holding a lock radarr needs"
            },
            {
                "action": {
                    "type": "restart_container",
                    "target": "radarr",
                    "cpus": None,
                    "memory": None
                },
                "rationale": "will pick up cleanly once sonarr is stopped"
            }
        ]
    }

    plan = plan_from_dict(data)

    assert plan.summary == "Recover the media stack"
    assert len(plan.steps) == 2
    assert plan.steps[0].action.type == "stop_container"
    assert plan.steps[0].action.target == "sonarr"
    assert plan.steps[0].rationale == "sonarr is holding a lock radarr needs"
    assert plan.steps[1].action.type == "restart_container"
