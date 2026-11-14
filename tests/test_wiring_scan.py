import threading

import pytest

from atlas.config.models import AtlasConfig
from atlas.wiring import WiringError
from atlas.wiring.scan import WiringBusy, run_scan, _LOCK
from atlas.wiring.store import WiringStore

SWITCH_RESULT = {"name": "core-switch", "host": "192.0.2.2", "sys_name": "core-switch",
                 "chassis_mac": "02:00:00:00:00:10", "weak_privacy": True,
                 "ports": {"gi5": {"index": 53, "up": True, "speed": 1000, "alias": ""}},
                 "neighbors": [], "fdb": [{"port": "gi5", "mac": "00:00:5e:00:53:01", "vlan": 1}]}


def _settings(tmp_path):
    return AtlasConfig(wiring={"enabled": True, "cabling_file": str(tmp_path / "cabling.yaml"),
                               "switches": [{"name": "core-switch", "host": "192.0.2.2", "priv": "des"}]})


def test_scan_saves_and_marks_des(temp_db, tmp_path):
    result = run_scan(_settings(tmp_path), WiringStore(), [], env={}, collect=lambda *a, **k: SWITCH_RESULT)
    assert result["sources"]["core-switch"] == {"ok": True, "error": "", "stale": False, "note": "weak privacy (DES)"}
    assert len(WiringStore().latest(5)) == 1


def test_failed_source_reuses_previous_raw(temp_db, tmp_path):
    settings = _settings(tmp_path)
    run_scan(settings, WiringStore(), [], env={}, collect=lambda *a, **k: SWITCH_RESULT)

    def broken(*a, **k):
        raise WiringError("core-switch: Timeout: No Response from 192.0.2.2")

    result = run_scan(settings, WiringStore(), [], env={}, collect=broken)
    source = result["sources"]["core-switch"]
    assert source["ok"] is False and source["stale"] is True and "Timeout" in source["error"]
    assert any(n["name"] == "00:00:5e:00:53:01" for n in result["snapshot"]["nodes"])


def test_busy(temp_db, tmp_path):
    assert _LOCK.acquire(blocking=False)
    try:
        with pytest.raises(WiringBusy):
            run_scan(_settings(tmp_path), WiringStore(), [], env={}, collect=lambda *a, **k: SWITCH_RESULT)
    finally:
        _LOCK.release()

def test_cli_wiring_scan_disabled(isolated_cwd):
    from typer.testing import CliRunner

    from atlas.cli.main import app

    result = CliRunner().invoke(app, ["wiring", "scan"])
    assert result.exit_code == 0 and "wiring.enabled is false" in result.output
