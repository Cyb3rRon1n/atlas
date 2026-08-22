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


def _run(virsh, *args, connect_uri=None):
    """
    connect_uri, when given, is passed as `-c <uri>` - libvirt's own
    native remote-connection mechanism (e.g. qemu+ssh://user@host/
    system), shelling through the system ssh binary under the hood.
    No new dependency, unlike Docker's ssh:// transport.
    """

    prefix = ["-c", connect_uri] if connect_uri else []

    return subprocess.run(
        [virsh, *prefix, *args],
        capture_output=True,
        text=True,
        timeout=5,
        check=True
    )


def _connect_uri(node):

    return f"qemu+ssh://{node.user}@{node.host}/system" if node else None


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


def get_guest_info(name, node=None):
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
        state = _run(virsh, "domstate", name, connect_uri=_connect_uri(node)).stdout.strip()

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


def _run_command(virsh, *args, connect_uri=None):
    """
    Shared by every mutating guest command (reboot/shutdown/setvcpus/
    setmem) - runs virsh and converts a failure into the pure
    result-dict shape every manager function in this codebase uses,
    never raising.
    """

    try:
        _run(virsh, *args, connect_uri=connect_uri)

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


def restart_guest(name, node=None):
    """
    Sends an ACPI reboot request via `virsh reboot` - like Proxmox's
    own restart_guest(), this has no automatic force-fallback if the
    guest OS isn't listening (unlike Docker's container.restart()),
    so a stuck guest can leave this stalled rather than guaranteeing
    completion.
    """

    virsh = get_client()

    if not virsh:
        return {
            "success": False,
            "error": "libvirt/virsh unavailable"
        }

    return _run_command(virsh, "reboot", name, connect_uri=_connect_uri(node))


def stop_guest(name, node=None):
    """
    Sends an ACPI shutdown request via `virsh shutdown` - not `virsh
    destroy`, which despite its name is libvirt's hard power-off (it
    doesn't delete the guest). Same choice and same caveat as
    Proxmox's stop_guest: no automatic force-fallback if the guest OS
    isn't listening.
    """

    virsh = get_client()

    if not virsh:
        return {
            "success": False,
            "error": "libvirt/virsh unavailable"
        }

    return _run_command(virsh, "shutdown", name, connect_uri=_connect_uri(node))


def resize_guest(name, vcpus=None, memory=None, node=None):
    """
    setvcpus/setmem are separate virsh subcommands (unlike Docker's
    single update call or Proxmox's single resize endpoint), so this
    is up to two calls. --config only - applies at next boot, not
    live. A running guest needing this immediately would need --live
    too, which requires hotplug already configured on that guest -
    the same class of gotcha Proxmox's own QEMU resize work found
    real surprises in (see CLAUDE.md). Deliberately not attempted
    here; the CLI's confirmation text says a restart may be needed
    instead. vcpus is an integer *count* of virtual CPUs (topology),
    not a fractional core limit like Docker's --cpus/Proxmox's
    cpulimit - a genuinely different concept despite similar naming.
    """

    virsh = get_client()

    if not virsh:
        return {
            "success": False,
            "error": "libvirt/virsh unavailable"
        }

    connect_uri = _connect_uri(node)

    if vcpus is not None:

        result = _run_command(
            virsh, "setvcpus", name, str(vcpus), "--config", connect_uri=connect_uri
        )

        if not result["success"]:
            return result

    if memory is not None:

        result = _run_command(
            virsh, "setmem", name, memory, "--config", connect_uri=connect_uri
        )

        if not result["success"]:
            return result

    return {
        "success": True
    }
