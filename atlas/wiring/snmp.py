"""
SNMP source: any managed switch that speaks the standard MIBs (IF-MIB, LLDP-MIB,
BRIDGE-MIB / Q-BRIDGE-MIB). Shells out to net-snmp's snmpbulkwalk - the same
"call the system tool" choice atlas made for ssh and virsh - so there is no
compiled Python dependency. Passphrases go through a private snmp.conf
(SNMPCONFPATH), never argv, where any local `ps` could read them.
"""

import os
import re
import shutil
import subprocess
import tempfile

from atlas.wiring import WiringError, env_key, normalize_mac


OIDS = {
    "sysName": "1.3.6.1.2.1.1.5",
    "lldpLocChassis": "1.0.8802.1.1.2.1.3.2",
    "ifName": "1.3.6.1.2.1.31.1.1.1.1",
    "ifOper": "1.3.6.1.2.1.2.2.1.8",
    "ifHighSpeed": "1.3.6.1.2.1.31.1.1.1.15",
    "ifAlias": "1.3.6.1.2.1.31.1.1.1.18",
    "basePort": "1.3.6.1.2.1.17.1.4.1.2",
    "qFdb": "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "dFdb": "1.3.6.1.2.1.17.4.3.1.2",
    "lldpRem": "1.0.8802.1.1.2.1.4.1.1",
}

LINE = re.compile(r"^\.([\d.]+) = (.*)$")
TYPE = re.compile(r"^[A-Za-z0-9-]+: ?")


def parse_walk(text, base):

    values, last = {}, None

    for raw in (text or "").splitlines():
        match = LINE.match(raw.strip())

        if not match:
            if last is not None and raw.strip():
                values[last] = f"{values[last]} {raw.strip()}".strip()
            continue

        oid, value = match.groups()
        last = None

        if not oid.startswith(base + ".") or value.startswith(("No Such", "No more")):
            continue

        last = oid[len(base) + 1:]
        values[last] = TYPE.sub("", value).strip().strip('"')

    return values


def _mac_from_index(parts):

    return ":".join(f"{int(part):02x}" for part in parts)


def parse_switch(walks):

    get = lambda key: parse_walk(walks.get(key, ""), OIDS[key])
    names, oper, speed, alias = get("ifName"), get("ifOper"), get("ifHighSpeed"), get("ifAlias")
    base = get("basePort")      # bridge port -> ifIndex

    ports = {}
    for index in sorted(set(base.values()), key=int):
        if index in names:
            status = oper.get(index, "")
            ports[names[index]] = {"index": int(index), "up": status.startswith("up") or status == "1",
                                   "speed": int(speed.get(index) or 0), "alias": alias.get(index, "")}

    def port_name(bridge_port):
        return names.get(base.get(bridge_port, ""))

    fdb = []
    q = get("qFdb")
    for suffix, bridge_port in q.items():
        parts = suffix.split(".")
        if len(parts) == 7 and port_name(bridge_port):
            fdb.append({"port": port_name(bridge_port), "mac": _mac_from_index(parts[1:]), "vlan": int(parts[0])})
    if not q:
        for suffix, bridge_port in get("dFdb").items():
            parts = suffix.split(".")
            if len(parts) == 6 and port_name(bridge_port):
                fdb.append({"port": port_name(bridge_port), "mac": _mac_from_index(parts), "vlan": None})

    remote = {}
    for suffix, value in get("lldpRem").items():
        parts = suffix.split(".")       # column.timemark.localPort.index
        if len(parts) == 4:
            remote.setdefault((parts[2], parts[3]), {})[parts[0]] = value

    neighbors = []
    for (local_port, _), columns in sorted(remote.items()):
        port = names.get(local_port)
        if not port:
            continue
        chassis, port_id = columns.get("5", ""), columns.get("7", "")
        neighbors.append({"port": port, "chassis_mac": normalize_mac(chassis), "chassis": chassis,
                          "remote_port": port_id, "remote_port_mac": normalize_mac(port_id),
                          "remote_port_desc": columns.get("8", ""), "sys_name": columns.get("9", "")})

    sys_name = next(iter(get("sysName").values()), "")
    chassis = normalize_mac(next(iter(get("lldpLocChassis").values()), ""))

    return {"sys_name": sys_name, "chassis_mac": chassis, "ports": ports, "fdb": fdb, "neighbors": neighbors}


def walk_switch(switch, env, timeout, run=subprocess.run, which=shutil.which):

    binary = which("snmpbulkwalk")
    if not binary:
        raise WiringError("snmpbulkwalk not found - install net-snmp (Debian/Ubuntu: apt install snmp)")

    key = env_key(switch.name)
    auth, priv = env.get(f"ATLAS_SNMP_{key}_AUTH"), env.get(f"ATLAS_SNMP_{key}_PRIV")
    if not auth or not priv:
        raise WiringError(f"set ATLAS_SNMP_{key}_AUTH and ATLAS_SNMP_{key}_PRIV in the atlas env file")

    walks = {}
    with tempfile.TemporaryDirectory() as conf_dir:
        conf = os.path.join(conf_dir, "snmp.conf")
        with open(os.open(conf, os.O_WRONLY | os.O_CREAT, 0o600), "w") as handle:
            handle.write(f"defVersion 3\ndefSecurityName {switch.snmp_user}\ndefSecurityLevel authPriv\n"
                         f"defAuthType SHA\ndefPrivType {switch.priv.upper()}\n"
                         f"defAuthPassphrase {auth}\ndefPrivPassphrase {priv}\n")
        child_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SNMPCONFPATH": conf_dir, "MIBS": ""}

        for name, oid in OIDS.items():
            if name == "dFdb" and walks.get("qFdb", "").strip():
                walks[name] = ""
                continue
            try:
                result = run([binary, "-On", "-t", str(timeout), "-r", "1", switch.host, oid],
                             capture_output=True, text=True, timeout=timeout * 4, env=child_env)
            except subprocess.TimeoutExpired:
                raise WiringError(f"{switch.name}: SNMP walk timed out")
            if result.returncode != 0:
                first = (result.stderr or "").strip().splitlines()[:1]
                raise WiringError(f"{switch.name}: {first[0] if first else 'snmpbulkwalk failed'}")
            walks[name] = result.stdout

    return walks


def collect_switch(switch, env, timeout, **kwargs):

    result = parse_switch(walk_switch(switch, env, timeout, **kwargs))

    return {**result, "name": switch.name, "host": switch.host, "weak_privacy": switch.priv == "des"}