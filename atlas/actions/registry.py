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
