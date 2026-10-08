"""
Live connection table from the kernel via `conntrack -L -o extended,id`
(netlink; /proc/net/nf_conntrack does not exist on current kernels). Byte
counters only appear when net.netfilter.nf_conntrack_acct=1 - without it every
flow parses with 0 bytes rather than failing.
"""

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Flow:
    id: int | None
    proto: str
    state: str
    src: str
    dst: str
    sport: int | None
    dport: int | None
    reply_src: str
    reply_dst: str
    bytes_out: int
    bytes_in: int


def _parse_line(line):

    tokens = line.split()

    if len(tokens) < 6 or tokens[0] not in ("ipv4", "ipv6"):
        return None

    proto = tokens[2]
    state = tokens[5] if tokens[5].isupper() and "=" not in tokens[5] else ""
    orig, reply, flow_id = {}, {}, None

    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep:
            continue
        if key == "id":
            flow_id = int(value)
            continue
        target = orig if key not in orig else reply
        target[key] = value

    if "src" not in orig or "dst" not in orig:
        return None

    port = lambda d, k: int(d[k]) if k in d else None

    return Flow(id=flow_id, proto=proto, state=state, src=orig["src"], dst=orig["dst"],
                sport=port(orig, "sport"), dport=port(orig, "dport"),
                reply_src=reply.get("src", ""), reply_dst=reply.get("dst", ""),
                bytes_out=int(orig.get("bytes", 0)), bytes_in=int(reply.get("bytes", 0)))


def parse_conntrack(text):
    return [flow for flow in (_parse_line(line) for line in text.splitlines()) if flow is not None]


def read_conntrack(run=subprocess.run):

    result = run(["conntrack", "-L", "-o", "extended,id"], capture_output=True, text=True, timeout=10)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"conntrack exited {result.returncode}")

    return parse_conntrack(result.stdout)
