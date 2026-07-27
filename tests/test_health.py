from unittest.mock import patch

from atlas.config.models import (
    AtlasConfig,
    IntelligenceConfig,
    MonitoringConfig,
    ProxmoxConfig,
)
from atlas.health.checks import (
    check_docker,
    check_intelligence,
    check_inventory,
    check_memory,
    check_monitoring,
    check_proxmox,
    check_python,
    check_storage,
    run_checks,
)


def test_run_checks_returns_eight_named_checks(isolated_cwd, monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    checks = run_checks()

    assert [c["name"] for c in checks] == [
        "Python", "Memory", "Storage", "Docker", "Inventory",
        "Proxmox", "Intelligence", "Monitoring",
    ]

    for check in checks:
        assert isinstance(check["status"], bool)
        assert isinstance(check["details"], str)


def test_check_python_is_always_healthy():

    assert check_python()["status"] is True


def test_check_memory_and_storage_report_percent_used():

    assert "% used" in check_memory()["details"]
    assert "% used" in check_storage()["details"]


def test_check_docker_reflects_availability():

    with patch(
        "atlas.docker.manager.docker.from_env",
        side_effect=RuntimeError("no docker socket")
    ):
        result = check_docker()

    assert result["status"] is False
    assert result["details"] == "not available"


def test_check_inventory_true_when_file_present(isolated_cwd):

    from atlas.inventory import save_inventory

    save_inventory({"system": {"hostname": "sentinel"}})

    result = check_inventory()

    assert result["status"] is True
    assert result["details"] == "available"


def test_check_inventory_false_when_missing(isolated_cwd):

    result = check_inventory()

    assert result["status"] is False
    assert result["details"] == "missing"


def test_check_proxmox_healthy_when_disabled():

    result = check_proxmox(AtlasConfig())

    assert result["status"] is True
    assert result["details"] == "disabled"


def test_check_proxmox_unhealthy_when_enabled_without_credentials():

    config = AtlasConfig(
        proxmox=ProxmoxConfig(enabled=True, host="192.168.1.10")
    )

    result = check_proxmox(config)

    assert result["status"] is False


def test_check_proxmox_healthy_when_enabled_with_token():

    config = AtlasConfig(
        proxmox=ProxmoxConfig(
            enabled=True,
            host="192.168.1.10",
            user="atlas@pve",
            token_name="atlas-token",
            token_value="secret",
        )
    )

    result = check_proxmox(config)

    assert result["status"] is True


def test_check_intelligence_unhealthy_without_api_key(monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = AtlasConfig(
        intelligence=IntelligenceConfig(provider="anthropic")
    )

    result = check_intelligence(config)

    assert result["status"] is False


def test_check_intelligence_healthy_with_api_key(monkeypatch):

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    config = AtlasConfig(
        intelligence=IntelligenceConfig(provider="anthropic")
    )

    result = check_intelligence(config)

    assert result["status"] is True


def test_check_intelligence_healthy_for_ollama_without_api_key(monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = AtlasConfig(
        intelligence=IntelligenceConfig(provider="ollama")
    )

    result = check_intelligence(config)

    assert result["status"] is True


def test_check_monitoring_healthy_when_disabled():

    result = check_monitoring(AtlasConfig())

    assert result["status"] is True
    assert result["details"] == "disabled"


def test_check_monitoring_healthy_when_enabled_with_url():

    config = AtlasConfig(
        monitoring=MonitoringConfig(
            enabled=True, prometheus_url="http://localhost:9090"
        )
    )

    result = check_monitoring(config)

    assert result["status"] is True
