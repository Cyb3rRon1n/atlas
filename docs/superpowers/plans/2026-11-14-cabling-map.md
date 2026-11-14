# Cabling Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A port-level wired topology page (/cabling) built from SNMP (any managed switch), the optional UniFi local API and an operator-kept `cabling.yaml`. It is refreshed on demand by `atlas wiring scan` or a Refresh button, and stored as snapshots with a "what changed" diff.

**Architecture:** A new `atlas/wiring/` package with one file per job:
- `snmp.py` walks a switch with net-snmp's `snmpbulkwalk` and parses the output.
- `unifi.py` fetches and parses the UniFi device and client lists.
- `cabling.py` loads the patch-panel file.
- `build.py` merges everything into one snapshot dict. It is a pure function.
- `store.py` keeps snapshots and diffs them.
- `scan.py` orchestrates the sources, with a per-source stale fallback and a lock.

The web side adds a server-rendered `/cabling` page. Its diagram is laid out in the browser by vendored ELK.js and drawn as SVG.

**Tech Stack:** Python 3.11+, SQLAlchemy 2 (SQLite), stdlib http.server/urllib, PyYAML (already a dependency), net-snmp CLI (`snmp` apt package in the image), elkjs 0.9.3 `lib/elk.bundled.js` (vendored, hash-pinned), pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-cabling-map-design.md`

## Global Constraints

- **Nothing site-specific is committed.** No real IPs, hostnames, MACs, port maps, credentials or `cabling.yaml` contents. Tests use 192.0.2.0/24, example names (`gateway`, `core-switch`, `nas`, `desktop-1`) and MACs from 02:00:00:… (locally administered) or documentation-style 00:00:5e:00:53:xx.
- **Secrets come only from env:** `ATLAS_SNMP_<NAME>_AUTH`, `ATLAS_SNMP_<NAME>_PRIV`, `ATLAS_UNIFI_USER`, `ATLAS_UNIFI_PASS`. `<NAME>` is the switch name upper-cased, with every non-alphanumeric character replaced by `_`. Secrets are never logged, never in a snapshot, and never on a command line: SNMP passphrases go through a 0600 temp `snmp.conf` (`SNMPCONFPATH`).
- **SNMP is v3 authPriv only.** `priv` is `aes` (default) or `des`. DES gets a "weak privacy" source note.
- **One dependency change:** the `snmp` apt package in the Dockerfile. No new Python dependencies. One new vendored JS file.
- **No data in `innerHTML`.** The page JS builds DOM/SVG nodes with `createElementNS` and `textContent`. JSON embedded in the page escapes `</` as `<\/`.
- **Match the repo's style:** read neighbouring code first, write docstrings that say *why*, no formatter.
- **Tests:** `python -m pytest tests/` stays green (`.venv`).
- **Commits:** no Co-Authored-By or any AI-attribution trailer.

## File map

| File | Responsibility |
|---|---|
| `atlas/config/models.py` | `WiringSwitch`, `WiringUnifi`, `WiringConfig`; `AtlasConfig.wiring` |
| `atlas/wiring/__init__.py` | `WiringError`, `env_key()`, `normalize_mac()`, `is_virtual_mac()` |
| `atlas/wiring/snmp.py` | `OIDS`, `parse_walk()`, `parse_switch()`, `walk_switch()`, `collect_switch()` |
| `atlas/wiring/unifi.py` | `fetch_unifi()`, `parse_unifi()` |
| `atlas/wiring/cabling.py` | `load_cabling()` |
| `atlas/wiring/build.py` | `build_wiring()` |
| `atlas/wiring/store.py` | `WiringStore`, `diff_snapshots()` |
| `atlas/wiring/scan.py` | `run_scan()`, `WiringBusy` |
| `atlas/database/models.py` | `WiringSnapshotRecord` |
| `atlas/cli/main.py` | `wiring_app` with `atlas wiring scan` |
| `atlas/web/cabling_page.py` | `render_cabling_page()`, `cabling_csv()` |
| `atlas/web/server.py`, `atlas/web/api.py`, `atlas/web/render.py` | route, refresh POST, nav entry, static allow-list |
| `atlas/web/static/elk.bundled.js` + `README.md` | vendored ELK |
| `Dockerfile`, `docker-compose.yml`, `cabling.example.yaml`, `atlas.yaml.example` | runtime |

---

### Task 1: Config, shared helpers

**Files:**
- Modify: `atlas/config/models.py` (append classes; add a field on `AtlasConfig`)
- Create: `atlas/wiring/__init__.py`
- Test: `tests/test_wiring_basics.py`

**Interfaces produced:**
- `WiringSwitch(name: str, host: str, snmp_user: str = "atlas", priv: Literal["aes","des"] = "aes")`
- `WiringUnifi(enabled: bool = False, url: str = "", site: str = "default", verify_ssl: bool = False)`
- `WiringConfig(enabled=False, timeout: int = 10, keep_snapshots: int = 30, switches: list[WiringSwitch] = [], unifi: WiringUnifi, cabling_file: str = "cabling.yaml")`
- `atlas.wiring.WiringError(Exception)`
- `env_key(name) -> str`: `"core-switch"` → `"CORE_SWITCH"`
- `normalize_mac(value) -> str | None`. It accepts `"aa:bb:cc:dd:ee:ff"`, `"AA-BB-…"`, `"AA BB CC DD EE FF"` (Hex-STRING) and `"aabb.ccdd.eeff"`, and returns lower-case colon form, or None.
- `is_virtual_mac(mac) -> bool`: True if the locally-administered bit is set, or the OUI is one of `bc:24:11` (Proxmox), `52:54:00` (QEMU), `02:42:..` (Docker, already locally administered) or `00:16:3e` (Xen).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_wiring_basics.py
import pytest
from pydantic import ValidationError

from atlas.config.models import AtlasConfig, WiringConfig
from atlas.wiring import env_key, is_virtual_mac, normalize_mac


def test_wiring_config_defaults_off():
    config = AtlasConfig()
    assert config.wiring.enabled is False
    assert config.wiring.switches == [] and config.wiring.unifi.enabled is False


def test_wiring_switch_priv_is_aes_or_des():
    WiringConfig(switches=[{"name": "core-switch", "host": "192.0.2.2", "priv": "des"}])
    with pytest.raises(ValidationError):
        WiringConfig(switches=[{"name": "core-switch", "host": "192.0.2.2", "priv": "none"}])


def test_env_key():
    assert env_key("core-switch") == "CORE_SWITCH"
    assert env_key("Rack 2.sw") == "RACK_2_SW"


@pytest.mark.parametrize("raw", ["02:00:00:AA:BB:01", "02-00-00-aa-bb-01", "02 00 00 AA BB 01",
                                 "0200.00aa.bb01", "Hex-STRING: 02 00 00 AA BB 01"])
def test_normalize_mac_forms(raw):
    assert normalize_mac(raw) == "02:00:00:aa:bb:01"


@pytest.mark.parametrize("raw", ["", None, "core-switch", "02:00:00:aa:bb", "zz:00:00:aa:bb:01"])
def test_normalize_mac_rejects(raw):
    assert normalize_mac(raw) is None


def test_is_virtual_mac():
    assert is_virtual_mac("bc:24:11:00:00:01") and is_virtual_mac("52:54:00:00:00:01")
    assert is_virtual_mac("02:00:00:00:00:01")          # locally administered
    assert not is_virtual_mac("00:00:5e:00:53:01")
```

- [ ] **Step 2: Run, confirm they fail:** `python -m pytest tests/test_wiring_basics.py -v` → ImportError.

- [ ] **Step 3: Implement**

```python
# atlas/config/models.py (append before AtlasConfig; add `from typing import Literal` at the top if missing)
class WiringSwitch(BaseModel):
    # SNMPv3 authPriv only; passphrases come from env ATLAS_SNMP_<NAME>_AUTH / _PRIV.
    name: str
    host: str
    snmp_user: str = "atlas"
    priv: Literal["aes", "des"] = "aes"   # des: older gear (e.g. Cisco Sx300) offers nothing else


class WiringUnifi(BaseModel):
    # Optional: a local read-only UniFi account, from env ATLAS_UNIFI_USER / ATLAS_UNIFI_PASS.
    enabled: bool = False
    url: str = ""
    site: str = "default"
    verify_ssl: bool = False   # UniFi consoles ship a self-signed cert


class WiringConfig(BaseModel):
    """Port-level wired map (atlas wiring scan -> web /cabling). Off unless enabled."""
    enabled: bool = False
    timeout: int = 10
    keep_snapshots: int = 30
    switches: list[WiringSwitch] = []
    unifi: WiringUnifi = WiringUnifi()
    cabling_file: str = "cabling.yaml"
```

On `AtlasConfig` add: `wiring: WiringConfig = WiringConfig()`.

```python
# atlas/wiring/__init__.py
"""
Port-level wired topology (atlas wiring scan -> web /cabling). Shared helpers
live here; each source has its own module so a vendor adapter (UniFi) stays
optional and the vendor-neutral path (SNMP standard MIBs) stands alone.
"""

import re


class WiringError(Exception):
    """A source failed in a way the operator can act on (message is safe to show: no secrets)."""


VIRTUAL_OUIS = ("bc:24:11", "52:54:00", "00:16:3e")


def env_key(name):

    return re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def normalize_mac(value):

    if not value:
        return None

    text = re.sub(r"^Hex-STRING:\s*", "", str(value).strip())
    digits = re.sub(r"[\s:.\-]", "", text)

    if not re.fullmatch(r"[0-9A-Fa-f]{12}", digits):
        return None

    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)).lower()


def is_virtual_mac(mac):

    return bool(int(mac[:2], 16) & 0x02) or mac[:8] in VIRTUAL_OUIS
```

- [ ] **Step 4: Run tests → PASS.** Also run `python -m pytest tests/test_config.py -q`.
- [ ] **Step 5: Commit** `git add atlas/config/models.py atlas/wiring/__init__.py tests/test_wiring_basics.py && git commit -m "feat(wiring): config models and MAC helpers"`

---

### Task 2: SNMP walk + parser

**Files:**
- Create: `atlas/wiring/snmp.py`
- Test: `tests/test_wiring_snmp.py`

**Interfaces:**
- Consumes: `WiringSwitch`, `WiringError`, `env_key`, `normalize_mac`
- Produces:
  - `OIDS: dict[str, str]` (keys: `sysName, lldpLocChassis, ifName, ifOper, ifHighSpeed, ifAlias, basePort, qFdb, dFdb, lldpRem`)
  - `parse_walk(text, base) -> dict[str, str]`: OID suffix after `base` → value with the type prefix and quotes stripped. Continuation lines (not starting with `.`) are appended to the previous value with a space.
  - `parse_switch(walks: dict[str, str]) -> dict`, which returns
    `{"sys_name": str, "chassis_mac": str|None, "ports": {ifName: {"index": int, "up": bool, "speed": int, "alias": str}}, "fdb": [{"port": ifName, "mac": str, "vlan": int|None}], "neighbors": [{"port": ifName, "chassis_mac": str|None, "chassis": str, "remote_port": str, "remote_port_mac": str|None, "remote_port_desc": str, "sys_name": str}]}`
    - Ports are only the ifIndexes that appear in `basePort`, i.e. physical bridge ports. That leaves out VLAN interfaces, loopback and similar.
  - `walk_switch(switch, env, timeout, run=subprocess.run, which=shutil.which) -> dict[str, str]`: raw walk text per OIDS key. `dFdb` is walked only when `qFdb` came back empty.
  - `collect_switch(switch, env, timeout, **kw) -> dict`, which is `parse_switch(walk_switch(...))` plus `name`, `host`, `weak_privacy: bool`.

- [ ] **Step 1: Write failing tests** (fixture text uses the real output format, with example data)

```python
# tests/test_wiring_snmp.py
import subprocess

import pytest

from atlas.config.models import WiringSwitch
from atlas.wiring import WiringError
from atlas.wiring.snmp import OIDS, collect_switch, parse_switch, parse_walk, walk_switch

WALKS = {
    "sysName": ".1.3.6.1.2.1.1.5.0 = STRING: core-switch\n",
    "lldpLocChassis": ".1.0.8802.1.1.2.1.3.2.0 = Hex-STRING: 02 00 00 00 00 10 \n",
    "ifName": ".1.3.6.1.2.1.31.1.1.1.1.49 = STRING: gi1\n.1.3.6.1.2.1.31.1.1.1.1.50 = STRING: gi2\n"
              ".1.3.6.1.2.1.31.1.1.1.1.51 = STRING: gi3\n.1.3.6.1.2.1.31.1.1.1.1.7000 = STRING: loopback1\n",
    "ifOper": ".1.3.6.1.2.1.2.2.1.8.49 = INTEGER: up(1)\n.1.3.6.1.2.1.2.2.1.8.50 = INTEGER: up(1)\n"
              ".1.3.6.1.2.1.2.2.1.8.51 = INTEGER: down(2)\n.1.3.6.1.2.1.2.2.1.8.7000 = INTEGER: up(1)\n",
    "ifHighSpeed": ".1.3.6.1.2.1.31.1.1.1.15.49 = Gauge32: 1000\n.1.3.6.1.2.1.31.1.1.1.15.50 = Gauge32: 1000\n"
                   ".1.3.6.1.2.1.31.1.1.1.15.51 = Gauge32: 0\n",
    "ifAlias": ".1.3.6.1.2.1.31.1.1.1.18.49 = STRING: uplink\n.1.3.6.1.2.1.31.1.1.1.18.50 = STRING: \n",
    "basePort": ".1.3.6.1.2.1.17.1.4.1.2.49 = INTEGER: 49\n.1.3.6.1.2.1.17.1.4.1.2.50 = INTEGER: 50\n"
                ".1.3.6.1.2.1.17.1.4.1.2.51 = INTEGER: 51\n",
    # vlan 1; MACs 02:00:00:00:00:01 on gi1 (the gateway side) and 00:00:5e:00:53:01 on gi2
    "qFdb": ".1.3.6.1.2.1.17.7.1.2.2.1.2.1.2.0.0.0.0.1 = INTEGER: 49\n"
            ".1.3.6.1.2.1.17.7.1.2.2.1.2.1.0.0.94.0.83.1 = INTEGER: 50\n",
    "dFdb": "",
    # neighbour on local port 49: chassis given as a MAC string, port id as Hex-STRING
    "lldpRem": ".1.0.8802.1.1.2.1.4.1.1.5.0.49.3 = STRING: 02:00:00:00:00:01\n"
               ".1.0.8802.1.1.2.1.4.1.1.7.0.49.3 = Hex-STRING: 02 00 00 00 00 02 \n"
               ".1.0.8802.1.1.2.1.4.1.1.8.0.49.3 = STRING: Port 1\n"
               ".1.0.8802.1.1.2.1.4.1.1.9.0.49.3 = STRING: gateway\n"
               ".1.0.8802.1.1.2.1.4.1.1.5.0.50.4 = Hex-STRING: 00 00 5E 00 53 01 \n"
               ".1.0.8802.1.1.2.1.4.1.1.7.0.50.4 = STRING: eth0\n"
               ".1.0.8802.1.1.2.1.4.1.1.9.0.50.4 = STRING: \n",
}


def test_parse_walk_strips_types_and_joins_continuations():
    text = ".1.2.3.1 = STRING: \"a b\"\n.1.2.3.2 = Hex-STRING: 01 02\n03 04\n.1.2.3.3 = No Such Object available\n"
    assert parse_walk(text, "1.2.3") == {"1": "a b", "2": "01 02 03 04"}


def test_parse_switch():
    result = parse_switch(WALKS)
    assert result["sys_name"] == "core-switch" and result["chassis_mac"] == "02:00:00:00:00:10"
    assert set(result["ports"]) == {"gi1", "gi2", "gi3"}            # loopback is not a bridge port
    assert result["ports"]["gi1"] == {"index": 49, "up": True, "speed": 1000, "alias": "uplink"}
    assert result["ports"]["gi3"]["up"] is False
    assert {"port": "gi2", "mac": "00:00:5e:00:53:01", "vlan": 1} in result["fdb"]
    gateway = next(n for n in result["neighbors"] if n["port"] == "gi1")
    assert gateway["chassis_mac"] == "02:00:00:00:00:01" and gateway["remote_port_mac"] == "02:00:00:00:00:02"
    assert gateway["remote_port_desc"] == "Port 1" and gateway["sys_name"] == "gateway"
    host = next(n for n in result["neighbors"] if n["port"] == "gi2")
    assert host["chassis_mac"] == "00:00:5e:00:53:01" and host["remote_port"] == "eth0"


def test_parse_switch_falls_back_to_dot1d_fdb():
    walks = dict(WALKS, qFdb="", dFdb=".1.3.6.1.2.1.17.4.3.1.2.0.0.94.0.83.1 = INTEGER: 50\n")
    assert parse_switch(walks)["fdb"] == [{"port": "gi2", "mac": "00:00:5e:00:53:01", "vlan": None}]


SWITCH = WiringSwitch(name="core-switch", host="192.0.2.2", priv="des")
ENV = {"ATLAS_SNMP_CORE_SWITCH_AUTH": "auth-secret-123", "ATLAS_SNMP_CORE_SWITCH_PRIV": "priv-secret-456"}


def test_walk_switch_keeps_secrets_off_the_command_line(tmp_path):
    seen = []

    def fake_run(args, **kwargs):
        conf = (kwargs["env"]["SNMPCONFPATH"] + "/snmp.conf")
        seen.append((args, open(conf).read()))
        key = next(k for k, oid in OIDS.items() if oid == args[-1])
        return subprocess.CompletedProcess(args, 0, WALKS.get(key, ""), "")

    walks = walk_switch(SWITCH, ENV, 5, run=fake_run, which=lambda _: "/usr/bin/snmpbulkwalk")
    assert walks["ifName"] == WALKS["ifName"]
    for args, conf in seen:
        assert "auth-secret-123" not in " ".join(args) and "priv-secret-456" not in " ".join(args)
        assert "defAuthPassphrase auth-secret-123" in conf and "defPrivType DES" in conf
    assert not any(k == "dFdb" for k in walks if walks[k])     # qFdb answered, so dFdb was skipped


def test_walk_switch_errors():
    with pytest.raises(WiringError, match="install net-snmp"):
        walk_switch(SWITCH, ENV, 5, which=lambda _: None)
    with pytest.raises(WiringError, match="ATLAS_SNMP_CORE_SWITCH_AUTH"):
        walk_switch(SWITCH, {}, 5, which=lambda _: "/x")

    def failing(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Timeout: No Response from 192.0.2.2\n")
    with pytest.raises(WiringError, match="Timeout"):
        walk_switch(SWITCH, ENV, 5, run=failing, which=lambda _: "/x")


def test_collect_switch_marks_des_weak():
    def fake_run(args, **kwargs):
        key = next(k for k, oid in OIDS.items() if oid == args[-1])
        return subprocess.CompletedProcess(args, 0, WALKS.get(key, ""), "")
    result = collect_switch(SWITCH, ENV, 5, run=fake_run, which=lambda _: "/x")
    assert result["name"] == "core-switch" and result["weak_privacy"] is True
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Implement**

```python
# atlas/wiring/snmp.py
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
```

- [ ] **Step 4: Run tests → PASS.**
- [ ] **Step 5: Commit** `feat(wiring): SNMP walk and parser (LLDP, bridge FDB, IF-MIB)`

---

### Task 3: UniFi adapter

**Files:**
- Create: `atlas/wiring/unifi.py`
- Test: `tests/test_wiring_unifi.py`

**Interfaces:**
- Produces:
  - `parse_unifi(devices: list[dict], clients: list[dict]) -> dict`, which returns
    `{"devices": [{"mac", "name", "model", "ip", "type", "role": "gateway"|"switch"|"ap", "port_macs": {mac: port_name}, "ports": {port_name: {"index", "up", "speed"}}, "uplink": {"type", "mac", "remote_port": int|None, "local_port": int|None}}], "clients": [{"mac", "name", "ip", "switch_mac", "switch_port": int}]}`
    - `clients` holds wired clients only.
    - The role is `switch` for `type == "usw"`; `ap` for `uap`, or for any device that has a `radio_table` and a wired uplink to another UniFi device; otherwise `gateway`.
    - Port names are `port_table[].name`, falling back to `"Port {idx}"`.
  - `fetch_unifi(config: WiringUnifi, env, timeout, opener_factory=None) -> dict`. It logs in with `POST {url}/api/auth/login`, then calls `GET {url}/proxy/network/api/s/{site}/stat/device` and `.../stat/sta`, and returns `parse_unifi(...)`. It raises `WiringError` on missing env, login refusal (401/403 → "UniFi login refused - check ATLAS_UNIFI_USER/PASS") and connection errors.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_wiring_unifi.py
import io
import json

import pytest

from atlas.config.models import WiringUnifi
from atlas.wiring import WiringError
from atlas.wiring.unifi import fetch_unifi, parse_unifi

DEVICES = [
    {"mac": "02:00:00:00:00:01", "name": "gateway", "model": "UCGF", "type": "udm", "ip": "192.0.2.1",
     "port_table": [{"port_idx": 1, "name": "Port 1", "up": True, "speed": 1000, "mac": "02:00:00:00:00:02"},
                    {"port_idx": 4, "name": "Port 4", "up": True, "speed": 2500},
                    {"port_idx": 5, "name": "Port 5", "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "00:00:5e:00:53:99", "port_idx": 5}},
    {"mac": "02:00:00:00:00:03", "name": "ap-express", "model": "UX7", "type": "udm", "ip": "192.0.2.3",
     "radio_table": [{"name": "wifi0"}],
     "port_table": [{"port_idx": 1, "up": True, "speed": 2500}, {"port_idx": 2, "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "02:00:00:00:00:01", "uplink_remote_port": 4, "port_idx": 2}},
    {"mac": "02:00:00:00:00:04", "name": "mesh-ap", "model": "U6M", "type": "uap",
     "last_uplink": {"type": "wireless", "uplink_mac": "02:00:00:00:00:03"}},
    {"mac": "02:00:00:00:00:05", "name": "flex", "model": "USWED35", "type": "usw",
     "port_table": [{"port_idx": 5, "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "02:00:00:00:00:03", "uplink_remote_port": 1, "port_idx": 5}},
]
CLIENTS = [
    {"mac": "00:00:5e:00:53:01", "is_wired": True, "hostname": "nas", "ip": "192.0.2.10",
     "sw_mac": "02:00:00:00:00:01", "sw_port": 1},
    {"mac": "00:00:5e:00:53:02", "is_wired": False, "hostname": "phone", "ap_mac": "02:00:00:00:00:03"},
]


def test_parse_unifi_roles_ports_uplinks():
    result = parse_unifi(DEVICES, CLIENTS)
    by_name = {d["name"]: d for d in result["devices"]}
    assert by_name["gateway"]["role"] == "gateway" and by_name["ap-express"]["role"] == "ap"
    assert by_name["mesh-ap"]["role"] == "ap" and by_name["flex"]["role"] == "switch"
    assert by_name["gateway"]["ports"]["Port 4"] == {"index": 4, "up": True, "speed": 2500}
    assert by_name["ap-express"]["ports"]["Port 2"]["speed"] == 2500        # name falls back to "Port N"
    assert by_name["gateway"]["port_macs"] == {"02:00:00:00:00:02": "Port 1"}
    assert by_name["flex"]["uplink"] == {"type": "wire", "mac": "02:00:00:00:00:03", "remote_port": 1, "local_port": 5}
    assert result["clients"] == [{"mac": "00:00:5e:00:53:01", "name": "nas", "ip": "192.0.2.10",
                                  "switch_mac": "02:00:00:00:00:01", "switch_port": 1}]


class FakeResponse(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode()); self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeOpener:
    def __init__(self, login_status=200):
        self.calls, self.login_status = [], login_status
    def open(self, request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else request
        self.calls.append((url, getattr(request, "data", None)))
        if url.endswith("/api/auth/login"):
            if self.login_status != 200:
                import urllib.error
                raise urllib.error.HTTPError(url, self.login_status, "nope", {}, None)
            return FakeResponse({})
        return FakeResponse({"data": DEVICES if url.endswith("stat/device") else CLIENTS})


def test_fetch_unifi():
    opener = FakeOpener()
    config = WiringUnifi(enabled=True, url="https://192.0.2.1")
    result = fetch_unifi(config, {"ATLAS_UNIFI_USER": "atlas", "ATLAS_UNIFI_PASS": "pw-123456"}, 5,
                         opener_factory=lambda: opener)
    assert len(result["devices"]) == 4
    assert opener.calls[1][0] == "https://192.0.2.1/proxy/network/api/s/default/stat/device"


def test_fetch_unifi_errors():
    config = WiringUnifi(enabled=True, url="https://192.0.2.1")
    with pytest.raises(WiringError, match="ATLAS_UNIFI_USER"):
        fetch_unifi(config, {}, 5, opener_factory=FakeOpener)
    with pytest.raises(WiringError, match="login refused"):
        fetch_unifi(config, {"ATLAS_UNIFI_USER": "a", "ATLAS_UNIFI_PASS": "b"}, 5,
                    opener_factory=lambda: FakeOpener(401))
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Implement**

```python
# atlas/wiring/unifi.py
"""
Optional UniFi adapter: a local read-only account on a UniFi OS console. Fills in
what SNMP can't see on UniFi gear (gateway/AP/Flex ports and their uplinks, and
which gateway port each wired client is learned on). Field names come from
community clients, not an official schema, and vary by firmware - every read
here uses .get() with a default so a renamed field degrades, never crashes.
"""

import http.cookiejar
import json
import ssl
import urllib.error
import urllib.request

from atlas.wiring import WiringError, normalize_mac


def _role(device, macs):

    if device.get("type") == "usw":
        return "switch"
    uplink = device.get("last_uplink") or {}
    if device.get("type") == "uap" or (device.get("radio_table") and normalize_mac(uplink.get("uplink_mac")) in macs):
        return "ap"
    return "gateway"


def parse_unifi(devices, clients):

    macs = {normalize_mac(d.get("mac")) for d in devices}
    parsed = []

    for device in devices:
        ports, port_macs = {}, {}
        for port in device.get("port_table") or []:
            index = port.get("port_idx")
            name = port.get("name") or f"Port {index}"
            ports[name] = {"index": index, "up": bool(port.get("up")), "speed": int(port.get("speed") or 0)}
            if normalize_mac(port.get("mac")):
                port_macs[normalize_mac(port.get("mac"))] = name
        uplink = device.get("last_uplink") or device.get("uplink") or {}
        parsed.append({
            "mac": normalize_mac(device.get("mac")), "name": device.get("name") or device.get("mac"),
            "model": device.get("model", ""), "ip": device.get("ip", ""), "type": device.get("type", ""),
            "role": _role(device, macs), "ports": ports, "port_macs": port_macs,
            "uplink": {"type": uplink.get("type"), "mac": normalize_mac(uplink.get("uplink_mac")),
                       "remote_port": uplink.get("uplink_remote_port"), "local_port": uplink.get("port_idx")}})

    wired = [{"mac": normalize_mac(c.get("mac")), "name": c.get("name") or c.get("hostname") or c.get("oui") or "",
              "ip": c.get("ip", ""), "switch_mac": normalize_mac(c.get("sw_mac")), "switch_port": c.get("sw_port")}
             for c in clients if c.get("is_wired") and normalize_mac(c.get("mac"))]

    return {"devices": parsed, "clients": wired}


def _default_opener(verify_ssl):

    context = ssl.create_default_context()
    if not verify_ssl:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                       urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def fetch_unifi(config, env, timeout, opener_factory=None):

    user, password = env.get("ATLAS_UNIFI_USER"), env.get("ATLAS_UNIFI_PASS")
    if not user or not password:
        raise WiringError("set ATLAS_UNIFI_USER and ATLAS_UNIFI_PASS in the atlas env file")

    opener = (opener_factory or (lambda: _default_opener(config.verify_ssl)))()
    base = config.url.rstrip("/")

    try:
        opener.open(urllib.request.Request(f"{base}/api/auth/login",
                                           json.dumps({"username": user, "password": password}).encode(),
                                           {"Content-Type": "application/json"}), timeout=timeout)

        def get(path):
            with opener.open(f"{base}/proxy/network/api/s/{config.site}/{path}", timeout=timeout) as response:
                return json.load(response).get("data") or []

        return parse_unifi(get("stat/device"), get("stat/sta"))

    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise WiringError("UniFi login refused - check ATLAS_UNIFI_USER/PASS (a local, read-only account)")
        raise WiringError(f"UniFi API error {error.code}")
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise WiringError(f"UniFi unreachable: {getattr(error, 'reason', error)}")
```

- [ ] **Step 4: Run tests → PASS.**
- [ ] **Step 5: Commit** `feat(wiring): optional UniFi local API adapter`

---

### Task 4: cabling.yaml loader

**Files:**
- Create: `atlas/wiring/cabling.py`, `cabling.example.yaml`
- Test: `tests/test_wiring_cabling.py`

**Interfaces:**
- `load_cabling(path) -> {"panels": [{"panel", "port": int, "switch", "switch_port", "label", "color"}], "ports": {"<switch>:<port>": {"label", "color"}}, "error": str|None}`
  - A missing file returns empty lists and `error=None`.
  - A YAML syntax error returns empty lists and `error="cabling.yaml line N: …"`.
  - A malformed entry is skipped, and an error string naming it is appended to `error` (joined with `"; "`).
  - Top-level `ports:` labels runs without a panel (e.g. `"gateway:Port 3": {label: "ISP Wi-Fi bridge"}`).

- [ ] **Step 1: Failing tests**

```python
# tests/test_wiring_cabling.py
from atlas.wiring.cabling import load_cabling


def test_missing_file_is_empty(tmp_path):
    assert load_cabling(tmp_path / "nope.yaml") == {"panels": [], "ports": {}, "error": None}


def test_loads_panels_and_port_labels(tmp_path):
    path = tmp_path / "cabling.yaml"
    path.write_text("""
panels:
  - name: PP1
    ports:
      1: {switch: core-switch, port: gi1, label: "Office A", color: blue}
      2: {switch: core-switch, port: gi2}
ports:
  "gateway:Port 3": {label: "Wi-Fi bridge"}
""")
    result = load_cabling(path)
    assert result["error"] is None
    assert result["panels"][0] == {"panel": "PP1", "port": 1, "switch": "core-switch", "switch_port": "gi1",
                                   "label": "Office A", "color": "blue"}
    assert result["panels"][1]["label"] == "" and result["panels"][1]["color"] == ""
    assert result["ports"] == {"gateway:Port 3": {"label": "Wi-Fi bridge", "color": ""}}


def test_bad_yaml_reports_line(tmp_path):
    path = tmp_path / "cabling.yaml"
    path.write_text("panels:\n  - name: PP1\n    ports: {1: [\n")
    result = load_cabling(path)
    assert result["panels"] == [] and result["error"].startswith("cabling.yaml line ")


def test_bad_entry_skipped_with_error(tmp_path):
    path = tmp_path / "cabling.yaml"
    path.write_text("panels:\n  - name: PP1\n    ports:\n      1: {port: gi1}\n      2: {switch: s, port: gi2}\n")
    result = load_cabling(path)
    assert [e["port"] for e in result["panels"]] == [2]
    assert "PP1 port 1" in result["error"]
```

- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement**

```python
# atlas/wiring/cabling.py
"""
The operator's patch-panel file. LLDP and MAC tables can't see a passive patch
panel or a wall jack, so this small YAML file is the only manual part of the
cabling map. Lives in the config dir (never the repo); a bad file never blanks
the page - discovery still renders and the error is shown.
"""

from pathlib import Path

import yaml


def load_cabling(path):

    empty = {"panels": [], "ports": {}, "error": None}
    path = Path(path)

    if not path.exists():
        return empty

    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark else "line ?"
        return {**empty, "error": f"cabling.yaml {where}: {getattr(error, 'problem', error)}"}

    errors, panels, ports = [], [], {}

    for panel in data.get("panels") or []:
        name = str((panel or {}).get("name") or "?")
        for number, entry in ((panel or {}).get("ports") or {}).items():
            entry = entry or {}
            if not isinstance(number, int) or not entry.get("switch") or not entry.get("port"):
                errors.append(f"{name} port {number}: needs a number, switch and port")
                continue
            panels.append({"panel": name, "port": number, "switch": str(entry["switch"]),
                           "switch_port": str(entry["port"]), "label": str(entry.get("label") or ""),
                           "color": str(entry.get("color") or "")})

    for key, entry in (data.get("ports") or {}).items():
        entry = entry or {}
        ports[str(key)] = {"label": str(entry.get("label") or ""), "color": str(entry.get("color") or "")}

    return {"panels": panels, "ports": ports, "error": "; ".join(errors) or None}
```

```yaml
# cabling.example.yaml - copy to cabling.yaml next to atlas.yaml and edit.
# Patch panels and wall jacks are invisible to LLDP/SNMP; describe them here once.
# switch = a switch name from atlas.yaml wiring.switches (or a UniFi device name),
# port = the port name as the switch reports it (e.g. gi1, Port 3).
panels:
  - name: PP1
    ports:
      1: {switch: core-switch, port: gi1, label: "Office - desk A", color: blue}
      2: {switch: core-switch, port: gi2, label: "Rack - nas"}
# Runs without a panel: label a switch port directly.
ports:
  "gateway:Port 3": {label: "ISP router (Wi-Fi only)", color: yellow}
```

- [ ] **Step 4: Run tests → PASS.**
- [ ] **Step 5: Commit** `feat(wiring): cabling.yaml patch-panel loader`

---

### Task 5: build_wiring (merge sources into a snapshot)

**Files:**
- Create: `atlas/wiring/build.py`
- Test: `tests/test_wiring_build.py`

**Interfaces:**
- Consumes: the outputs of `collect_switch` (Task 2), `parse_unifi` (Task 3) and `load_cabling` (Task 4), plus `InventoryStore.devices()` entries (`id`, `name`, `kind`, `sightings[].mac`).
- Produces: `build_wiring(switches: list[dict], unifi: dict|None, devices: list[dict], cabling: dict) -> dict`:

```
{"nodes": [{"id", "name", "kind": "wan"|"gateway"|"switch"|"ap"|"host"|"bridge"|"unknown",
            "ip", "mac", "device_id", "behind": [names], "ports": {port: {"up","speed"}}}],
 "links": [{"id", "a", "a_port", "b", "b_port", "speed", "up", "via": "lldp"|"unifi"|"fdb",
            "patch": "PP1-07"|None, "label": str, "color": str}],
 "panels": [{"panel","port","switch","switch_port","label","color","device","speed","up"}],
 "warnings": [str]}
```

Rules, in this order. The `a` end is always the upstream end, nearer the gateway.

1. **Nodes:**
   - Each UniFi device whose uplink isn't `wireless` becomes a node `u:<mac>`, kind = its role.
   - Each SNMP switch becomes `s:<name>`, kind `switch`.
   - If UniFi has a gateway with a wired uplink to an unknown MAC, add a `wan` node (`"Internet / ISP"`) and link it to the gateway's uplink port.
2. **UniFi uplinks:** a device's wired `uplink.mac` that is another UniFi node gives a link (uplink device, `Port {remote_port}`) → (device, `Port {local_port}`, falling back to the name from its `ports` with that index). Speed and up come from the device's local port.
3. **SNMP LLDP:** for each neighbour, find the node it is:
   - first, a UniFi `port_macs` hit, which also gives the remote port name;
   - else a UniFi device MAC;
   - else another SNMP switch's `chassis_mac`;
   - else a UniFi device whose name, with spaces turned into dashes, equals `sys_name` (case-insensitive). The remote port is then `remote_port_desc` or `remote_port`.

   If that node is infrastructure, it's a link (`via: lldp`) and the switch port counts as an *uplink port*. If it isn't, the neighbour is a host that speaks LLDP. Record its chassis MAC as the preferred MAC for that port.

   A UniFi wired client whose `ip` equals an SNMP switch's `host` gives that switch's UniFi-side port: the link from (that UniFi switch_mac node, `Port {switch_port}`) to the SNMP switch is used if LLDP didn't already make one.
4. **Uplink ports:** these are the LLDP infrastructure ports from rule 3, plus any SNMP port with more than 3 learned *non-virtual* MACs (hypervisor guests use virtual MACs).
5. **SNMP hosts:** for each non-uplink port that is up and has learned MACs:
   - The primary MAC is the LLDP chassis MAC (rule 3), else the first non-virtual MAC, else the first MAC.
   - The primary becomes a node `h:<mac>`. Its name comes from inventory (a device with a sighting of that MAC), else the UniFi client name, else the MAC. Kind `host`, or `unknown` when there is no name.
   - Every other MAC on the port is listed in `behind` by name.
   - Link (switch, port) → (host, "") with `via: fdb`, using the port's speed and state.
6. **UniFi wired clients not placed by SNMP**, grouped by (switch_mac, switch_port):
   - Skip the group if that port's link already leads to an infrastructure node (rule 2 or 3).
   - Skip a client whose MAC is any SNMP switch's MAC or whose IP is an SNMP switch's host.
   - A group of more than 3 clients becomes one `bridge` node `b:<switch>:<port>`, named `"<n> devices (unmanaged)"`, with every client in `behind`.
   - Otherwise each client becomes a host node (same naming as rule 5), linked from (switch node, `Port N`) with `via: unifi`.
7. **Labels:** `cabling["ports"]["<node name>:<port>"]` sets `label` and `color` on the link whose `a` side matches. A matching bridge node is renamed to that label.
8. **Panels:**
   - Each panel entry matches the link where (node name == `switch` and `a_port == switch_port`). The match sets `patch = f"{panel}-{port:02d}"` plus label and color.
   - Every entry is also listed in `panels`, with the attached device name, speed and up state. A matching link with nothing on it lists the device as `""`.
   - An entry naming a switch or port that doesn't exist gives a warning: `"PP1-03: core-switch has no port gi30"`.
9. **Warnings:**
   - When more than one link joins the same two nodes: `"2 links between gateway and core-switch (Port 1, Port 2) - spanning tree blocks all but one; remove one or bundle them (LACP)"`.
   - `cabling["error"]`, if set, is passed through.
10. **Link id:** `f"{a}|{a_port}|{b}|{b_port}"`. Nodes that no link touches are dropped, except the gateway.

- [ ] **Step 1: Failing tests.** Use the Task 3 `DEVICES` and `CLIENTS` copied into this test file, plus one switch:

```python
# tests/test_wiring_build.py
from atlas.wiring.build import build_wiring
from atlas.wiring.unifi import parse_unifi

DEVICES = [  # same shapes as tests/test_wiring_unifi.py
    {"mac": "02:00:00:00:00:01", "name": "gateway", "model": "UCGF", "type": "udm", "ip": "192.0.2.1",
     "port_table": [{"port_idx": 1, "name": "Port 1", "up": True, "speed": 1000, "mac": "02:00:00:00:00:02"},
                    {"port_idx": 2, "name": "Port 2", "up": True, "speed": 1000, "mac": "02:00:00:00:00:06"},
                    {"port_idx": 3, "name": "Port 3", "up": True, "speed": 2500},
                    {"port_idx": 4, "name": "Port 4", "up": True, "speed": 2500},
                    {"port_idx": 5, "name": "Port 5", "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "00:00:5e:00:53:99", "port_idx": 5}},
    {"mac": "02:00:00:00:00:03", "name": "ap-express", "model": "UX7", "type": "udm", "radio_table": [{}],
     "port_table": [{"port_idx": 1, "up": True, "speed": 2500}, {"port_idx": 2, "up": True, "speed": 2500}],
     "last_uplink": {"type": "wire", "uplink_mac": "02:00:00:00:00:01", "uplink_remote_port": 4, "port_idx": 2}},
    {"mac": "02:00:00:00:00:04", "name": "mesh-ap", "type": "uap",
     "last_uplink": {"type": "wireless", "uplink_mac": "02:00:00:00:00:03"}},
]
CLIENTS = [
    {"mac": "02:00:00:00:00:10", "is_wired": True, "hostname": "core-switch", "ip": "192.0.2.2",
     "sw_mac": "02:00:00:00:00:01", "sw_port": 2},
    {"mac": "00:00:5e:00:53:01", "is_wired": True, "hostname": "nas", "ip": "192.0.2.10",
     "sw_mac": "02:00:00:00:00:01", "sw_port": 1},                     # really behind core-switch gi5
] + [{"mac": f"00:00:5e:00:53:{40 + i:02x}", "is_wired": True, "hostname": f"tv-{i}",
      "sw_mac": "02:00:00:00:00:01", "sw_port": 3} for i in range(5)]    # unmanaged bridge on Port 3

SWITCH = {
    "name": "core-switch", "host": "192.0.2.2", "sys_name": "core-switch", "chassis_mac": "02:00:00:00:00:10",
    "weak_privacy": False,
    "ports": {"gi1": {"index": 49, "up": True, "speed": 1000, "alias": ""},
              "gi2": {"index": 50, "up": True, "speed": 1000, "alias": ""},
              "gi5": {"index": 53, "up": True, "speed": 1000, "alias": ""},
              "gi6": {"index": 54, "up": False, "speed": 0, "alias": ""}},
    "neighbors": [{"port": "gi1", "chassis_mac": "02:00:00:00:00:02", "chassis": "", "remote_port": "",
                   "remote_port_mac": "02:00:00:00:00:02", "remote_port_desc": "", "sys_name": "gateway"},
                  {"port": "gi2", "chassis_mac": "02:00:00:00:00:06", "chassis": "", "remote_port": "",
                   "remote_port_mac": "02:00:00:00:00:06", "remote_port_desc": "", "sys_name": "gateway"}],
    "fdb": [{"port": "gi1", "mac": f"00:00:5e:00:53:{40 + i:02x}", "vlan": 1} for i in range(5)]
           + [{"port": "gi5", "mac": "00:00:5e:00:53:01", "vlan": 1},
              {"port": "gi5", "mac": "bc:24:11:00:00:01", "vlan": 1}],
}
INVENTORY = [{"id": 7, "name": "nas", "kind": "server", "sightings": [{"mac": "00:00:5e:00:53:01"}]},
             {"id": 8, "name": "nas-guest", "kind": "other", "sightings": [{"mac": "bc:24:11:00:00:01"}]}]
CABLING = {"panels": [{"panel": "PP1", "port": 5, "switch": "core-switch", "switch_port": "gi5",
                       "label": "Rack - nas", "color": "blue"},
                      {"panel": "PP1", "port": 9, "switch": "core-switch", "switch_port": "gi30",
                       "label": "", "color": ""}],
           "ports": {"gateway:Port 3": {"label": "ISP Wi-Fi bridge", "color": "yellow"}}, "error": None}


def _build():
    return build_wiring([SWITCH], parse_unifi(DEVICES, CLIENTS), INVENTORY, CABLING)


def _link(snapshot, a_name, a_port):
    names = {n["id"]: n["name"] for n in snapshot["nodes"]}
    return [l for l in snapshot["links"] if names[l["a"]] == a_name and l["a_port"] == a_port]


def test_infrastructure_links():
    snap = _build()
    names = {n["id"]: n for n in snap["nodes"]}
    assert any(n["kind"] == "wan" for n in snap["nodes"])
    assert "mesh-ap" not in {n["name"] for n in snap["nodes"]}                 # wireless uplink: hidden
    express = _link(snap, "gateway", "Port 4")[0]
    assert names[express["b"]]["name"] == "ap-express" and express["b_port"] == "Port 2" and express["speed"] == 2500
    core = _link(snap, "gateway", "Port 1")[0]
    assert names[core["b"]]["name"] == "core-switch" and core["b_port"] == "gi1" and core["via"] == "lldp"


def test_hosts_from_fdb_with_guests_behind_and_patch():
    snap = _build()
    names = {n["id"]: n for n in snap["nodes"]}
    nas_link = _link(snap, "core-switch", "gi5")[0]
    nas = names[nas_link["b"]]
    assert nas["name"] == "nas" and nas["device_id"] == 7 and nas["behind"] == ["nas-guest"]
    assert nas_link["patch"] == "PP1-05" and nas_link["label"] == "Rack - nas" and nas_link["color"] == "blue"
    assert not _link(snap, "gateway", "Port 1")[0]["b"].startswith("h:")     # nas not placed on the gateway


def test_unmanaged_bridge_and_port_label():
    snap = _build()
    names = {n["id"]: n for n in snap["nodes"]}
    bridge_link = _link(snap, "gateway", "Port 3")[0]
    bridge = names[bridge_link["b"]]
    assert bridge["kind"] == "bridge" and bridge["name"] == "ISP Wi-Fi bridge" and len(bridge["behind"]) == 5
    assert bridge_link["color"] == "yellow"


def test_warnings_double_link_and_bad_panel():
    snap = _build()
    assert any("2 links between gateway and core-switch" in w for w in snap["warnings"])
    assert any("PP1-09: core-switch has no port gi30" in w for w in snap["warnings"])
    panel = next(p for p in snap["panels"] if p["port"] == 5)
    assert panel["device"] == "nas" and panel["speed"] == 1000 and panel["up"] is True


def test_snmp_only_no_unifi():
    snap = build_wiring([SWITCH], None, INVENTORY, {"panels": [], "ports": {}, "error": None})
    assert any(n["name"] == "nas" for n in snap["nodes"])
    assert all(n["kind"] != "wan" for n in snap["nodes"])
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Implement** `atlas/wiring/build.py`. Follow the rules above in order, as one module with small private helpers (`_name_for(mac)`, `_add_link(...)`). Make sure of these:
   - The UniFi gateway's `port_macs` lets rule 3 resolve `02:00:00:00:00:02` → (gateway, "Port 1").
   - FDB MACs on uplink ports (gi1 above) are never placed as hosts.
   - The unifi-placed `nas` (gateway Port 1) is skipped, because its MAC was placed by SNMP and because Port 1 leads to an infrastructure node.
   - The node `ports` dict only holds ports used by a link: `{port: {"up", "speed"}}`, taken from the switch/UniFi port data.
   - Pure: no I/O, no clock.
- [ ] **Step 4: Run tests → PASS** (iterate on the helpers until every rule's test passes).
- [ ] **Step 5: Commit** `feat(wiring): merge SNMP, UniFi and cabling into one wired snapshot`

---

### Task 6: Snapshot store + diff

**Files:**
- Modify: `atlas/database/models.py` (add `WiringSnapshotRecord`), `tests/conftest.py` (patch the `engine` in `atlas.wiring.store` inside `temp_db`)
- Create: `atlas/wiring/store.py`
- Test: `tests/test_wiring_store.py`

**Interfaces:**
- `WiringSnapshotRecord(id: int pk, taken_at: datetime index, data: str (JSON text), errors: str (JSON text))`, with `__tablename__ = "wiring_snapshots"`.
- `WiringStore(engine_=None)`:
  - `.save(snapshot: dict, raw: dict, sources: dict, taken_at: datetime, keep: int) -> int`. `raw` is the per-source input (for the stale fallback); it holds no secrets.
  - `.latest(n=2) -> list[dict]`, newest first. Each item is `{"taken_at", "snapshot", "raw", "sources"}`.
  - Pruning keeps the newest `keep` rows.
- `diff_snapshots(previous: dict|None, current: dict) -> list[dict]`. Each change is `{"type": "moved"|"added"|"removed"|"speed"|"down"|"up", "text": str}`. It returns `[]` when `previous` is None.
  - Host attachment is keyed by host node id and compared as (upstream node name, port).
  - `moved` text: `"nas moved: core-switch gi5 → core-switch gi7"`.
  - Speed changes and up/down are compared per link id.

The `data` column stores `{"snapshot": …, "raw": …}`; the `errors` column stores `sources`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_wiring_store.py
from datetime import datetime, timedelta

from atlas.wiring.store import WiringStore, diff_snapshots


def _snap(port="gi5", speed=1000, up=True):
    return {"nodes": [{"id": "s:core", "name": "core-switch", "kind": "switch"},
                      {"id": "h:1", "name": "nas", "kind": "host"}],
            "links": [{"id": f"s:core|{port}|h:1|", "a": "s:core", "a_port": port, "b": "h:1", "b_port": "",
                       "speed": speed, "up": up}], "panels": [], "warnings": []}


def test_save_latest_prune(temp_db):
    store = WiringStore()
    t0 = datetime(2026, 1, 1)
    for i in range(4):
        store.save(_snap(), {"switches": {}}, {"core-switch": {"ok": True}}, t0 + timedelta(minutes=i), keep=3)
    rows = store.latest(10)
    assert len(rows) == 3 and rows[0]["taken_at"] == t0 + timedelta(minutes=3)
    assert rows[0]["sources"] == {"core-switch": {"ok": True}} and rows[0]["raw"] == {"switches": {}}


def test_diff():
    assert diff_snapshots(None, _snap()) == []
    moved = diff_snapshots(_snap("gi5"), _snap("gi7"))
    assert {"type": "moved", "text": "nas moved: core-switch gi5 → core-switch gi7"} in moved
    assert diff_snapshots(_snap(speed=1000), _snap(speed=100))[0]["type"] == "speed"
    assert diff_snapshots(_snap(up=True), _snap(up=False))[0]["type"] == "down"
    gone = dict(_snap(), links=[])
    assert diff_snapshots(_snap(), gone)[0]["type"] == "removed"
    assert diff_snapshots(gone, _snap())[0]["type"] == "added"
```

- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement.** The model is a new class in `models.py`, modeled on `AccessHitRecord`. `create_all` picks it up, so no migration is needed. The store follows `PostureStore`'s pattern: an explicit engine, `initialize_database` in `__init__`, and `Session(self.engine)`. In `temp_db`, add `import atlas.wiring.store as wiring_store_module` and `monkeypatch.setattr(wiring_store_module, "engine", engine)`.

```python
# atlas/wiring/store.py (diff part)
def diff_snapshots(previous, current):

    if not previous:
        return []

    def attachments(snapshot):
        names = {n["id"]: n["name"] for n in snapshot["nodes"]}
        hosts = {n["id"] for n in snapshot["nodes"] if n["kind"] in ("host", "unknown", "bridge")}
        return ({l["b"]: (names.get(l["a"], l["a"]), l["a_port"], names.get(l["b"], l["b"]))
                 for l in snapshot["links"] if l["b"] in hosts},
                {l["id"]: l for l in snapshot["links"]})

    (old_at, old_links), (new_at, new_links) = attachments(previous), attachments(current)
    changes = []

    for host, (switch, port, name) in new_at.items():
        if host not in old_at:
            changes.append({"type": "added", "text": f"{name} appeared on {switch} {port}"})
        elif old_at[host][:2] != (switch, port):
            changes.append({"type": "moved", "text": f"{name} moved: {old_at[host][0]} {old_at[host][1]} → {switch} {port}"})
    for host, (switch, port, name) in old_at.items():
        if host not in new_at:
            changes.append({"type": "removed", "text": f"{name} gone from {switch} {port}"})

    for link_id, link in new_links.items():
        old = old_links.get(link_id)
        if old and old["speed"] != link["speed"]:
            changes.append({"type": "speed", "text": f"{link['a_port']}: {old['speed']}M → {link['speed']}M"})
        if old and old["up"] != link["up"]:
            changes.append({"type": "up" if link["up"] else "down", "text": f"{link['a_port']} went {'up' if link['up'] else 'down'}"})

    return changes
```

- [ ] **Step 4: Run tests → PASS;** also run `python -m pytest tests/test_database_migrate.py -q`.
- [ ] **Step 5: Commit** `feat(wiring): snapshot store and change diff`

---

### Task 7: Scan orchestration + CLI

**Files:**
- Create: `atlas/wiring/scan.py`
- Modify: `atlas/cli/main.py` (add `wiring_app`, modeled on `access_app`)
- Test: `tests/test_wiring_scan.py`

**Interfaces:**
- `WiringBusy(Exception)`.
- `run_scan(settings: AtlasConfig, store: WiringStore, devices: list[dict], env=os.environ, now=None, collect=collect_switch, fetch=fetch_unifi) -> dict`. It returns `{"taken_at", "snapshot", "sources": {name: {"ok", "error", "stale", "note"}}}`.
  - It takes a module-level `threading.Lock` non-blocking and raises `WiringBusy` if a scan is already running.
  - Each switch, and UniFi when enabled, is collected on its own. On `WiringError`, the previous snapshot's `raw` for that source is reused if present (`stale: True`) and the error is recorded.
  - `note` is `"weak privacy (DES)"` for DES switches.
  - It loads cabling from `settings.wiring.cabling_file`, calls `build_wiring`, then saves with `keep=settings.wiring.keep_snapshots`.
- CLI: `atlas wiring scan [--json]`.
  - It prints a line per source, plus a summary: `"<n> links, <m> warnings, <k> changes since last scan"`.
  - Exit code 1 if any source has an error, even when stale data was used.
  - If `wiring.enabled` is false: print a yellow notice and exit 0, the same as `access collect`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_wiring_scan.py
import threading

import pytest

from atlas.config.models import AtlasConfig
from atlas.wiring import WiringError
from atlas.wiring.scan import WiringBusy, run_scan, _LOCK
from atlas.wiring.store import WiringStore

SWITCH_RESULT = {"name": "core-switch", "host": "192.0.2.2", "sys_name": "core-switch",
                 "chassis_mac": "02:00:00:00:00:10", "weak_privacy": True,
                 "ports": {"gi5": {"index": 53, "up": True, "speed": 1000, "alias": ""}},
                 "neighbors": [], "fdb": [{"port": "gi5", "mac": "00:00:5e:00:53:01", "vlan": 1}]}


def _settings(tmp_path):
    return AtlasConfig(wiring={"enabled": True, "cabling_file": str(tmp_path / "cabling.yaml"),
                               "switches": [{"name": "core-switch", "host": "192.0.2.2", "priv": "des"}]})


def test_scan_saves_and_marks_des(temp_db, tmp_path):
    result = run_scan(_settings(tmp_path), WiringStore(), [], env={}, collect=lambda *a, **k: SWITCH_RESULT)
    assert result["sources"]["core-switch"] == {"ok": True, "error": "", "stale": False, "note": "weak privacy (DES)"}
    assert len(WiringStore().latest(5)) == 1


def test_failed_source_reuses_previous_raw(temp_db, tmp_path):
    settings = _settings(tmp_path)
    run_scan(settings, WiringStore(), [], env={}, collect=lambda *a, **k: SWITCH_RESULT)

    def broken(*a, **k):
        raise WiringError("core-switch: Timeout: No Response from 192.0.2.2")

    result = run_scan(settings, WiringStore(), [], env={}, collect=broken)
    source = result["sources"]["core-switch"]
    assert source["ok"] is False and source["stale"] is True and "Timeout" in source["error"]
    assert any(n["name"] == "00:00:5e:00:53:01" for n in result["snapshot"]["nodes"])


def test_busy(temp_db, tmp_path):
    assert _LOCK.acquire(blocking=False)
    try:
        with pytest.raises(WiringBusy):
            run_scan(_settings(tmp_path), WiringStore(), [], env={}, collect=lambda *a, **k: SWITCH_RESULT)
    finally:
        _LOCK.release()
```

Plus a CLI smoke test in the same file. It uses typer's `CliRunner` in `isolated_cwd`, with no atlas.yaml present, and checks that `atlas wiring scan` prints "wiring.enabled is false" and exits 0. Copy the pattern from `tests/test_cli_smoke.py`.

- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement** `scan.py` as specified, then the CLI command:

```python
wiring_app = typer.Typer(name="wiring", help="Port-level wired map: switches, patch panels, cables (web /cabling).")


@wiring_app.command("scan")
def wiring_scan(json_output: bool = typer.Option(False, "--json", help="Print the scan result as JSON")):
    """
    One read-only pass over the configured switches (SNMPv3) and, if enabled,
    the UniFi console; saves a snapshot for /cabling. On demand, like every
    atlas command - the web Refresh button runs the same thing.
    """

    from atlas.devices.store import InventoryStore
    from atlas.wiring.scan import WiringBusy, run_scan
    from atlas.wiring.store import WiringStore, diff_snapshots

    settings = load_config()
    if not settings.wiring.enabled:
        console.print("[yellow]wiring.enabled is false in atlas.yaml - nothing to do.[/yellow]")
        return

    store = WiringStore()
    previous = store.latest(1)
    try:
        result = run_scan(settings, store, InventoryStore().devices())
    except WiringBusy:
        console.print("[yellow]A wiring scan is already running.[/yellow]")
        raise typer.Exit(code=1)

    changes = diff_snapshots(previous[0]["snapshot"] if previous else None, result["snapshot"])
    failed = any(not source["ok"] for source in result["sources"].values())

    if json_output:
        print(json.dumps({**result, "changes": changes}, default=str))
    else:
        for name, source in result["sources"].items():
            mark = "[green]✓" if source["ok"] else ("[yellow]! stale" if source["stale"] else "[red]✗")
            console.print(f"{mark} {name}[/] {source['error'] or source['note']}")
        snapshot = result["snapshot"]
        console.print(f"{len(snapshot['links'])} links, {len(snapshot['warnings'])} warnings, "
                      f"{len(changes)} changes since last scan")

    if failed:
        raise typer.Exit(code=1)


app.add_typer(wiring_app)
```

- [ ] **Step 4: Run tests → PASS.**
- [ ] **Step 5: Commit** `feat(wiring): atlas wiring scan with per-source stale fallback`

---

### Task 8: /cabling page, refresh API, vendored ELK

**Files:**
- Create: `atlas/web/cabling_page.py`, `atlas/web/static/elk.bundled.js`
- Modify: `atlas/web/static/README.md`, `atlas/web/server.py` (route `/cabling`, `/cabling.csv`, `STATIC_FILES`), `atlas/web/api.py` (POST `/api/wiring/refresh`), `atlas/web/render.py` (NAV adds `("/cabling", "Cabling", "cabling")` after Network)
- Test: `tests/test_web_cabling.py`, `tests/test_web_server.py` (`PINNED` gains elk)

**Interfaces:**
- `render_cabling_page(latest: dict|None, changes: list[dict], enabled: bool) -> str`. `latest` is a `WiringStore.latest()` item.
- `cabling_csv(snapshot: dict) -> str`, with the header `panel,port,label,switch,switch_port,device,speed,up`. Each value is passed through `_csv_safe`, which prefixes `'` to any value starting with `= + - @` (formula injection). `csv` stdlib.
- API POST `/api/wiring/refresh` returns:
  - 400 `{"error": "wiring is not enabled in atlas.yaml"}` when wiring is disabled;
  - 409 `{"error": "a scan is already running"}` on `WiringBusy`;
  - otherwise 200 `{"ok": true, "taken_at": iso, "sources": {...}}`.

  It runs synchronously, which takes seconds. An event `atlas.wiring.scanned` is published with `{"links": n, "warnings": n, "sources": {name: ok}}`.

**Page layout** (server-rendered, `render_page("Cabling", body, active="cabling")`):
1. Header row: "Refreshed <relative time>" (UTC timestamp in a `<time>` element), the **Refresh map** button (`id="wiring-refresh"`), and source chips (`ok` green, `stale` orange, `error` red; note text in `title`). Warnings go in a `.warn` list.
2. `<section id="diagram">`: an empty `<svg id="wiring-svg">`, plus `<script type="application/json" id="wiring-data">` holding `{"nodes", "links"}`, with `</` escaped. A small legend gives the speed colours: 100M grey, 1G blue, 2.5G teal, 10G purple; a dashed line means down. Plus an **Export SVG** button.
3. `<section id="faceplates">`: one `<details>` per switch, gateway or AP node, each with a grid of all its known ports. A port is lit (speed colour) if up and dim if down. Its tooltip (`title`) says `"gi5 · 1G · nas · PP1-05 Rack - nas"`. Built server-side with `_esc`.
4. `<section id="patch">`: a table of `snapshot["panels"]`, a filter input (JS filters rows by `textContent`), and a **CSV** link to `/cabling.csv`.
5. `<section id="changes">`: the changes list, or "No changes since the previous scan."
6. If there is no snapshot: "No wiring scan yet - press Refresh map (or run `atlas wiring scan`)". If disabled: "Enable `wiring:` in atlas.yaml - see cabling.example.yaml".

**Diagram JS** (inline, built with createElementNS and no innerHTML). It runs `new ELK().layout(graph)` on this graph:
- `layoutOptions`: `{"elk.algorithm": "layered", "elk.direction": "DOWN", "elk.edgeRouting": "ORTHOGONAL", "elk.layered.spacing.nodeNodeBetweenLayers": "70", "elk.spacing.nodeNode": "30"}`.
- Each node is 150×46, with `layoutOptions: {"elk.portConstraints": "FIXED_ORDER"}`.
- Ports: for each link, the `a` end gets a port `a|a_port` on the SOUTH side and the `b` end gets `b|b_port` on the NORTH side, both 8×8, ordered by port index where known.
- Edges are `{id, sources: [a-port], targets: [b-port]}`.

After layout, it draws:
- a rect per node, with the name and a second line giving the kind and IP, plus `+N behind` when present;
- each port as a small square with its name in tiny text;
- each edge as a polyline through `sections[0]` (startPoint, bendPoints, endPoint), stroked in the speed colour, dashed when down;
- a midpoint label `"{a_port} ⇄ {b_port or '·'} · {speed}"`, with ` · PP1-05` appended when patched.

It sets the SVG viewBox to the layout size. A node click scrolls to its faceplate `<details>` and opens it. Export SVG serializes `#wiring-svg` with `XMLSerializer` to a Blob download named `cabling.svg`. Refresh POSTs `/api/wiring/refresh` with `fetch(..., {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"})`, disables the button with the text "Scanning…", and then calls `location.reload()`. On an error it shows the JSON error in `#msg`.

**Vendoring ELK:**
- `curl -fsSL https://cdn.jsdelivr.net/npm/elkjs@0.9.3/lib/elk.bundled.js -o atlas/web/static/elk.bundled.js`
- Record its `sha256sum` in `static/README.md` (EPL-2.0 licence) and in `tests/test_web_server.py::PINNED`.
- `STATIC_FILES = {"cytoscape.min.js", "elk.bundled.js"}`.

- [ ] **Step 1: Failing tests** in `tests/test_web_cabling.py`:
   - `render_cabling_page(None, [], False)` mentions `cabling.example.yaml`.
   - `render_cabling_page(None, [], True)` mentions "No wiring scan yet".
   - With a snapshot built by `build_wiring` from the Task 5 fixtures (import them from `tests.test_wiring_build`), the page contains `id="wiring-data"`, `PP1-05`, `Rack - nas`, the faceplate title text `gi5 · 1G · nas`, the warning text, and a `/static/elk.bundled.js` script tag. A node named `</script><b>x` renders as `<\/script>` inside the JSON and escaped in the HTML.
   - `cabling_csv` has the header row, and a label `=cmd()` becomes `'=cmd()`.
   - Server: GET `/cabling` returns 200 using `running_server`, with an empty DB and wiring disabled by default.
   - POST `/api/wiring/refresh` with a same-origin header and wiring disabled returns 400. Without an origin it returns 403 (the existing gate).
   - GET `/static/elk.bundled.js` returns 200.
- [ ] **Step 2: Run, confirm failure.**
- [ ] **Step 3: Implement** the page, the routes, the API and the vendored file, as specified above.
- [ ] **Step 4: Run** `python -m pytest tests/ -q` → all green.
- [ ] **Step 5: Commit** `feat(web): /cabling page - ELK port-level diagram, faceplates, patch table, changes, refresh`

---

### Task 9: Runtime packaging

**Files:**
- Modify: `Dockerfile` (apt: add `snmp`), `docker-compose.yml` (x-atlas: `env_file: [{path: .env, required: false}]` with a comment; mount `./cabling.yaml:/data/cabling.yaml:ro` is NOT added to the base file, because a missing source would become a directory), `atlas.yaml.example` (commented `wiring:` block from the spec), `.gitignore` (add `cabling.yaml`, `.env`).
- Test: `tests/test_compose.py` (existing compose tests must stay green; add an assertion that `env_file` with `required: false` is present on the anchor).

- [ ] **Step 1:** Add the compose assertion test, then run it and confirm it fails.
- [ ] **Step 2:** Make the edits.
- [ ] **Step 3:** Run `python -m pytest tests/ -q` → green. `docker build -t atlas:cabling .` succeeds, and `docker run --rm atlas:cabling snmpbulkwalk -V` prints a version.
- [ ] **Step 4: Commit** `build: net-snmp in the image, optional .env for wiring secrets`

---

### Task 10: Real verification on the operator's network (no repo changes)

This task runs on the deployment host and commits nothing. The operator's config stays local.

- [ ] **Step 1:** Build the branch image on the host (`docker build -t atlas:cabling .` in a checkout outside the compose dir). Run it once against the real config:
   `docker run --rm --network host --env-file ~/atlas/.env -v ~/atlas/atlas.yaml:/data/atlas.yaml:ro -v ~/atlas/data/inventory:/data/inventory --user 1000:1000 atlas:cabling atlas wiring scan`
   Expected: each source ✓, and links and warnings that match the spike (two gateway↔switch links warned about, the servers on their switch ports).
   - Add the `wiring:` block to the host's `atlas.yaml` first (switch name/host/priv des, unifi url).
   - Create an empty `cabling.yaml` from the example, with the operator's real ports filled in later by the operator.
- [ ] **Step 2:** Compare the result with the spike output. Fix any parsing mismatches with a test using rewritten example data, never the real dump.
- [ ] **Step 3:** After merge, CI builds the GHCR image. Then:
   - **Host override (local file):** add `./cabling.yaml:/data/cabling.yaml:ro` to both services.
   - **Recreate:** `docker compose pull && docker compose up -d --no-deps atlas atlas-scan`.
   - **Check:** open /cabling and press Refresh.
