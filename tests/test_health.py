from unittest.mock import MagicMock, patch

import requests

from atlas.config.models import (
    AtlasConfig,
    IntelligenceConfig,
    MonitoringConfig,
    ProxmoxConfig,
)
from atlas.health.checks import (
    check_docker,
    check_environment,
    check_intelligence,
    check_inventory,
    check_memory,
    check_monitoring,
    check_proxmox,
    check_python,
    check_storage,
    run_checks,
)


def test_run_checks_returns_nine_named_checks(isolated_cwd, monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    checks = run_checks()

    assert [c["name"] for c in checks] == [
        "Python", "Memory", "Storage", "Docker", "Environment", "Inventory",
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


def test_check_proxmox_healthy_when_enabled_and_reachable():

    config = AtlasConfig(
        proxmox=ProxmoxConfig(
            enabled=True,
            host="192.168.1.10",
            user="atlas@pve",
            token_name="atlas-token",
            token_value="secret",
        )
    )

    mock_client = MagicMock()
    mock_client.version.get.return_value = {"version": "8.0"}

    with patch("atlas.proxmox.client.connect", return_value=mock_client):
        result = check_proxmox(config)

    assert result["status"] is True
    assert "reachable" in result["details"]


def test_check_proxmox_unhealthy_when_enabled_but_unreachable():

    config = AtlasConfig(
        proxmox=ProxmoxConfig(
            enabled=True,
            host="192.168.1.10",
            user="atlas@pve",
            token_name="atlas-token",
            token_value="secret",
        )
    )

    mock_client = MagicMock()
    mock_client.version.get.side_effect = RuntimeError("connection refused")

    with patch("atlas.proxmox.client.connect", return_value=mock_client):
        result = check_proxmox(config)

    assert result["status"] is False
    assert "unreachable" in result["details"]


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


def test_check_intelligence_healthy_for_ollama_when_reachable(monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = AtlasConfig(
        intelligence=IntelligenceConfig(provider="ollama")
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("atlas.health.checks.requests.get", return_value=mock_response):
        result = check_intelligence(config)

    assert result["status"] is True
    assert "reachable" in result["details"]


def test_check_intelligence_unhealthy_for_ollama_when_unreachable(monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = AtlasConfig(
        intelligence=IntelligenceConfig(provider="ollama")
    )

    with patch(
        "atlas.health.checks.requests.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        result = check_intelligence(config)

    assert result["status"] is False
    assert "unreachable" in result["details"]


def test_check_monitoring_healthy_when_disabled():

    result = check_monitoring(AtlasConfig())

    assert result["status"] is True
    assert result["details"] == "disabled"


def test_check_monitoring_healthy_when_enabled_and_reachable():

    config = AtlasConfig(
        monitoring=MonitoringConfig(
            enabled=True, prometheus_url="http://localhost:9090"
        )
    )

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("atlas.health.checks.requests.get", return_value=mock_response):
        result = check_monitoring(config)

    assert result["status"] is True
    assert "reachable" in result["details"]


def test_check_monitoring_unhealthy_when_enabled_but_unreachable():

    config = AtlasConfig(
        monitoring=MonitoringConfig(
            enabled=True, prometheus_url="http://localhost:9090"
        )
    )

    with patch(
        "atlas.health.checks.requests.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        result = check_monitoring(config)

    assert result["status"] is False
    assert "unreachable" in result["details"]


def test_check_environment_reports_none_detected(monkeypatch):

    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.setattr("atlas.health.checks.shutil.which", lambda name: None)
    monkeypatch.setattr("atlas.health.checks.Path.exists", lambda self: False)

    result = check_environment()

    assert result["status"] is True
    assert "no additional" in result["details"]


def test_check_environment_detects_libvirt(monkeypatch):

    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)

    monkeypatch.setattr(
        "atlas.health.checks.shutil.which",
        lambda name: "/usr/bin/virsh" if name == "virsh" else None,
    )

    monkeypatch.setattr("atlas.health.checks.Path.exists", lambda self: False)

    result = check_environment()

    assert result["status"] is True
    assert "libvirt/KVM" in result["details"]


def test_check_environment_detects_kubernetes_in_cluster(monkeypatch):

    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.setattr("atlas.health.checks.shutil.which", lambda name: None)
    monkeypatch.setattr("atlas.health.checks.Path.exists", lambda self: False)

    result = check_environment()

    assert result["status"] is True
    assert "Kubernetes" in result["details"]
