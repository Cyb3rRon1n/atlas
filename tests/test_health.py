from unittest.mock import patch

from atlas.health.checks import (
    check_docker,
    check_inventory,
    check_memory,
    check_python,
    check_storage,
    run_checks,
)


def test_run_checks_returns_five_named_checks():

    checks = run_checks()

    assert [c["name"] for c in checks] == [
        "Python", "Memory", "Storage", "Docker", "Inventory"
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
