from atlas.actions import ACTIONS, known_container_names, known_guest_ids
from atlas.intelligence.providers.base import SuggestedAction


def test_known_container_names_flattens_across_plugins():

    environment = {
        "containers": {
            "Docker": {
                "available": True,
                "containers": [
                    {"name": "plex", "status": "running"},
                    {"name": "sonarr", "status": "exited"},
                ]
            }
        }
    }

    assert known_container_names(environment) == {"plex", "sonarr"}


def test_known_container_names_empty_when_no_containers_key():

    assert known_container_names({"system": {}}) == set()


def test_known_guest_ids_flattens_vmids_as_strings():

    environment = {
        "virtualization": {
            "nodes": [{"name": "pve1", "status": "online"}],
            "guests": [
                {"vmid": 100, "name": "plex", "type": "qemu", "status": "running"},
                {"vmid": 101, "name": "pihole", "type": "lxc", "status": "stopped"},
            ]
        }
    }

    assert known_guest_ids(environment) == {"100", "101"}


def test_known_guest_ids_empty_when_no_virtualization_key():

    assert known_guest_ids({"system": {}}) == set()


def test_actions_registry_has_all_six_entries():

    assert set(ACTIONS.keys()) == {
        "restart_container", "restart_guest", "stop_container", "resize_container",
        "stop_guest", "resize_guest"
    }


def test_restart_container_action_wired_correctly():

    definition = ACTIONS["restart_container"]

    action = SuggestedAction(type="restart_container", target="plex")
    assert definition.command_template(action) == "atlas restart plex"
    assert definition.known_targets is known_container_names


def test_restart_guest_action_wired_correctly():

    definition = ACTIONS["restart_guest"]

    action = SuggestedAction(type="restart_guest", target="100")
    assert definition.command_template(action) == "atlas proxmox restart 100"
    assert definition.known_targets is known_guest_ids


def test_stop_container_action_wired_correctly():

    definition = ACTIONS["stop_container"]

    action = SuggestedAction(type="stop_container", target="plex")
    assert definition.command_template(action) == "atlas stop plex"
    assert definition.known_targets is known_container_names


def test_resize_container_action_wired_correctly():

    definition = ACTIONS["resize_container"]

    assert definition.known_targets is known_container_names


def test_resize_container_command_template_with_cpus_only():

    definition = ACTIONS["resize_container"]

    action = SuggestedAction(
        type="resize_container", target="plex", cpus="1.5", memory=None
    )

    assert definition.command_template(action) == "atlas resize plex --cpus 1.5"


def test_resize_container_command_template_with_memory_only():

    definition = ACTIONS["resize_container"]

    action = SuggestedAction(
        type="resize_container", target="plex", cpus=None, memory="512m"
    )

    assert definition.command_template(action) == "atlas resize plex --memory 512m"


def test_resize_container_command_template_with_both():

    definition = ACTIONS["resize_container"]

    action = SuggestedAction(
        type="resize_container", target="plex", cpus="1.5", memory="512m"
    )

    assert (
        definition.command_template(action)
        == "atlas resize plex --cpus 1.5 --memory 512m"
    )


def test_resize_container_command_template_with_neither():
    """
    A malformed suggestion (both null) still renders to something -
    atlas resize's own CLI validation is the safety net that catches
    a genuinely empty resize, not this template.
    """

    definition = ACTIONS["resize_container"]

    action = SuggestedAction(
        type="resize_container", target="plex", cpus=None, memory=None
    )

    assert definition.command_template(action) == "atlas resize plex"


def test_stop_guest_action_wired_correctly():

    definition = ACTIONS["stop_guest"]

    action = SuggestedAction(type="stop_guest", target="100")
    assert definition.command_template(action) == "atlas proxmox stop 100"
    assert definition.known_targets is known_guest_ids


def test_resize_guest_action_wired_correctly():

    definition = ACTIONS["resize_guest"]

    assert definition.known_targets is known_guest_ids


def test_resize_guest_command_template_with_both():

    definition = ACTIONS["resize_guest"]

    action = SuggestedAction(
        type="resize_guest", target="100", cpus="1.5", memory="512m"
    )

    assert (
        definition.command_template(action)
        == "atlas proxmox resize 100 --cpus 1.5 --memory 512m"
    )
