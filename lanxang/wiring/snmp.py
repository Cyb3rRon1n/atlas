"""
SNMP source: any managed switch that speaks the standard MIBs (IF-MIB, LLDP-MIB,
BRIDGE-MIB / Q-BRIDGE-MIB). Shells out to net-snmp's snmpbulkwalk - the same
"call the system tool" choice atlas made for ssh and virsh - so there is no
compiled Python dependency. Passphrases go through a private snmp.conf
(SNMPCONFPATH), never argv, where any local `ps` could read them.
"""

import contextlib
import os
import re
import shutil
import subprocess
import tempfile

from lanxang.wiring import WiringError, env_key, normalize_mac


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

# Per-port health counters (cable health). Optional: a switch that lacks one (EtherLike-MIB is
# common but not universal) just reports nothing for it - the walk never fails because of them.
COUNTERS = {
    "inErrors": "1.3.6.1.2.1.2.2.1.14",
    "outErrors": "1.3.6.1.2.1.2.2.1.20",
    "inUcast": "1.3.6.1.2.1.2.2.1.11",
    "hcInUcast": "1.3.6.1.2.1.31.1.1.1.7",
    "hcInOctets": "1.3.6.1.2.1.31.1.1.1.6",     # bytes, for traffic graphs (64-bit: no wrap between scans)
    "hcOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
    "lastChange": "1.3.6.1.2.1.2.2.1.9",
    "fcs": "1.3.6.1.2.1.10.7.2.1.3",
    "align": "1.3.6.1.2.1.10.7.2.1.2",
    "late": "1.3.6.1.2.1.10.7.2.1.8",
    "duplex": "1.3.6.1.2.1.10.7.2.1.19",
}

# PoE (POWER-ETHERNET-MIB, RFC 3621). Optional like COUNTERS: switches without PoE answer nothing.
POE = {
    "psePort": "1.3.6.1.2.1.105.1.1.1",     # .3 admin enable, .6 detection status, .10 power class; index group.port
    "pseMain": "1.3.6.1.2.1.105.1.3.1.1",   # .2 budget W, .4 consumption W; index group
}

# Model, spanning tree, link bundles (IEEE 802.3ad LAG-MIB) and VLANs (Q-BRIDGE-MIB). Optional too:
# a switch that lacks a table just shows nothing for it.
TOPOLOGY = {
    "sysDescr": "1.3.6.1.2.1.1.1",
    "stp": "1.3.6.1.2.1.17.2.15.1.3",            # dot1dStpPortState, index = bridge port
    "lag": "1.2.840.10006.300.43.1.2.1.1.13",    # dot3adAggPortAttachedAggID, ifIndex -> aggregator ifIndex
    "pvid": "1.3.6.1.2.1.17.7.1.4.5.1.1",        # dot1qPvid, index = bridge port
    "vlanEgress": "1.3.6.1.2.1.17.7.1.4.2.1.4",  # dot1qVlanCurrentEgressPorts, index timemark.vlan
    "vlanUntagged": "1.3.6.1.2.1.17.7.1.4.2.1.5",
}

OPTIONAL = {**COUNTERS, **POE, **TOPOLOGY}

STP = {"1": "disabled", "2": "blocking", "3": "listening", "4": "learning", "5": "forwarding", "6": "broken"}

DETECTION = {"1": "disabled", "2": "searching", "3": "delivering", "4": "fault", "5": "test", "6": "fault"}

DUPLEX = {"2": "half", "3": "full"}     # dot3StatsDuplexStatus; 1 = unknown

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


def _number(value):
    """A counter or TimeTicks value as an int; None when the switch didn't report it."""

    match = re.search(r"\d+", value or "")

    return int(match.group()) if match else None


def port_counters(get_counter, index):

    value = lambda key: _number(get_counter(key).get(index))
    hc, ucast = value("hcInUcast"), value("inUcast")

    return {"in_errors": value("inErrors"), "out_errors": value("outErrors"),
            "fcs": value("fcs"), "align": value("align"), "late": value("late"),
            "packets": hc if hc else ucast,      # some switches (e.g. Cisco SG300) leave the 64-bit counter at 0
            "duplex": DUPLEX.get(get_counter("duplex").get(index, ""), "unknown"),
            "last_change": value("lastChange"), "in_bytes": value("hcInOctets"), "out_bytes": value("hcOutOctets")}


def _poe(get, names):
    """({port name: poe}, budget W, used W). The MIB's port number is the ifIndex on the switches
    seen so far. Limit: per-vendor group/port -> ifIndex maps if one numbers them differently."""

    columns = {}
    for suffix, value in get("psePort").items():
        parts = suffix.split(".")
        if len(parts) == 3:
            columns.setdefault(parts[2], {})[parts[0]] = re.sub(r"\D", "", value)

    ports = {}
    for number, cols in columns.items():
        if number in names:
            state = DETECTION.get(cols.get("6"), "unknown")
            power_class = int(cols["10"]) - 1 if cols.get("10", "").isdigit() and int(cols["10"]) > 0 else None
            ports[names[number]] = {"delivering": state == "delivering", "fault": state == "fault",
                                    "enabled": cols.get("3") != "2", "watts": None, "mode": state,
                                    "class": f"Class {power_class}" if power_class is not None else ""}

    main = {}
    for suffix, value in get("pseMain").items():
        column = suffix.split(".")[0]
        main[column] = (main.get(column) or 0) + (_number(value) or 0)

    return ports, main.get("2"), main.get("4")


def _bitmap(value):
    """A PortList (one bit per bridge port, port 1 = the first byte's top bit) -> set of bridge port numbers."""

    ports = set()
    for byte_number, octet in enumerate(re.findall(r"[0-9A-Fa-f]{2}", value or "")):
        for bit in range(8):
            if int(octet, 16) & (0x80 >> bit):
                ports.add(str(byte_number * 8 + bit + 1))

    return ports


CAPABILITIES = {"3": "bridge", "4": "access point", "5": "router"}   # LLDP system capability bits (1-based)


def _caps(value):
    """lldpRemSysCapEnabled -> {"bridge", "router", ...}; net-snmp prints it as hex or, when printable, as text."""

    value = value or ""
    if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}\s*)+", value.strip()):
        value = value.encode("latin-1", "replace").hex()

    return sorted(CAPABILITIES[bit] for bit in _bitmap(value) if bit in CAPABILITIES)


def _topology(get, ports, names, oper, speed, base):
    """Adds stp / lag / vlan / tagged to the port dicts (only where the switch reports them)."""

    by_bridge = {bridge: names.get(index) for bridge, index in base.items()}

    for bridge, value in get("stp").items():
        if by_bridge.get(bridge) in ports:
            ports[by_bridge[bridge]]["stp"] = STP.get(re.sub(r"\D", "", value), "unknown")

    for index, aggregator in get("lag").items():
        aggregator = re.sub(r"\D", "", aggregator)
        if aggregator in ("", "0", index) or index not in names or aggregator not in names:
            continue
        # a bundled port can drop out of the bridge table (the port-channel takes its place): keep it on the panel
        port = ports.setdefault(names[index], {"index": int(index), "up": oper.get(index, "").startswith("up")
                                               or oper.get(index) == "1", "speed": int(speed.get(index) or 0),
                                               "alias": "", "counters": {}})
        port["lag"] = names[aggregator]

    for bridge, value in get("pvid").items():
        if by_bridge.get(bridge) in ports:
            ports[by_bridge[bridge]]["vlan"] = int(_number(value) or 0)

    untagged = {suffix.split(".")[-1]: _bitmap(value) for suffix, value in get("vlanUntagged").items()}
    for suffix, value in get("vlanEgress").items():
        vlan = suffix.split(".")[-1]
        for bridge in _bitmap(value) - untagged.get(vlan, set()):
            if by_bridge.get(bridge) in ports:
                ports[by_bridge[bridge]].setdefault("tagged", []).append(int(vlan))


def parse_switch(walks):

    get = lambda key: parse_walk(walks.get(key, ""), {**OIDS, **OPTIONAL}[key])
    counters = {key: get(key) for key in COUNTERS}
    names, oper, speed, alias = get("ifName"), get("ifOper"), get("ifHighSpeed"), get("ifAlias")
    base = get("basePort")      # bridge port -> ifIndex

    ports = {}
    for index in sorted(set(base.values()), key=int):
        if index in names:
            status = oper.get(index, "")
            ports[names[index]] = {"index": int(index), "up": status.startswith("up") or status == "1",
                                   "speed": int(speed.get(index) or 0), "alias": alias.get(index, ""),
                                   "counters": port_counters(counters.__getitem__, index)}

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
                          "remote_port_desc": columns.get("8", ""), "sys_name": columns.get("9", ""),
                          "caps": _caps(columns.get("12", ""))})

    poe, budget, used = _poe(get, names)
    for name, info in poe.items():
        if name in ports:
            ports[name]["poe"] = info

    _topology(get, ports, names, oper, speed, base)

    sys_name = next(iter(get("sysName").values()), "")
    model = next(iter(get("sysDescr").values()), "").splitlines()[0][:80] if get("sysDescr") else ""
    chassis = normalize_mac(next(iter(get("lldpLocChassis").values()), ""))

    return {"sys_name": sys_name, "model": model, "chassis_mac": chassis, "ports": ports, "fdb": fdb, "neighbors": neighbors,
            "poe_budget_w": budget, "poe_used_w": used}


@contextlib.contextmanager
def _snmp(switch, env, which, tool="snmpbulkwalk"):
    """(binary, child env) with the passphrases in a private snmp.conf that's deleted afterwards."""

    binary = which(tool)
    if not binary:
        raise WiringError(f"{tool} not found - install net-snmp (Debian/Ubuntu: apt install snmp)")

    key = env_key(switch.name)
    if getattr(switch, "version", "3") == "2c":
        community = env.get(f"LANXANG_SNMP_{key}_COMMUNITY")
        if not community:
            raise WiringError(f"set LANXANG_SNMP_{key}_COMMUNITY (the read-only community) in the atlas env file")
        settings = f"defVersion 2c\ndefCommunity {community}\n"
    else:
        auth, priv = env.get(f"LANXANG_SNMP_{key}_AUTH"), env.get(f"LANXANG_SNMP_{key}_PRIV")
        if not auth or not priv:
            raise WiringError(f"set LANXANG_SNMP_{key}_AUTH and LANXANG_SNMP_{key}_PRIV in the atlas env file")
        settings = (f"defVersion 3\ndefSecurityName {switch.snmp_user}\ndefSecurityLevel authPriv\n"
                    f"defAuthType SHA\ndefPrivType {switch.priv.upper()}\n"
                    f"defAuthPassphrase {auth}\ndefPrivPassphrase {priv}\n")

    with tempfile.TemporaryDirectory() as conf_dir:
        conf = os.path.join(conf_dir, "snmp.conf")
        with open(os.open(conf, os.O_WRONLY | os.O_CREAT, 0o600), "w") as handle:
            handle.write(settings)
        yield binary, {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SNMPCONFPATH": conf_dir, "MIBS": ""}


HINTS = {      # net-snmp's terse errors, in words a person can act on
    "Timeout": "no answer from {host} - check the address, that SNMP is on, and the login (SNMPv3 user and "
               "passphrases, or the v2c community)",
    "Unknown user name": "the switch has no SNMPv3 user {user}",
    "Authentication failure": "the switch refused the auth passphrase",
    "Decryption error": "the privacy passphrase or type ({priv}) doesn't match the switch",
}


def _failure(switch, result):

    first = ((result.stderr or "").strip().splitlines() or ["SNMP request failed"])[0]
    hint = next((text for key, text in HINTS.items() if key in first), None)
    message = hint.format(host=switch.host, user=switch.snmp_user, priv=switch.priv.upper()) if hint else first

    return WiringError(f"{switch.name}: {message}")


def walk_switch(switch, env, timeout, run=subprocess.run, which=shutil.which):

    walks = {}
    with _snmp(switch, env, which) as (binary, child_env):
        for name, oid in {**OIDS, **OPTIONAL}.items():
            if name == "dFdb" and walks.get("qFdb", "").strip():
                walks[name] = ""
                continue
            try:
                result = run([binary, "-On", "-t", str(timeout), "-r", "1", switch.host, oid],
                             capture_output=True, text=True, timeout=timeout * 4, env=child_env)
            except subprocess.TimeoutExpired:
                raise WiringError(f"{switch.name}: SNMP walk timed out")
            if result.returncode != 0 and name in OPTIONAL:
                walks[name] = ""        # optional health counter / PoE table: leave it out, keep the scan
                continue
            if result.returncode != 0:
                raise _failure(switch, result)
            walks[name] = result.stdout

    return walks


def probe_switch(switch, env, timeout, run=subprocess.run, which=shutil.which):
    """One read-only request (sysName + sysDescr) to check the address and passphrases: (name, description)."""

    with _snmp(switch, env, which, "snmpget") as (binary, child_env):
        try:
            result = run([binary, "-On", "-Oqv", "-t", str(timeout), "-r", "1", switch.host,
                          "1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.1.0"],
                         capture_output=True, text=True, timeout=timeout * 3, env=child_env)
        except subprocess.TimeoutExpired:
            raise WiringError(f"{switch.name}: no answer from {switch.host}")
    if result.returncode != 0:
        raise _failure(switch, result)
    lines = [line.strip().strip('"') for line in result.stdout.splitlines()] + ["", ""]

    return lines[0], lines[1]


def collect_switch(switch, env, timeout, **kwargs):

    result = parse_switch(walk_switch(switch, env, timeout, **kwargs))

    return {**result, "name": switch.name, "host": switch.host, "weak_privacy": switch.priv == "des"}