from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from atlas.actions.targets import known_container_names, known_guest_ids
from atlas.config import load_config
from atlas.docker import resize_container, restart_container, stop_container
from atlas.proxmox import connect, get_guest_info, resize_guest, restart_guest, stop_guest

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
    executor: Callable[["SuggestedAction"], dict]


def _execute_guest_action(action, manager_fn, **extra_kwargs):
    """
    Shared by the three Proxmox executors below - each needs a
    connected client plus a discovery lookup (for node/guest_type)
    before it can call its manager function, exactly what each
    standalone atlas proxmox restart/stop/resize command already does
    inline. Written once here instead of three times.
    """

    settings = load_config()
    proxmox_settings = settings.proxmox

    client = connect(
        proxmox_settings.host,
        proxmox_settings.user,
        password=proxmox_settings.password,
        token_name=proxmox_settings.token_name,
        token_value=proxmox_settings.token_value,
        verify_ssl=proxmox_settings.verify_ssl
    )

    if not client:
        return {
            "success": False,
            "error": "Unable to connect to Proxmox"
        }

    vmid = int(action.target)

    info = get_guest_info(client, vmid)

    if not info["found"]:
        return info

    return manager_fn(client, info["node"], vmid, info["type"], **extra_kwargs)


ACTIONS: dict[str, ActionDefinition] = {
    "restart_container": ActionDefinition(
        type="restart_container",
        command_template=lambda a: f"atlas restart {a.target}",
        known_targets=known_container_names,
        executor=lambda a: restart_container(a.target)
    ),
    "restart_guest": ActionDefinition(
        type="restart_guest",
        command_template=lambda a: f"atlas proxmox restart {a.target}",
        known_targets=known_guest_ids,
        executor=lambda a: _execute_guest_action(a, restart_guest)
    ),
    "stop_container": ActionDefinition(
        type="stop_container",
        command_template=lambda a: f"atlas stop {a.target}",
        known_targets=known_container_names,
        executor=lambda a: stop_container(a.target)
    ),
    "resize_container": ActionDefinition(
        type="resize_container",
        command_template=lambda a: (
            f"atlas resize {a.target}"
            + (f" --cpus {a.cpus}" if a.cpus else "")
            + (f" --memory {a.memory}" if a.memory else "")
        ),
        known_targets=known_container_names,
        executor=lambda a: resize_container(
            a.target,
            cpus=float(a.cpus) if a.cpus else None,
            mem_limit=a.memory
        )
    ),
    "stop_guest": ActionDefinition(
        type="stop_guest",
        command_template=lambda a: f"atlas proxmox stop {a.target}",
        known_targets=known_guest_ids,
        executor=lambda a: _execute_guest_action(a, stop_guest)
    ),
    "resize_guest": ActionDefinition(
        type="resize_guest",
        command_template=lambda a: (
            f"atlas proxmox resize {a.target}"
            + (f" --cpus {a.cpus}" if a.cpus else "")
            + (f" --memory {a.memory}" if a.memory else "")
        ),
        known_targets=known_guest_ids,
        executor=lambda a: _execute_guest_action(
            a, resize_guest,
            cpus=float(a.cpus) if a.cpus else None,
            memory=a.memory
        )
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


def execute_action(action: "SuggestedAction") -> dict:
    """
    Generic dispatcher used by the "run this plan?" loop - looks up
    the matching ActionDefinition and calls its executor, so the
    caller never branches on action.type itself. An unrecognized
    type returns an error dict rather than raising, same as every
    executor it dispatches to.
    """

    definition = ACTIONS.get(action.type)

    if not definition:
        return {
            "success": False,
            "error": f"Unknown action type: {action.type}"
        }

    return definition.executor(action)
