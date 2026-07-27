from atlas.proxmox.changes import diff_virtualization, format_change


def test_no_changes_when_no_previous_baseline():

    current = {
        "nodes": [{"name": "pve1", "status": "online"}],
        "guests": [{"vmid": 100, "name": "plex", "type": "qemu", "status": "running"}]
    }

    assert diff_virtualization(None, current) == []
    assert diff_virtualization({}, current) == []


def test_no_changes_when_nothing_differs():

    snapshot = {
        "nodes": [{"name": "pve1", "status": "online"}],
        "guests": [{"vmid": 100, "name": "plex", "type": "qemu", "status": "running"}]
    }

    assert diff_virtualization(snapshot, snapshot) == []


def test_node_added():

    previous = {"nodes": [], "guests": []}
    current = {"nodes": [{"name": "pve2", "status": "online"}], "guests": []}

    assert diff_virtualization(previous, current) == [
        {"type": "node_added", "node": "pve2"}
    ]


def test_node_removed():

    previous = {"nodes": [{"name": "pve2", "status": "online"}], "guests": []}
    current = {"nodes": [], "guests": []}

    assert diff_virtualization(previous, current) == [
        {"type": "node_removed", "node": "pve2"}
    ]


def test_node_status_changed():

    previous = {"nodes": [{"name": "pve1", "status": "online"}], "guests": []}
    current = {"nodes": [{"name": "pve1", "status": "offline"}], "guests": []}

    assert diff_virtualization(previous, current) == [
        {
            "type": "node_status_changed",
            "node": "pve1",
            "from": "online",
            "to": "offline"
        }
    ]


def test_guest_added():

    previous = {"nodes": [], "guests": []}
    current = {
        "nodes": [],
        "guests": [{"vmid": 101, "name": "sonarr", "type": "lxc", "status": "running"}]
    }

    assert diff_virtualization(previous, current) == [
        {
            "type": "guest_added",
            "vmid": 101,
            "name": "sonarr",
            "guest_type": "lxc"
        }
    ]


def test_guest_removed():

    previous = {
        "nodes": [],
        "guests": [{"vmid": 101, "name": "sonarr", "type": "lxc", "status": "running"}]
    }
    current = {"nodes": [], "guests": []}

    assert diff_virtualization(previous, current) == [
        {"type": "guest_removed", "vmid": 101, "name": "sonarr"}
    ]


def test_guest_status_changed():

    previous = {
        "nodes": [],
        "guests": [{"vmid": 100, "name": "plex", "type": "qemu", "status": "running"}]
    }
    current = {
        "nodes": [],
        "guests": [{"vmid": 100, "name": "plex", "type": "qemu", "status": "stopped"}]
    }

    assert diff_virtualization(previous, current) == [
        {
            "type": "guest_status_changed",
            "vmid": 100,
            "name": "plex",
            "from": "running",
            "to": "stopped"
        }
    ]


def test_guest_matched_by_vmid_not_name():
    """
    A guest renamed but keeping the same vmid should be treated as a
    status/no-op check against the same guest, not as one removed and
    a different one added - vmid is Proxmox's actual stable identifier.
    """

    previous = {
        "nodes": [],
        "guests": [{"vmid": 100, "name": "old-name", "type": "qemu", "status": "running"}]
    }
    current = {
        "nodes": [],
        "guests": [{"vmid": 100, "name": "old-name", "type": "qemu", "status": "running"}]
    }

    assert diff_virtualization(previous, current) == []


def test_multiple_simultaneous_changes():

    previous = {
        "nodes": [{"name": "pve1", "status": "online"}],
        "guests": [
            {"vmid": 100, "name": "plex", "type": "qemu", "status": "running"},
            {"vmid": 101, "name": "sonarr", "type": "lxc", "status": "running"},
        ]
    }
    current = {
        "nodes": [{"name": "pve1", "status": "offline"}],
        "guests": [
            {"vmid": 100, "name": "plex", "type": "qemu", "status": "stopped"},
            {"vmid": 102, "name": "radarr", "type": "lxc", "status": "running"},
        ]
    }

    changes = diff_virtualization(previous, current)

    assert {"type": "node_status_changed", "node": "pve1", "from": "online", "to": "offline"} in changes
    assert {"type": "guest_status_changed", "vmid": 100, "name": "plex", "from": "running", "to": "stopped"} in changes
    assert {"type": "guest_removed", "vmid": 101, "name": "sonarr"} in changes
    assert {"type": "guest_added", "vmid": 102, "name": "radarr", "guest_type": "lxc"} in changes
    assert len(changes) == 4


def test_format_change_covers_every_type():

    assert format_change(
        {"type": "node_added", "node": "pve2"}
    ) == "+ Node 'pve2' added"

    assert format_change(
        {"type": "node_removed", "node": "pve2"}
    ) == "- Node 'pve2' removed"

    assert format_change(
        {"type": "node_status_changed", "node": "pve1", "from": "online", "to": "offline"}
    ) == "~ Node 'pve1' status changed: online → offline"

    assert format_change(
        {"type": "guest_added", "vmid": 101, "name": "sonarr", "guest_type": "lxc"}
    ) == "+ Guest 'sonarr' (101, lxc) added"

    assert format_change(
        {"type": "guest_removed", "vmid": 101, "name": "sonarr"}
    ) == "- Guest 'sonarr' (101) removed"

    assert format_change(
        {
            "type": "guest_status_changed",
            "vmid": 100,
            "name": "plex",
            "from": "running",
            "to": "stopped"
        }
    ) == "~ Guest 'plex' (100) status changed: running → stopped"
