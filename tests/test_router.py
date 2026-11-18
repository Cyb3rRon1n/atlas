import pytest

from atlas.config.models import RouterConfig
from atlas.devices import router
from atlas.devices.store import InventoryStore


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


class FakeOpenWrt:
    """ubus over HTTP the way uhttpd answers it."""

    def __init__(self, password="pw"):
        self.password, self.calls = password, []

    def post(self, url, json=None, **kw):
        sid, obj, method, args = json["params"]
        self.calls.append(f"{obj}.{method}")
        if (obj, method) == ("session", "login"):
            ok = args["password"] == self.password
            return Reply({"result": [0, {"ubus_rpc_session": "s1"}] if ok else [6]})
        assert sid == "s1"
        answers = {
            ("luci-rpc", "getDHCPLeases"): {"dhcp_leases": [
                {"macaddr": "02:00:00:00:00:41", "ipaddr": "192.0.2.41", "hostname": "den-tv"},
                {"macaddr": "02:00:00:00:00:42", "ipaddr": "192.0.2.42"}]},
            ("luci-rpc", "getWirelessDevices"): {"radio0": {"interfaces": [
                {"ifname": "phy0-ap0", "iwinfo": {"ssid": "home"}}]}},
            ("iwinfo", "assoclist"): {"results": [{"mac": "02:00:00:00:00:41", "signal": -58}]},
            ("session", "destroy"): {}}
        return Reply({"result": [0, answers[(obj, method)]]})


def test_dhcp_names_and_wifi_then_signs_out():
    http = FakeOpenWrt()
    clients = router.fetch(RouterConfig(url="http://192.0.2.1"), {"ATLAS_ROUTER_PASSWORD": "pw"}, http)
    assert clients[0] == {"mac": "02:00:00:00:00:41", "ip": "192.0.2.41", "hostname": "den-tv",
                          "wifi": {"ssid": "home", "ap": "", "band": "", "signal": -58}}
    assert clients[1]["hostname"] == "" and clients[1]["wifi"] is None
    assert http.calls[-1] == "session.destroy"
    with pytest.raises(router.RouterError, match="wrong user or password"):
        router.fetch(RouterConfig(url="http://192.0.2.1"), {"ATLAS_ROUTER_PASSWORD": "nope"}, FakeOpenWrt())
    with pytest.raises(router.RouterError, match="address"):
        router.fetch(RouterConfig(url="192.0.2.1"), {}, FakeOpenWrt())


def test_leases_link_to_devices_by_mac(temp_db):
    from atlas.devices import Sighting, identify

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "02:00:00:00:00:41", ip="192.0.2.41", mac="02:00:00:00:00:41")])
    clients = router.fetch(RouterConfig(url="http://192.0.2.1"), {"ATLAS_ROUTER_PASSWORD": "pw"}, FakeOpenWrt())
    store.record_run("router", router.sightings(clients))
    tv = next(d for d in store.devices() if d["ip"] == "192.0.2.41")
    assert {s["source"] for s in tv["sightings"]} == {"lan", "router"}
    found = identify.clues(tv, {})
    assert found["hostname"] == "den-tv" and found["wifi"]["ssid"] == "home"


class NoWifiRights(FakeOpenWrt):
    def post(self, url, json=None, **kw):
        if json["params"][1:3] == ["luci-rpc", "getWirelessDevices"]:
            return Reply({"result": [6]})
        return super().post(url, json=json, **kw)


def test_wifi_trouble_keeps_dhcp_names_and_http_errors_read_plainly():
    clients = router.fetch(RouterConfig(url="http://192.0.2.1"), {"ATLAS_ROUTER_PASSWORD": "pw"}, NoWifiRights())
    assert [c["hostname"] for c in clients] == ["den-tv", ""] and clients[0]["wifi"] is None

    class Down:
        def post(self, *a, **kw):
            return Reply({}, status=404)

    with pytest.raises(router.RouterError, match="HTTP 404"):
        router.fetch(RouterConfig(url="http://192.0.2.1"), {}, Down())
