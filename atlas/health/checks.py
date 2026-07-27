import os
import platform
import shutil
from pathlib import Path

import psutil

from atlas.config import load_config


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


def check_proxmox(config):

    proxmox = config.proxmox

    if not proxmox.enabled:
        return {
            "name": "Proxmox",
            "status": True,
            "details": "disabled",
        }

    has_host = bool(proxmox.host)

    has_auth = bool(
        proxmox.token_name and proxmox.token_value
    ) or bool(proxmox.password)

    healthy = has_host and has_auth

    return {
        "name": "Proxmox",
        "status": healthy,
        "details": (
            "enabled, host and credentials configured"
            if healthy
            else "enabled but missing host or credentials"
        ),
    }


def check_intelligence(config):

    provider = config.intelligence.provider

    if provider == "anthropic":

        healthy = bool(os.environ.get("ANTHROPIC_API_KEY"))

        details = (
            "anthropic, ANTHROPIC_API_KEY set"
            if healthy
            else "anthropic, ANTHROPIC_API_KEY not set"
        )

    elif provider == "ollama":

        healthy = True
        details = f"ollama, {config.intelligence.ollama_host}"

    else:

        healthy = False
        details = f"unknown provider '{provider}'"

    return {
        "name": "Intelligence",
        "status": healthy,
        "details": details,
    }


def check_monitoring(config):

    monitoring = config.monitoring

    if not monitoring.enabled:
        return {
            "name": "Monitoring",
            "status": True,
            "details": "disabled",
        }

    healthy = bool(monitoring.prometheus_url)

    return {
        "name": "Monitoring",
        "status": healthy,
        "details": (
            f"enabled, {monitoring.prometheus_url}"
            if healthy
            else "enabled but no prometheus_url configured"
        ),
    }


def run_checks():

    config = load_config()

    return [
        check_python(),
        check_memory(),
        check_storage(),
        check_docker(),
        check_inventory(),
        check_proxmox(config),
        check_intelligence(config),
        check_monitoring(config),
    ]
