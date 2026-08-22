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


def _run_remote_json(node, *atlas_args, timeout=20):
    """
    Shared by every "SSH out, run an atlas --json subcommand, parse
    the payload" fleet collector (run_remote_doctor, run_remote_trends).
    Returns (reachable, payload, error) - payload is the parsed dict
    only when reachable is True, error is the reason only when it's
    False. Never raises: connection failure and unparseable remote
    output are both reported through the return value, not exceptions.

    BatchMode=yes means an auth prompt fails fast instead of hanging
    the whole fleet scan waiting on stdin that will never arrive.
    ConnectTimeout bounds the SSH handshake; the outer `timeout` bounds
    the whole call including the remote atlas subcommand's own work
    (a remote atlas doctor's reachability checks can themselves take
    several seconds - see atlas/health/checks.py).

    A remote command that ran and reported something unhealthy (e.g.
    atlas doctor finding a problem) exits non-zero but still prints
    valid JSON - that's a legitimate "reachable but unhealthy" result,
    not an SSH failure, so this does not use check=True.
    """

    ssh = get_client()

    if not ssh:
        return False, None, "ssh unavailable"

    try:
        result = subprocess.run(
            [ssh, *_ssh_args(node), "atlas", *atlas_args],
            capture_output=True,
            text=True,
            timeout=timeout
        )

    except (subprocess.SubprocessError, OSError) as error:
        return False, None, str(error)

    if result.returncode != 0 and not result.stdout.strip():
        return False, None, result.stderr.strip() or f"ssh exited {result.returncode}"

    try:
        payload = json.loads(result.stdout)

    except json.JSONDecodeError:
        return False, None, f"could not parse atlas {atlas_args[0]} output from remote host"

    return True, payload, None


def run_remote_doctor(node, timeout=20):
    """
    SSHes into a fleet node and runs `atlas doctor --json` there,
    reusing its {"checks": [...], "healthy": bool} payload rather than
    inventing a fleet-specific format.
    """

    reachable, payload, error = _run_remote_json(node, "doctor", "--json", timeout=timeout)

    if not reachable:
        return {
            "reachable": False,
            "error": error
        }

    return {
        "reachable": True,
        "healthy": payload.get("healthy", False),
        "checks": payload.get("checks", [])
    }


def run_remote_trends(node, limit=20, timeout=20):
    """
    SSHes into a fleet node and runs `atlas trends --limit <limit>
    --json` there, reusing its {"host": {...}, "containers": {...},
    "guests": {...}} payload. Unlike doctor, there's no "healthy"
    concept here - atlas trends itself has no health/threshold concept
    to signal, so reachability is the only pass/fail atlas fleet
    trends reports.
    """

    reachable, payload, error = _run_remote_json(
        node, "trends", "--limit", str(limit), "--json", timeout=timeout
    )

    if not reachable:
        return {
            "reachable": False,
            "error": error
        }

    return {
        "reachable": True,
        "host": payload.get("host", {}),
        "containers": payload.get("containers", {}),
        "guests": payload.get("guests", {})
    }


def run_remote_report(node, timeout=20):
    """
    SSHes into a fleet node and runs `atlas report --json` there,
    reusing its raw inventory-dict payload. Unlike doctor/trends,
    atlas report --json can legitimately print `null` (valid JSON) -
    a reachable node that just hasn't run atlas discover yet, not a
    parse failure - so that's its own case here, not folded into
    "reachable": False.
    """

    reachable, payload, error = _run_remote_json(node, "report", "--json", timeout=timeout)

    if not reachable:
        return {
            "reachable": False,
            "error": error
        }

    if payload is None:
        return {
            "reachable": True,
            "inventory": None
        }

    return {
        "reachable": True,
        "system": payload.get("system", {}),
        "hardware": payload.get("hardware", {}),
        "storage": payload.get("storage", []),
        "network": payload.get("network", {})
    }
