import json
from datetime import datetime, timedelta

import pytest

from atlas.config.models import AtlasConfig, HomeAssistantConfig
from atlas.monitoring import homeassistant as ha
from atlas.web.home_page import build_stats, render_home_page

NOW = datetime(2026, 11, 18, 12)
LONG_AGO = (NOW - timedelta(hours=30)).isoformat() + "+00:00"
JUST_NOW = (NOW - timedelta(hours=1)).isoformat() + "+00:00"


def _entity(entity_id, state, changed=LONG_AGO, **attributes):
    return {"entity_id": entity_id, "state": state, "last_changed": changed, "attributes": attributes}


STATES = [
    _entity("camera.porch", "unavailable"), _entity("binary_sensor.porch_motion", "unavailable"),   # all down: offline
    _entity("sensor.shed_temp", "unavailable"), _entity("sensor.shed_humidity", "21"),         # one still answers
    _entity("light.hall", "unavailable", JUST_NOW),                                                # down, but 1 h only
    _entity("media_player.living_room_tv", "unavailable"),                                         # TVs don't count
    _entity("sensor.door_lock_battery", "12", device_class="battery", unit_of_measurement="%"),
    _entity("sensor.tablet_battery", "64", device_class="battery", unit_of_measurement="%"),
    _entity("binary_sensor.leak_battery_low", "on", device_class="battery"),
    _entity("update.home_assistant_core_update", "on", title="Home Assistant Core", installed_version="2026.10.3",
            latest_version="2026.11.2"),
    _entity("update.mushroom", "off", title="Mushroom")]
DEVICES = {"camera.porch": "Porch camera", "binary_sensor.porch_motion": "Porch camera",
           "sensor.shed_temp": "Shed sensor", "sensor.shed_humidity": "Shed sensor",
           "sensor.door_lock_battery": "Front door lock", "binary_sensor.leak_battery_low": "Leak sensor"}


def test_offline_devices_batteries_and_updates():
    found = ha.summarize(STATES, DEVICES, HomeAssistantConfig(), NOW)
    assert found["offline"] == [{"name": "Porch camera", "hours": 30, "kinds": ["binary sensor", "camera"]}]
    assert found["batteries"] == [{"name": "Front door lock", "level": 12}, {"name": "Leak sensor", "level": None}]
    assert found["updates"] == [{"title": "Home Assistant Core", "installed": "2026.10.3", "latest": "2026.11.2"}]


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
        self.text = json.dumps(data)

    def json(self):
        return self.data


class FakeHA:
    def __init__(self, status=200):
        self.status, self.seen = status, []

    def get(self, url, headers=None, **kw):
        self.seen.append(headers["Authorization"])
        if self.status != 200:
            return Reply({"message": "nope"}, self.status)
        return Reply({"version": "2026.10.3"} if url.endswith("/api/config") else STATES)

    def post(self, url, headers=None, json=None, **kw):
        assert "device_attr" in json["template"]
        return Reply(DEVICES)


def test_fetch_uses_the_token_and_explains_failures():
    config = HomeAssistantConfig(url="http://192.0.2.80:8123")
    http = FakeHA()
    info = ha.fetch(config, {"ATLAS_HA_TOKEN": "t0k"}, http, now=NOW)
    assert info["version"] == "2026.10.3" and info["offline"][0]["name"] == "Porch camera"
    assert http.seen == ["Bearer t0k", "Bearer t0k"]
    with pytest.raises(ha.HomeAssistantError, match="token was refused"):
        ha.fetch(config, {"ATLAS_HA_TOKEN": "bad"}, FakeHA(401))
    with pytest.raises(ha.HomeAssistantError, match="long-lived access token"):
        ha.fetch(config, {}, FakeHA())
    with pytest.raises(ha.HomeAssistantError, match="address"):
        ha.fetch(HomeAssistantConfig(url="homeassistant"), {"ATLAS_HA_TOKEN": "t"}, FakeHA())


def test_alerts_once_and_when_fine_again(temp_db):
    from atlas.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    settings = AtlasConfig(homeassistant={"enabled": True, "url": "http://192.0.2.80:8123"})
    lost = {"version": "x", "offline": [{"name": "Porch camera", "hours": 30, "kinds": ["camera"]}],
            "batteries": [{"name": "Front door lock", "level": 12}], "updates": []}
    fine = {"version": "x", "offline": [], "batteries": [], "updates": []}

    def down(config):
        raise ha.HomeAssistantError("No answer from http://192.0.2.80:8123: ConnectTimeout")

    for i, get in enumerate([lambda c: lost, lambda c: lost, down, down, down, lambda c: fine]):
        ha.run(settings, store, NOW + timedelta(minutes=15 * i), get=get, send=sent.append)
    assert [text.key for text in sent] == ["ha:offline:Porch camera", "ha:battery:Front door lock", "ha:down",
                                           "ha:down", "ha:offline:Porch camera"]
    assert "isn't answering" in sent[2] and "answering again" in sent[3] and "back in Home Assistant" in sent[4]


def test_home_tile_and_card():
    detail = {"error": "", "failures": 0, "info": {"version": "2026.10.3", "offline": [
        {"name": "Porch camera", "hours": 30, "kinds": ["camera"]}], "batteries": [], "updates": [
        {"title": "Home Assistant Core", "installed": "a", "latest": "2026.11.2"}]}}
    tiles = build_stats(ha=detail)
    assert tiles == [("Smart home", "1 to check", "1 offline", "/#homeassistant", "bad")]
    html = render_home_page(None, {"rows": [], "down": [], "state": "ok"}, [], now=NOW, ha=detail)
    assert 'id="homeassistant"' in html and "Porch camera" in html and "offline 30 h" in html and "2026.11.2" in html
