import platform
import shutil
from pathlib import Path

import psutil


def check_python():
    return {
        "name": "Python",
        "status": True,
        "details": platform.python_version(),
    }


def check_memory():

    memory = psutil.virtual_memory()

    healthy = memory.percent < 90

    return {
        "name": "Memory",
        "status": healthy,
        "details": f"{memory.percent}% used",
    }


def check_storage():

    disk = psutil.disk_usage("/")

    healthy = disk.percent < 90

    return {
        "name": "Storage",
        "status": healthy,
        "details": f"{disk.percent}% used",
    }


def check_docker():

    from atlas.docker import collect_containers

    result = collect_containers()

    return {
        "name": "Docker",
        "status": result["available"],
        "details": (
            f"{len(result['containers'])} containers"
            if result["available"]
            else "not available"
        ),
    }


def check_inventory():

    exists = Path(
        "inventory/generated/system-inventory.yaml"
    ).exists()

    return {
        "name": "Inventory",
        "status": exists,
        "details": (
            "available"
            if exists
            else "missing"
        ),
    }


def run_checks():

    return [
        check_python(),
        check_memory(),
        check_storage(),
        check_docker(),
        check_inventory(),
    ]
