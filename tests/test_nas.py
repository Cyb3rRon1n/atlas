import json
from datetime import datetime, timedelta

import pytest

from atlas.config.models import AtlasConfig, NasConfig
from atlas.monitoring import nas
from atlas.web.home_page import build_storage


def _config(**kw):
    return NasConfig(**{"enabled": True, "kind": "truenas", "url": "https://192.0.2.20", "user": "atlas", **kw})


class FakeTrueNAS:
    """A websocket answering JSON-RPC like TrueNAS: login, then pools, disks, temperatures, alerts."""

    def __init__(self, login_ex=True, key_ok=True):
        self.login_ex, self.key_ok, self.sent, self.closed, self.queue = login_ex, key_ok, [], False, []

    def __call__(self, url, timeout=None, sslopt=None):
        self.url, self.sslopt = url, sslopt
        return self

    def send(self, text):
        request = json.loads(text)
        self.sent.append(request["method"])
        method, rid = request["method"], request["id"]
        answers = {
            "auth.login_with_api_key": self.key_ok,
            "pool.query": [{"name": "tank", "status": "DEGRADED", "healthy": False, "size": 8 * 10**12,
                            "allocated": 2 * 10**12}],
            "disk.query": [{"name": "sda", "serial": "S1", "model": "Example HDD", "type": "HDD", "size": 4 * 10**12},
                           {"name": "nvme0n1", "serial": "S2", "model": "Example NVMe", "type": "SSD"}],
            "disk.temperatures": {"sda": 38, "nvme0n1": 51},
            "alert.list": [{"klass": "SMART", "level": "CRITICAL", "dismissed": False,
                            "formatted": "Device: /dev/sda, 8 Currently unreadable (pending) sectors."},
                           {"klass": "SMART", "level": "CRITICAL", "dismissed": True, "formatted": "/dev/nvme0n1"}]}
        if method == "auth.login_ex":
            reply = ({"result": {"response_type": "SUCCESS" if self.key_ok else "AUTH_ERR"}} if self.login_ex
                     else {"error": {"code": -32601, "message": "Method not found"}})
        else:
            reply = {"result": answers[method]}
        self.queue += [{"jsonrpc": "2.0", "method": "collection_update", "params": {}},     # a notification
                       {"jsonrpc": "2.0", "id": rid, **reply}]

    def recv(self):
        return json.dumps(self.queue.pop(0))

    def close(self):
        self.closed = True


def test_truenas_reads_pools_disks_temps_and_smart_alerts():
    ws = FakeTrueNAS()
    info = nas.fetch(_config(), {"ATLAS_NAS_PASSWORD": "1-key"}, connect=ws)
    assert ws.url == "wss://192.0.2.20/api/current" and ws.sslopt["cert_reqs"] == 0 and ws.closed
    assert ws.sent[0] == "auth.login_ex"
    assert info["pools"] == [{"name": "tank", "health": "DEGRADED", "size": 8 * 10**12, "alloc": 2 * 10**12}]
    sda, nvme = info["disks"]
    assert (sda["dev"], sda["type"], sda["temp"], sda["health"]) == ("sda", "hdd", 38, "FAILED")
    assert (nvme["type"], nvme["temp"], nvme["health"]) == ("nvme", 51, "PASSED")      # its alert was dismissed


def test_truenas_older_login_bad_key_and_plain_http():
    old = FakeTrueNAS(login_ex=False)
    nas.fetch(_config(), {"ATLAS_NAS_PASSWORD": "1-key"}, connect=old)
    assert old.sent[:2] == ["auth.login_ex", "auth.login_with_api_key"]                # 24.10 has no login_ex
    for fake in (FakeTrueNAS(key_ok=False), FakeTrueNAS(login_ex=False, key_ok=False)):
        with pytest.raises(nas.NasError, match="API key not accepted"):
            nas.fetch(_config(), {"ATLAS_NAS_PASSWORD": "1-bad"}, connect=fake)
        assert fake.closed
    with pytest.raises(nas.NasError, match="https"):
        nas.fetch(_config(url="http://192.0.2.20"), {"ATLAS_NAS_PASSWORD": "1-key"}, connect=FakeTrueNAS())


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


class FakeSynology:

    def __init__(self, login_error=None):
        self.login_error, self.calls = login_error, []

    def post(self, url, data=None, **kw):
        self.calls.append(data["method"])
        if data["method"] == "login":
            assert data["account"] == "atlas" and data["passwd"] == "pw"
            return Reply({"success": False, "error": {"code": self.login_error}} if self.login_error
                         else {"success": True, "data": {"sid": "abc"}})
        if data["method"] == "logout":
            return Reply({"success": True})
        assert data["_sid"] == "abc"
        return Reply({"success": True, "data": {
            "volumes": [{"id": "volume_1", "status": "normal", "size": {"total": "4000000000000", "used": "1000000000000"}}],
            "disks": [{"id": "sata1", "name": "Drive 1", "model": "Example HDD ", "diskType": "SATA", "temp": 36,
                       "smart_status": "normal", "status": "normal", "exceed_bad_sector_thr": False,
                       "below_remain_life_thr": False},
                      {"id": "nvme1", "name": "Cache 1", "diskType": "SSD", "temp": 44, "smart_status": "normal",
                       "status": "normal", "below_remain_life_thr": True}]}})


def test_synology_reads_volumes_and_disks_and_always_signs_out():
    http = FakeSynology()
    info = nas.fetch(_config(kind="synology"), {"ATLAS_NAS_PASSWORD": "pw"}, http)
    assert http.calls == ["login", "load_info", "logout"]
    assert info["pools"] == [{"name": "volume 1", "health": "NORMAL", "size": 4 * 10**12, "alloc": 10**12}]
    drive, cache = info["disks"]
    assert (drive["dev"], drive["type"], drive["temp"], drive["health"], drive["model"]) == \
        ("Drive 1", "hdd", 36, "PASSED", "Example HDD")
    assert cache["type"] == "ssd" and cache["worn"]
    with pytest.raises(nas.NasError, match="must be an administrator"):
        nas.fetch(_config(kind="synology"), {"ATLAS_NAS_PASSWORD": "pw"}, FakeSynology(login_error=402))
    with pytest.raises(nas.NasError, match="two-factor"):
        nas.fetch(_config(kind="synology"), {"ATLAS_NAS_PASSWORD": "pw"}, FakeSynology(login_error=403))


def test_pool_alerts_once_disk_alerts_and_read_errors_keep_state(temp_db):
    from atlas.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    settings = AtlasConfig(nas=_config(name="nas"))
    t = datetime(2026, 11, 17, 9)

    def info(health, disk_health="PASSED"):
        return {"kind": "TrueNAS", "pools": [{"name": "tank", "health": health, "size": 10, "alloc": 5}],
                "disks": [{"dev": "sda", "type": "hdd", "serial": "S1", "health": disk_health, "temp": 30}]}

    def failing(config):
        raise nas.NasError("No answer from https://192.0.2.20: ConnectTimeout")

    for i, get in enumerate([lambda c: info("ONLINE"), lambda c: info("DEGRADED", "FAILED"), failing,
                             lambda c: info("DEGRADED", "FAILED"), lambda c: info("ONLINE")]):
        detail = nas.run(settings, store, t + timedelta(minutes=15 * i), get=get, send=sent.append)
    assert [s.key for s in sent] == ["nas:pool:nas:tank", "disks:failed:nas:S1", "nas:pool:nas:tank",
                                     "disks:failed:nas:S1"]
    assert "DEGRADED" in sent[0] and "healthy again" in sent[2] and "no longer failing" in sent[3]
    statuses = store.statuses()
    assert statuses["nas"]["ok"] and statuses["nas-disks"]["ok"] and detail["bad_pools"] == []


def test_home_storage_card_shows_the_nas():
    detail = {"name": "nas", "error": "", "info": {
        "pools": [{"name": "volume 1", "health": "NORMAL", "size": 4 * 10**12, "alloc": 10**12}],
        "disks": [{"dev": "Drive 1", "type": "hdd", "health": "PASSED", "temp": 36}]}}
    rows = build_storage([], {}, {}, None, nas=detail)["rows"]
    assert rows[0] == {"name": "nas volume 1", "detail": "NORMAL · 25% of 4.0 TB", "warn": False}
    assert rows[1]["name"] == "nas disks" and "all healthy" in rows[1]["detail"]
    broken = build_storage([], {}, {}, None, nas={"name": "nas", "error": "No answer", "info": {}})
    assert broken["state"] == "warn" and broken["rows"][-1]["detail"] == "can't read it - see Setup"
