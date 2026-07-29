from unittest.mock import MagicMock, patch

from atlas.actions import ACTIONS, execute_action, known_container_names, known_guest_ids
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


def test_execute_action_restart_container_calls_manager_function():

    with patch(
        "atlas.actions.registry.restart_container",
        return_value={"success": True, "previous_status": "running"}
    ) as mock_restart:

        result = execute_action(
            SuggestedAction(type="restart_container", target="plex")
        )

    assert result == {"success": True, "previous_status": "running"}
    mock_restart.assert_called_once_with("plex")


def test_execute_action_stop_container_calls_manager_function():

    with patch(
        "atlas.actions.registry.stop_container",
        return_value={"success": True, "previous_status": "running"}
    ) as mock_stop:

        result = execute_action(
            SuggestedAction(type="stop_container", target="plex")
        )

    assert result == {"success": True, "previous_status": "running"}
    mock_stop.assert_called_once_with("plex")


def test_execute_action_resize_container_converts_cpus_and_passes_memory():

    with patch(
        "atlas.actions.registry.resize_container",
        return_value={"success": True}
    ) as mock_resize:

        result = execute_action(
            SuggestedAction(
                type="resize_container", target="plex",
                cpus="1.5", memory="512m"
            )
        )

    assert result == {"success": True}
    mock_resize.assert_called_once_with("plex", cpus=1.5, mem_limit="512m")


def test_execute_action_unknown_type_returns_error_without_raising():

    result = execute_action(SuggestedAction(type="delete_everything", target="x"))

    assert result == {
        "success": False,
        "error": "Unknown action type: delete_everything"
    }


def _fake_proxmox_setup(guest_type="lxc"):
    """
    Shared mock setup for the three Proxmox executors: a connected
    client and a found guest, matching what _execute_guest_action()
    needs before it can call its manager function.
    """

    fake_client = MagicMock()

    return patch(
        "atlas.actions.registry.connect",
        return_value=fake_client
    ), patch(
        "atlas.actions.registry.get_guest_info",
        return_value={
            "found": True, "node": "pve1", "type": guest_type
        }
    )


def test_execute_action_restart_guest_connects_and_looks_up_guest_first():

    connect_patch, info_patch = _fake_proxmox_setup(guest_type="qemu")

    with connect_patch as mock_connect, info_patch as mock_info, patch(
        "atlas.actions.registry.restart_guest",
        return_value={"success": True}
    ) as mock_restart_guest:

        result = execute_action(
            SuggestedAction(type="restart_guest", target="100")
        )

    assert result == {"success": True}
    mock_connect.assert_called_once()
    mock_info.assert_called_once_with(mock_connect.return_value, 100)
    mock_restart_guest.assert_called_once_with(
        mock_connect.return_value, "pve1", 100, "qemu"
    )


def test_execute_action_stop_guest_calls_manager_function():

    connect_patch, info_patch = _fake_proxmox_setup(guest_type="lxc")

    with connect_patch as mock_connect, info_patch, patch(
        "atlas.actions.registry.stop_guest",
        return_value={"success": True}
    ) as mock_stop_guest:

        result = execute_action(
            SuggestedAction(type="stop_guest", target="101")
        )

    assert result == {"success": True}
    mock_stop_guest.assert_called_once_with(
        mock_connect.return_value, "pve1", 101, "lxc"
    )


def test_execute_action_resize_guest_converts_cpus_and_passes_memory():

    connect_patch, info_patch = _fake_proxmox_setup(guest_type="lxc")

    with connect_patch as mock_connect, info_patch, patch(
        "atlas.actions.registry.resize_guest",
        return_value={"success": True}
    ) as mock_resize_guest:

        result = execute_action(
            SuggestedAction(
                type="resize_guest", target="100",
                cpus="0.5", memory="256m"
            )
        )

    assert result == {"success": True}
    mock_resize_guest.assert_called_once_with(
        mock_connect.return_value, "pve1", 100, "lxc",
        cpus=0.5, memory="256m"
    )


def test_execute_action_guest_action_returns_error_when_cannot_connect():

    with patch(
        "atlas.actions.registry.connect",
        return_value=None
    ):

        result = execute_action(
            SuggestedAction(type="restart_guest", target="100")
        )

    assert result == {
        "success": False,
        "error": "Unable to connect to Proxmox"
    }


def test_execute_action_guest_action_returns_error_when_guest_not_found():

    with patch(
        "atlas.actions.registry.connect",
        return_value=MagicMock()
    ), patch(
        "atlas.actions.registry.get_guest_info",
        return_value={"found": False, "error": "No guest with vmid 999 found"}
    ):

        result = execute_action(
            SuggestedAction(type="restart_guest", target="999")
        )

    assert result == {
        "found": False,
        "error": "No guest with vmid 999 found"
    }
