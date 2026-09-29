import json

from typer.testing import CliRunner

import atlas.devices.lan as lan
from atlas.cli.main import app
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore


runner = CliRunner()


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


def test_scan_disabled_does_nothing(temp_db, isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text("scan:\n  enabled: false\n")

    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 0
    assert InventoryStore().source_runs() == []
