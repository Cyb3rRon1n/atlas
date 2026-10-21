import os
import platform
import shutil
from pathlib import Path

import psutil
import requests

from atlas.config import load_config
from atlas.docker.manager import get_client


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


def find_deleted_mounts(mountinfo):
    """
    Mount points whose source was deleted after the container started.
    When a bind-mounted host folder is removed and recreated, the running
    container keeps the dead directory (it sees it empty) and the kernel
    marks the mount's root field (4th column of mountinfo) "//deleted".
    """

    stale = []

    for line in mountinfo.splitlines():

        fields = line.split(" ")

        if len(fields) > 4 and fields[3].endswith("//deleted"):
            stale.append(fields[4].replace("\\040", " "))

    return stale


def _read_host_mountinfo(pid, container_id):
    """
    Only trusted when /proc/<pid> really is that container - with a remote
    Docker daemon, or Atlas in its own PID namespace, the same PID can be an
    unrelated local process, so its cgroup must name the container id.
    """

    try:
        if container_id not in Path(f"/proc/{pid}/cgroup").read_text():
            return None
        return Path(f"/proc/{pid}/mountinfo").read_text()
    except OSError:
        return None


def check_stale_mounts():
    """
    Flags containers still pointing at a deleted bind-mount source. Reads
    /proc/<pid>/mountinfo from the host (world-readable, no root needed);
    when Atlas itself runs in a container and can't see host PIDs, falls
    back to reading the container's own /proc/1/mountinfo via docker exec.
    """

    client = get_client()

    if not client:
        return {
            "name": "Mounts",
            "status": True,
            "details": "skipped - Docker not available",
        }

    stale = {}
    checked = 0

    for container in client.containers.list():

        mountinfo = _read_host_mountinfo(
            container.attrs.get("State", {}).get("Pid"),
            container.id,
        )

        if mountinfo is None:

            try:
                exit_code, output = container.exec_run(["cat", "/proc/1/mountinfo"])
            except Exception:
                continue

            if exit_code != 0:
                continue

            mountinfo = output.decode(errors="replace")

        checked += 1
        deleted = find_deleted_mounts(mountinfo)

        if deleted:
            stale[container.name] = deleted

    if not stale:
        return {
            "name": "Mounts",
            "status": True,
            "details": f"{checked} containers checked, no stale bind mounts",
        }

    return {
        "name": "Mounts",
        "status": False,
        "details": (
            "stale bind mounts (source folder was deleted/recreated): "
            + "; ".join(f"{name}: {', '.join(paths)}" for name, paths in stale.items())
            + " - fix: docker compose up -d --force-recreate "
            + " ".join(stale)
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
        check_stale_mounts(),
        check_environment(),
        check_inventory(),
        check_proxmox(config),
        check_intelligence(config),
        check_monitoring(config),
    ]
