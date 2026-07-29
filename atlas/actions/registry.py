from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from atlas.actions.targets import known_container_names, known_guest_ids

if TYPE_CHECKING:
    from atlas.intelligence.providers.base import SuggestedAction


@dataclass
class ActionDefinition:
    """
    Everything AtlasAnalyzer and the CLI need to know about an action
    type without knowing anything about Docker or Proxmox specifically.
    """

    type: str
    command_template: Callable[["SuggestedAction"], str]
    known_targets: Callable[[dict], set[str]]


ACTIONS: dict[str, ActionDefinition] = {
    "restart_container": ActionDefinition(
        type="restart_container",
        command_template=lambda a: f"atlas restart {a.target}",
        known_targets=known_container_names
    ),
    "restart_guest": ActionDefinition(
        type="restart_guest",
        command_template=lambda a: f"atlas proxmox restart {a.target}",
        known_targets=known_guest_ids
    ),
    "stop_container": ActionDefinition(
        type="stop_container",
        command_template=lambda a: f"atlas stop {a.target}",
        known_targets=known_container_names
    ),
    "resize_container": ActionDefinition(
        type="resize_container",
        command_template=lambda a: (
            f"atlas resize {a.target}"
            + (f" --cpus {a.cpus}" if a.cpus else "")
            + (f" --memory {a.memory}" if a.memory else "")
        ),
        known_targets=known_container_names
    ),
}


def is_action_grounded(action: "SuggestedAction", environment: dict) -> bool:
    """
    Shared by AtlasAnalyzer and AtlasAgent (single actions and, now,
    every step of a plan) so the "is this a real action type with a
    target Atlas actually observed" check lives in one place - it was
    duplicated verbatim between the two before a plan's steps needed
    the exact same check a third and fourth time.
    """

    definition = ACTIONS.get(action.type)

    return bool(definition) and action.target in definition.known_targets(environment)
