import json
import shutil
import subprocess


def get_client():
    """
    Returns the ssh binary path, or None - same availability-gate
    shape as every other manager module in this codebase (Docker's
    docker.from_env, libvirt's virsh). No new dependency: shells out
    to the system ssh client rather than a Python SSH library.
    """

    return shutil.which("ssh")


def _ssh_args(node):

    args = [
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-p", str(node.port),
    ]

    if node.identity_file:
        args += ["-i", node.identity_file]

    args.append(f"{node.user}@{node.host}")

    return args


def run_remote_doctor(node, timeout=20):
    """
    SSHes into a fleet node and runs `atlas doctor --json` there,
    parsing its {"checks": [...], "healthy": bool} payload - the same
    shape atlas doctor already produces locally, reused rather than
    inventing a fleet-specific format. Never raises: connection
    failure and unparseable remote output are both reported as
    "reachable": False with a distinguishing "error", not exceptions.

    BatchMode=yes means an auth prompt fails fast instead of hanging
    the whole fleet scan waiting on stdin that will never arrive.
    ConnectTimeout bounds the SSH handshake; the outer `timeout` bounds
    the whole call including the remote atlas doctor's own reachability
    checks (which can themselves take several seconds - see
    atlas/health/checks.py).

    A remote atlas doctor that ran and found something unhealthy exits
    1 but still prints valid JSON - that's a legitimate "reachable but
    unhealthy" result, not an SSH failure, so this does not use
    check=True.
    """

    ssh = get_client()

    if not ssh:
        return {
            "reachable": False,
            "error": "ssh unavailable"
        }

    try:
        result = subprocess.run(
            [ssh, *_ssh_args(node), "atlas", "doctor", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout
        )

    except (subprocess.SubprocessError, OSError) as error:
        return {
            "reachable": False,
            "error": str(error)
        }

    if result.returncode != 0 and not result.stdout.strip():
        return {
            "reachable": False,
            "error": result.stderr.strip() or f"ssh exited {result.returncode}"
        }

    try:
        payload = json.loads(result.stdout)

    except json.JSONDecodeError:
        return {
            "reachable": False,
            "error": "could not parse atlas doctor output from remote host"
        }

    return {
        "reachable": True,
        "healthy": payload.get("healthy", False),
        "checks": payload.get("checks", [])
    }
