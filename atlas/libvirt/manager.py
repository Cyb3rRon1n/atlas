import shutil
import subprocess


def get_client():
    """
    Returns the virsh binary path if libvirt/KVM is reachable on this
    host, or None - same availability-gate shape as
    atlas.docker.manager.get_client(). Shells out to virsh rather than
    the libvirt-python bindings, which need a compiled extension built
    against the host's libvirt C library - not a fit for this
    project's pure-Python dependency posture (proxmoxer/docker-py/
    requests are all pure-Python).
    """

    return shutil.which("virsh")


def _run(virsh, *args):

    return subprocess.run(
        [virsh, *args],
        capture_output=True,
        text=True,
        timeout=5,
        check=True
    )


def collect_guests():

    virsh = get_client()

    if not virsh:
        return {
            "available": False,
            "guests": []
        }

    try:
        result = _run(virsh, "list", "--all", "--name")

    except (subprocess.SubprocessError, OSError):
        return {
            "available": False,
            "guests": []
        }

    names = [
        name.strip()
        for name in result.stdout.splitlines()
        if name.strip()
    ]

    return {
        "available": True,
        "guests": [_guest_info(virsh, name) for name in names]
    }


def _guest_info(virsh, name):

    try:
        state = _run(virsh, "domstate", name).stdout.strip()

    except (subprocess.SubprocessError, OSError):
        state = "unknown"

    try:
        uuid = _run(virsh, "domuuid", name).stdout.strip()

    except (subprocess.SubprocessError, OSError):
        uuid = ""

    return {
        "name": name,
        "uuid": uuid,
        "state": state,
    }


def get_guest_info(name):
    """
    Look up a single guest's current state by name, for the CLI's
    "show current state before confirming" step - same {"found": bool,
    ...} shape as atlas.docker.manager.get_container_info()/
    atlas.proxmox.manager.get_guest_info().
    """

    virsh = get_client()

    if not virsh:
        return {
            "found": False,
            "error": "libvirt/virsh unavailable"
        }

    try:
        state = _run(virsh, "domstate", name).stdout.strip()

    except (subprocess.SubprocessError, OSError):
        return {
            "found": False,
            "error": f"No libvirt guest named '{name}' found"
        }

    return {
        "found": True,
        "name": name,
        "state": state,
    }


def restart_guest(name):
    """
    Sends an ACPI reboot request via `virsh reboot` - like Proxmox's
    own restart_guest(), this has no automatic force-fallback if the
    guest OS isn't listening (unlike Docker's container.restart()),
    so a stuck guest can leave this stalled rather than guaranteeing
    completion. Same pure result-dict, never-raises shape as every
    other manager function in this codebase.
    """

    virsh = get_client()

    if not virsh:
        return {
            "success": False,
            "error": "libvirt/virsh unavailable"
        }

    try:
        _run(virsh, "reboot", name)

    except subprocess.CalledProcessError as error:
        return {
            "success": False,
            "error": error.stderr.strip() if error.stderr else str(error)
        }

    except (subprocess.SubprocessError, OSError) as error:
        return {
            "success": False,
            "error": str(error)
        }

    return {
        "success": True
    }
