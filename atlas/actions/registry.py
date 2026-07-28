from dataclasses import dataclass
from typing import Callable

from atlas.actions.targets import known_container_names, known_guest_ids


@dataclass
class ActionDefinition:
    """
    Everything AtlasAnalyzer and the CLI need to know about an action
    type without knowing anything about Docker or Proxmox specifically.
    """

    type: str
    command_template: str
    known_targets: Callable[[dict], set[str]]


ACTIONS: dict[str, ActionDefinition] = {
    "restart_container": ActionDefinition(
        type="restart_container",
        command_template="atlas restart {target}",
        known_targets=known_container_names
    ),
    "restart_guest": ActionDefinition(
        type="restart_guest",
        command_template="atlas proxmox restart {target}",
        known_targets=known_guest_ids
    ),
    "stop_container": ActionDefinition(
        type="stop_container",
        command_template="atlas stop {target}",
        known_targets=known_container_names
    ),
}
