import requests

from atlas.posture.collectors.services import (container_ip, container_ips, crowdsec_bans, gluetun_status,
                                               public_ip, vpn_members)
from posture_fakes import Response, make_client


CLIENT = make_client()


def test_container_ips_maps_bridge_ips_only():
    assert container_ips(CLIENT) == {"172.18.0.3": "gluetun", "172.18.0.13": "sonarr"}
    assert container_ip(CLIENT, "sonarr") == "172.18.0.13"


def test_vpn_members_by_id_or_name():
    assert vpn_members(CLIENT, "gluetun") == ["qbittorrent"]


def test_gluetun_status_sends_key_and_parses():
    seen = {}
    def get(url, headers, timeout):
        seen.update(url=url, headers=headers)
        return Response(data={"public_ip": "198.51.100.9", "country": "Netherlands"})
    assert gluetun_status("http://172.18.0.3:8000", "k", get=get) == {
        "ok": True, "exit_ip": "198.51.100.9", "country": "Netherlands"}
    assert seen == {"url": "http://172.18.0.3:8000/v1/publicip/ip", "headers": {"X-API-Key": "k"}}


def test_gluetun_status_reports_errors_without_raising():
    def get(url, headers, timeout):
        raise requests.ConnectionError("refused")
    result = gluetun_status("http://x", "k", get=get)
    assert result["ok"] is False and "refused" in result["error"]
    assert gluetun_status("http://x", "k", get=lambda url, headers, timeout: Response(401))["ok"] is False


def test_crowdsec_counts_active_decisions_including_null():
    def get(url, headers, timeout):
        assert url == "http://172.18.0.7:8080/v1/decisions" and headers == {"X-Api-Key": "b"}
        return Response(data=[{"value": "203.0.113.5"}, {"value": "203.0.113.6"}])
    assert crowdsec_bans("http://172.18.0.7:8080", "b", get=get) == {"ok": True, "active": 2}
    assert crowdsec_bans("http://x", "b", get=lambda url, headers, timeout: Response(data=None)) == {
        "ok": True, "active": 0}


def test_public_ip_strips_and_validates():
    assert public_ip("https://ip.example.test", get=lambda url, timeout: Response(text=" 192.0.2.10\n")) == {
        "ok": True, "ip": "192.0.2.10"}
    assert public_ip("https://ip.example.test", get=lambda url, timeout: Response(text="<html>"))["ok"] is False
