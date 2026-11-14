import pytest
from pydantic import ValidationError

from atlas.config.models import AtlasConfig, WiringConfig
from atlas.wiring import env_key, is_virtual_mac, normalize_mac


def test_wiring_config_defaults_off():
    config = AtlasConfig()
    assert config.wiring.enabled is False
    assert config.wiring.switches == [] and config.wiring.unifi.enabled is False


def test_wiring_switch_priv_is_aes_or_des():
    WiringConfig(switches=[{"name": "core-switch", "host": "192.0.2.2", "priv": "des"}])
    with pytest.raises(ValidationError):
        WiringConfig(switches=[{"name": "core-switch", "host": "192.0.2.2", "priv": "none"}])


def test_env_key():
    assert env_key("core-switch") == "CORE_SWITCH"
    assert env_key("Rack 2.sw") == "RACK_2_SW"


@pytest.mark.parametrize("raw", ["02:00:00:AA:BB:01", "02-00-00-aa-bb-01", "02 00 00 AA BB 01",
                                 "0200.00aa.bb01", "Hex-STRING: 02 00 00 AA BB 01"])
def test_normalize_mac_forms(raw):
    assert normalize_mac(raw) == "02:00:00:aa:bb:01"


@pytest.mark.parametrize("raw", ["", None, "core-switch", "02:00:00:aa:bb", "zz:00:00:aa:bb:01"])
def test_normalize_mac_rejects(raw):
    assert normalize_mac(raw) is None


def test_is_virtual_mac():
    assert is_virtual_mac("bc:24:11:00:00:01") and is_virtual_mac("52:54:00:00:00:01")
    assert is_virtual_mac("02:00:00:00:00:01")          # locally administered
    assert not is_virtual_mac("00:00:5e:00:53:01")