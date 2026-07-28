from atlas.actions import ACTIONS, known_container_names, known_guest_ids


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


def test_actions_registry_has_all_three_entries():

    assert set(ACTIONS.keys()) == {
        "restart_container", "restart_guest", "stop_container"
    }


def test_restart_container_action_wired_correctly():

    definition = ACTIONS["restart_container"]

    assert definition.command_template.format(target="plex") == "atlas restart plex"
    assert definition.known_targets is known_container_names


def test_restart_guest_action_wired_correctly():

    definition = ACTIONS["restart_guest"]

    assert (
        definition.command_template.format(target="100")
        == "atlas proxmox restart 100"
    )
    assert definition.known_targets is known_guest_ids


def test_stop_container_action_wired_correctly():

    definition = ACTIONS["stop_container"]

    assert definition.command_template.format(target="plex") == "atlas stop plex"
    assert definition.known_targets is known_container_names
