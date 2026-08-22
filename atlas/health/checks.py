import os
import platform
import shutil
from pathlib import Path

import psutil
import requests

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

    if not (has_host and has_auth):
        return {
            "name": "Proxmox",
            "status": False,
            "details": "enabled but missing host or credentials",
        }

    from atlas.proxmox.client import connect

    client = connect(
        proxmox.host,
        proxmox.user,
        password=proxmox.password,
        token_name=proxmox.token_name,
        token_value=proxmox.token_value,
        verify_ssl=proxmox.verify_ssl,
    )

    if client is None:
        return {
            "name": "Proxmox",
            "status": False,
            "details": "enabled, configured, but connection failed",
        }

    try:
        client.version.get()

    except Exception as error:
        return {
            "name": "Proxmox",
            "status": False,
            "details": f"enabled, configured, but unreachable: {error}",
        }

    return {
        "name": "Proxmox",
        "status": True,
        "details": "enabled, configured, and reachable",
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

        host = config.intelligence.ollama_host

        try:
            requests.get(f"{host.rstrip('/')}/api/tags", timeout=3).raise_for_status()

            healthy = True
            details = f"ollama, {host}, reachable"

        except requests.exceptions.RequestException as error:
            healthy = False
            details = f"ollama, {host}, unreachable: {error}"

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

    if not monitoring.prometheus_url:
        return {
            "name": "Monitoring",
            "status": False,
            "details": "enabled but no prometheus_url configured",
        }

    url = monitoring.prometheus_url

    try:
        requests.get(f"{url.rstrip('/')}/-/healthy", timeout=3).raise_for_status()

        return {
            "name": "Monitoring",
            "status": True,
            "details": f"enabled, {url}, reachable",
        }

    except requests.exceptions.RequestException as error:
        return {
            "name": "Monitoring",
            "status": False,
            "details": f"enabled, {url}, unreachable: {error}",
        }


def check_environment():
    """
    Informational, always healthy: reports virtualization/orchestration
    backends Atlas detects beyond Docker/Proxmox, so a libvirt/KVM or
    Kubernetes host sees itself acknowledged by doctor rather than
    silently ignored.
    """

    detected = []

    if shutil.which("virsh") or Path("/var/run/libvirt/libvirt-sock").exists():
        detected.append("libvirt/KVM (discoverable via atlas discover, no actions yet)")

    if (
        os.environ.get("KUBERNETES_SERVICE_HOST")
        or shutil.which("kubectl")
        or (Path.home() / ".kube" / "config").exists()
    ):
        detected.append("Kubernetes (not managed by Atlas)")

    return {
        "name": "Environment",
        "status": True,
        "details": (
            "; ".join(detected)
            if detected
            else "no additional virtualization/orchestration backends detected"
        ),
    }


def run_checks():

    config = load_config()

    return [
        check_python(),
        check_memory(),
        check_storage(),
        check_docker(),
        check_environment(),
        check_inventory(),
        check_proxmox(config),
        check_intelligence(config),
        check_monitoring(config),
    ]
