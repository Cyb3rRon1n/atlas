import json

from typer.testing import CliRunner

import atlas.cli.main as cli_main
import atlas.devices.lan as lan
from atlas.cli.main import app
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore


runner = CliRunner()

PROXMOX_ATLAS_YAML = (
    "proxmox:\n"
    "  enabled: true\n"
    "  host: proxmox.local\n"
    "  user: root@pam\n"
    "  token_name: atlas\n"
    "  token_value: secret\n"
)


def test_scan_records_devices_and_devices_lists_them(temp_db, isolated_cwd, monkeypatch):

    (isolated_cwd / "atlas.yaml").write_text(
        "map:\n  hosts:\n    - name: mediabox\n      address: 192.168.10.57\n")
    monkeypatch.setattr(lan, "scan", lambda subnets, timeout: (
        ["192.168.10.0/24"], [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")]))

    result = runner.invoke(app, ["scan", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["linked"] == 1

    listed = runner.invoke(app, ["devices", "--json"])
    devices = json.loads(listed.output)
    assert [d["name"] for d in devices] == ["mediabox"]
    assert devices[0]["status"] == "seen"


def test_scan_failure_is_recorded_and_exits_1(temp_db, isolated_cwd, monkeypatch):

    def boom(subnets, timeout):
        raise RuntimeError("no subnet to scan")

    (isolated_cwd / "atlas.yaml").write_text("name: test\n")
    monkeypatch.setattr(lan, "scan", boom)

    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 1
    run = InventoryStore().source_runs()[0]
    assert (run["source"], run["ok"], run["error"]) == ("lan", False, "no subnet to scan")


def test_scan_with_nothing_new_or_offline_does_not_publish_event(temp_db, isolated_cwd, monkeypatch):
    """A scan that links a sighting to an already-known device with no new
    or offline devices and nothing to notify is a no-op - it shouldn't add
    event-log noise (same rule already applied elsewhere in this codebase)."""

    from atlas.knowledge.queries import KnowledgeQueries

    (isolated_cwd / "atlas.yaml").write_text(
        "map:\n  hosts:\n    - name: mediabox\n      address: 192.168.10.57\n")
    monkeypatch.setattr(lan, "scan", lambda subnets, timeout: (
        ["192.168.10.0/24"], [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")]))

    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 0
    event_types = [event.event_type for event in KnowledgeQueries().recent_events()]
    assert "atlas.devices.scan.completed" not in event_types


def test_scan_disabled_does_nothing(temp_db, isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text("scan:\n  enabled: false\n")

    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 0
    assert InventoryStore().source_runs() == []


def test_map_records_failed_proxmox_run_when_discover_resources_raises(temp_db, isolated_cwd, monkeypatch):
    """Token auth means connect() succeeds without network I/O - discover_resources
    is where a down Proxmox actually surfaces, and atlas map must still record
    (and survive) that failure rather than crashing before anything is saved."""

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ATLAS_YAML)

    monkeypatch.setattr(cli_main, "connect", lambda *args, **kwargs: object())

    def boom(client):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(cli_main, "discover_resources", boom)

    result = runner.invoke(app, ["map"])

    assert result.exit_code == 0, result.output
    run = InventoryStore().source_runs()[0]
    assert run["source"] == "proxmox"
    assert run["ok"] is False
    assert "connection refused" in run["error"]


def test_map_only_sights_running_guests(temp_db, isolated_cwd, monkeypatch):

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ATLAS_YAML)

    monkeypatch.setattr(cli_main, "connect", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli_main, "discover_resources", lambda client: [
        {"vmid": 100, "name": "plex", "type": "lxc", "status": "running", "template": None},
        {"vmid": 200, "name": "stopped-vm", "type": "qemu", "status": "stopped", "template": None},
    ])

    result = runner.invoke(app, ["map"])

    assert result.exit_code == 0, result.output
    assert [d["name"] for d in InventoryStore().devices()] == ["plex"]


def test_map_stopped_guest_does_not_refresh_last_seen(temp_db, isolated_cwd, monkeypatch):

    (isolated_cwd / "atlas.yaml").write_text(PROXMOX_ATLAS_YAML)
    monkeypatch.setattr(cli_main, "connect", lambda *args, **kwargs: object())

    guest = {"vmid": 100, "name": "plex", "type": "lxc", "status": "running", "template": None}
    monkeypatch.setattr(cli_main, "discover_resources", lambda client: [guest])

    assert runner.invoke(app, ["map"]).exit_code == 0
    first_seen = InventoryStore().devices()[0]["last_seen"]

    guest["status"] = "stopped"
    assert runner.invoke(app, ["map"]).exit_code == 0

    assert InventoryStore().devices()[0]["last_seen"] == first_seen
