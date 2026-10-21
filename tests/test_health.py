from pathlib import Path
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
    _read_host_mountinfo,
    check_stale_mounts,
    check_storage,
    find_deleted_mounts,
    run_checks,
)


def test_run_checks_returns_ten_named_checks(isolated_cwd, monkeypatch):

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    checks = run_checks()

    assert [c["name"] for c in checks] == [
        "Python", "Memory", "Storage", "Docker", "Mounts", "Environment", "Inventory",
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


MOUNTINFO_OK = (
    "1041 1022 0:118 / / rw,relatime - overlay overlay rw\n"
    "1052 1041 259:3 /home/me/media/downloads /data/downloads rw,relatime - ext4 /dev/md0 rw\n"
)
MOUNTINFO_STALE = MOUNTINFO_OK + (
    "1053 1041 259:3 /home/me/media/books\\040old//deleted /books rw,relatime - ext4 /dev/md0 rw\n"
)


def test_find_deleted_mounts_flags_only_deleted_sources():

    assert find_deleted_mounts(MOUNTINFO_OK) == []
    assert find_deleted_mounts(MOUNTINFO_STALE) == ["/books"]


def _fake_container(name, pid, exec_output=None):

    container = MagicMock()
    container.name = name
    container.attrs = {"State": {"Pid": pid}}
    container.exec_run.return_value = (0, exec_output.encode()) if exec_output is not None else (1, b"")
    return container


def test_check_stale_mounts_flags_container_and_suggests_recreate(monkeypatch):

    client = MagicMock()
    client.containers.list.return_value = [
        _fake_container("chaptarr", 101, MOUNTINFO_STALE),
        _fake_container("radarr", 102, MOUNTINFO_OK),
    ]
    monkeypatch.setattr("atlas.health.checks.get_client", lambda: client)
    # host /proc not readable (e.g. Atlas itself in a container) -> docker exec fallback
    monkeypatch.setattr("atlas.health.checks._read_host_mountinfo", lambda pid, cid: None)

    result = check_stale_mounts()

    assert result["name"] == "Mounts"
    assert result["status"] is False
    assert "chaptarr: /books" in result["details"]
    assert "radarr" not in result["details"]
    assert "--force-recreate chaptarr" in result["details"]


def test_check_stale_mounts_prefers_host_proc_and_is_healthy_when_clean(monkeypatch):

    container = _fake_container("radarr", 102)
    client = MagicMock()
    client.containers.list.return_value = [container]
    monkeypatch.setattr("atlas.health.checks.get_client", lambda: client)
    monkeypatch.setattr("atlas.health.checks._read_host_mountinfo", lambda pid, cid: MOUNTINFO_OK)

    result = check_stale_mounts()

    assert result["status"] is True
    assert "1 containers checked" in result["details"]
    container.exec_run.assert_not_called()


def test_check_stale_mounts_skips_when_docker_unavailable(monkeypatch):

    monkeypatch.setattr("atlas.health.checks.get_client", lambda: None)

    result = check_stale_mounts()

    assert result["status"] is True
    assert "skipped" in result["details"]


def test_read_host_mountinfo_rejects_a_pid_that_is_not_the_container(tmp_path, monkeypatch):

    # same PID, different process (remote daemon / own PID namespace): cgroup doesn't name the container
    real_path = Path
    proc = tmp_path / "proc" / "4521"
    proc.mkdir(parents=True)
    (proc / "cgroup").write_text("0::/user.slice/user-1000.slice/session-2.scope\n")
    (proc / "mountinfo").write_text(MOUNTINFO_STALE)
    monkeypatch.setattr("atlas.health.checks.Path", lambda p: real_path(str(tmp_path) + p))

    assert _read_host_mountinfo(4521, "abc123") is None

    (proc / "cgroup").write_text("0::/system.slice/docker-abc123def.scope\n")
    assert _read_host_mountinfo(4521, "abc123") == MOUNTINFO_STALE
