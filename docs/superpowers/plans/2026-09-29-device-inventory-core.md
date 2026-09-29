# Device Inventory Core + LAN Scanner Implementation Plan (PR 1 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give atlas a persistent device inventory fed by a whole-LAN scan and Proxmox. It links sightings of the same device, tracks seen/quiet status, and sends Signal alerts for new and offline devices. It is exposed as `atlas scan` and `atlas devices`, run by a new `atlas-scan` container.

**Architecture:**
- A new `atlas/devices/` package:
  - Pure functions: LAN parsing (`lan.py`), linking (`linking.py`), status (`status.py`), and message formatting (`notify.py`).
  - One stateful `InventoryStore` (`store.py`) over four new SQLAlchemy tables in the existing `inventory/atlas.db`.
- The LAN scan pokes every address with a TCP connect so the kernel resolves each live device's MAC. It then reads `/proc/net/arp`. That needs only host networking: no ping, no NET_RAW, no new dependency.

**Tech Stack:**
- Python 3.11+, SQLAlchemy 2.0, typer, stdlib `socket`/`ipaddress`/`urllib`, pytest.
- The Signal side is signal-cli-rest-api's `POST /v2/send`.

**Spec:** `docs/superpowers/specs/2026-09-29-network-inventory-design.md`. This plan covers delivery step 1. Web tabs, map v2, chat and vulcan are later plans.

## Global Constraints

- No new runtime dependency: stdlib + what `pyproject.toml` already has.
- Timestamps are naive UTC via `datetime.utcnow()`, matching the existing models.
- Every public function returns plain dicts or tuples and never raises for expected failures (no network, no Signal). This follows the existing "pure result dict" convention.
- JSON columns are stored as `str` (`json.dumps`), matching `EventRecord.payload`.
- Nothing is ever merged automatically on a name match. Name matches only set `suggested_merge_id`.
- Fields listed in a device's `locked_fields` are never overwritten by automation.
- The first successful run of a source is a **baseline**: it creates devices but queues no "new" alerts.
- "New device" alerts roll up: if a `new` message was sent in the last 24h, further `new` items wait. "Offline" alerts send on the next run.
- Tests assert shape and logic, never the CI machine's state (no real `/proc`, no real network).
- Commits carry no AI-attribution trailers. Code style: the repo's heavy vertical spacing and docstrings that explain *why*.
- Run tests with `.venv/bin/python -m pytest tests/ -q` from the repo root.

## File Structure

| File | Responsibility |
|---|---|
| `atlas/database/engine.py` (modify) | `enable_wal(engine)`: WAL + busy_timeout so `atlas` and `atlas-scan` can both write |
| `atlas/database/models.py` (modify) | `DeviceRecord`, `SightingRecord`, `SourceRunRecord`, `NotificationRecord` |
| `atlas/config/models.py` (modify) | `ScanConfig`, `SignalNotifyConfig`, `NotifyConfig` on `AtlasConfig` |
| `atlas/devices/__init__.py` (create) | `Sighting` dataclass, the shared input type |
| `atlas/devices/lan.py` (create) | `/proc/net/route` + `/proc/net/arp` parsing, sweep, `scan()` |
| `atlas/devices/linking.py` (create) | `match(new, known)`: link / suggest / new |
| `atlas/devices/status.py` (create) | `device_status(sightings, ok_runs)` |
| `atlas/devices/store.py` (create) | `InventoryStore`: import hosts, record runs, list devices, the notification queue |
| `atlas/devices/notify.py` (create) | `format_message`, `send_signal`, `deliver` |
| `atlas/cli/main.py` (modify) | `atlas scan`, `atlas devices`, and `atlas map` records Proxmox sightings |
| `tests/conftest.py` (modify) | `temp_db` also patches `atlas.devices.store.engine` |
| `tests/test_devices_*.py` (create) | one test file per module |
| `docker-compose.yml` (modify) | `atlas-scan` replaces the `atlas-refresh` profile |
| `docs/configuration.md`, `docs/cli-reference.md`, `README.md`, spec (modify) | docs |

---

### Task 1: Tables, WAL, config

**Files:**
- Modify: `atlas/database/engine.py`, `atlas/database/models.py`, `atlas/config/models.py`, `tests/conftest.py`
- Create: `atlas/devices/__init__.py`, `atlas/devices/store.py` (a stub holding only the engine import, so conftest can patch it)
- Test: `tests/test_devices_models.py`

**Interfaces:**
- Produces:
  - `enable_wal(engine) -> None`.
  - Models `DeviceRecord`, `SightingRecord`, `SourceRunRecord`, `NotificationRecord`, with columns exactly as below.
  - `AtlasConfig.scan: ScanConfig(enabled=True, subnets=[], timeout=0.5, interval_minutes=15)`.
  - `AtlasConfig.notify.signal: SignalNotifyConfig(url="", number="", recipients=[])`.
  - `Sighting(source, external_id, ip=None, mac=None, hostname=None, detail={})`.

- [ ] **Step 1: Write the failing test** in `tests/test_devices_models.py`

```python
from sqlalchemy import create_engine, inspect, text

from atlas.config.models import AtlasConfig
from atlas.database.engine import enable_wal
from atlas.database.models import Base
from atlas.devices import Sighting


def test_new_tables_exist(temp_db):

    tables = set(inspect(temp_db).get_table_names())

    assert {"devices", "sightings", "source_runs", "notifications"} <= tables


def test_enable_wal_sets_journal_mode_and_busy_timeout(tmp_path):

    engine = create_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    enable_wal(engine)
    Base.metadata.create_all(engine)

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_scan_and_notify_config_defaults():

    config = AtlasConfig()

    assert config.scan.enabled is True
    assert config.scan.subnets == []
    assert config.scan.interval_minutes == 15
    assert config.notify.signal.url == ""


def test_sighting_defaults_are_independent():

    first, second = Sighting("lan", "aa"), Sighting("lan", "bb")
    first.detail["x"] = 1

    assert second.detail == {}
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_devices_models.py -q`
Expected: FAIL (ImportError: `enable_wal` / `atlas.devices`).

- [ ] **Step 3: Implement**

Append to `atlas/database/engine.py`:

```python
from sqlalchemy import event


def enable_wal(target_engine):
    """
    WAL + a 5s busy timeout on every new connection: the atlas web container
    and the atlas-scan container write the same SQLite file, and the default
    rollback journal would make one of them fail with "database is locked".
    """

    @event.listens_for(target_engine, "connect")
    def _pragmas(dbapi_connection, _record):

        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


enable_wal(engine)
```

Append to `atlas/database/models.py`. Also add `from sqlalchemy import ForeignKey, UniqueConstraint` at the top:

```python
class DeviceRecord(Base):
    """One real device as the operator knows it; sightings point at it."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str]

    kind: Mapped[str] = mapped_column(default="other")

    tags: Mapped[str] = mapped_column(default="[]")

    notes: Mapped[str] = mapped_column(default="")

    important: Mapped[bool] = mapped_column(default=False)

    # new / known / ignored
    state: Mapped[str] = mapped_column(default="new")

    # Fields the operator set by hand - automation never overwrites these.
    locked_fields: Mapped[str] = mapped_column(default="[]")

    # A name match is only ever a suggestion, never an automatic merge.
    suggested_merge_id: Mapped[int | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class SightingRecord(Base):
    """What one source saw, keyed by that source's own id (MAC, pve:<vmid>, address)."""

    __tablename__ = "sightings"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[str]

    external_id: Mapped[str]

    ip: Mapped[str | None] = mapped_column(default=None)

    mac: Mapped[str | None] = mapped_column(default=None)

    hostname: Mapped[str | None] = mapped_column(default=None)

    detail: Mapped[str] = mapped_column(default="{}")

    first_seen: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    last_seen: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), default=None)


class SourceRunRecord(Base):
    """One run of one source - a failed run never makes a device look quiet."""

    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[str]

    started_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    ok: Mapped[bool] = mapped_column(default=True)

    error: Mapped[str] = mapped_column(default="")

    seen_count: Mapped[int] = mapped_column(default=0)


class NotificationRecord(Base):
    """Queued alert (kind new/offline); sent_at stays null until delivered."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))

    kind: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    sent_at: Mapped[datetime | None] = mapped_column(default=None)
```

In `atlas/config/models.py`, add these before `AtlasConfig`, then add `scan: ScanConfig = ScanConfig()` and `notify: NotifyConfig = NotifyConfig()` to `AtlasConfig`:

```python
class ScanConfig(BaseModel):
    # Whole-LAN device discovery (atlas scan). Empty subnets = the default-route interface's network.
    enabled: bool = True
    subnets: list[str] = []
    timeout: float = 0.5
    interval_minutes: int = 15


class SignalNotifyConfig(BaseModel):
    # signal-cli-rest-api, e.g. http://signal-cli:8080. Empty url = no alerts.
    url: str = ""
    number: str = ""
    recipients: list[str] = []


class NotifyConfig(BaseModel):
    signal: SignalNotifyConfig = SignalNotifyConfig()
```

Create `atlas/devices/__init__.py`:

```python
from dataclasses import dataclass, field


@dataclass
class Sighting:
    """
    One observation from one source, before it's stored: source is lan /
    proxmox / manual, external_id is that source's own stable key (a MAC,
    pve:<vmid>, a configured address).
    """

    source: str
    external_id: str
    ip: str | None = None
    mac: str | None = None
    hostname: str | None = None
    detail: dict = field(default_factory=dict)
```

Create `atlas/devices/store.py`, filled in by Task 4:

```python
from atlas.database.engine import engine
```

In `tests/conftest.py`, add `import atlas.devices.store as devices_store_module` beside the other imports, and add this line inside `temp_db` after the other two patches:

```python
    monkeypatch.setattr(devices_store_module, "engine", engine)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_devices_models.py tests/ -q`
Expected: all pass. No existing test broke.

- [ ] **Step 5: Commit**

```bash
git add atlas/database atlas/config/models.py atlas/devices tests/conftest.py tests/test_devices_models.py
git commit -m "feat(devices): inventory tables, WAL for shared writers, scan/notify config"
```

---

### Task 2: LAN discovery (`atlas/devices/lan.py`)

**Files:**
- Create: `atlas/devices/lan.py`
- Test: `tests/test_devices_lan.py`

**Interfaces:**
- Consumes: `Sighting` (Task 1).
- Produces:
  - `parse_route(text) -> list[str]` (CIDRs).
  - `default_interface(text) -> str | None`.
  - `parse_arp(text) -> dict[str, str]` (ip to lowercase mac).
  - `sweep(subnets, timeout) -> None` (raises `ValueError` over 1024 addresses).
  - `scan(subnets=None, timeout=0.5) -> tuple[list[str], list[Sighting]]`. It raises `RuntimeError` when there's no subnet. The CLI records any exception as a failed run.

- [ ] **Step 1: Write the failing test** in `tests/test_devices_lan.py`

```python
import pytest

import atlas.devices.lan as lan
from atlas.devices import Sighting


ROUTE = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eno1\t00000000\t010AA8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0
eno1\t000AA8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0
docker0\t000011AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0
"""

ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.10.1     0x1         0x2         aa:bb:cc:00:00:01     *        eno1
192.168.10.57    0x1         0x2         AA:BB:CC:00:00:57     *        eno1
192.168.10.99    0x1         0x0         00:00:00:00:00:00     *        eno1
172.17.0.2       0x1         0x2         02:42:ac:11:00:02     *        docker0
"""


def test_parse_route_returns_default_interface_networks_only():

    assert lan.default_interface(ROUTE) == "eno1"
    assert lan.parse_route(ROUTE) == ["192.168.10.0/24"]


def test_parse_route_without_default_route():

    assert lan.parse_route(ROUTE.splitlines()[0] + "\n") == []


def test_parse_arp_keeps_complete_entries_lowercased():

    assert lan.parse_arp(ARP) == {
        "192.168.10.1": "aa:bb:cc:00:00:01",
        "192.168.10.57": "aa:bb:cc:00:00:57",
        "172.17.0.2": "02:42:ac:11:00:02",
    }


def test_sweep_refuses_huge_ranges():

    with pytest.raises(ValueError):
        lan.sweep(["10.0.0.0/16"], timeout=0.01)


def test_scan_filters_to_subnet_and_adds_self(monkeypatch):

    files = {"/proc/net/route": ROUTE, "/proc/net/arp": ARP}
    monkeypatch.setattr(lan, "_read", lambda path: files[path])
    monkeypatch.setattr(lan, "sweep", lambda subnets, timeout: None)
    monkeypatch.setattr(lan, "_reverse_dns", lambda ip: "router.lan" if ip.endswith(".1") else None)
    monkeypatch.setattr(lan, "local_sighting", lambda iface: Sighting(
        "lan", "aa:bb:cc:00:01:57", ip="192.168.10.157", mac="aa:bb:cc:00:01:57", hostname="cyberpac", detail={"self": True}))

    subnets, sightings = lan.scan()

    assert subnets == ["192.168.10.0/24"]
    by_ip = {s.ip: s for s in sightings}
    assert set(by_ip) == {"192.168.10.1", "192.168.10.57", "192.168.10.157"}
    assert by_ip["192.168.10.1"].hostname == "router.lan"
    assert by_ip["192.168.10.57"].external_id == "aa:bb:cc:00:00:57"
    assert all(s.source == "lan" for s in sightings)


def test_scan_with_no_subnet_raises(monkeypatch):

    monkeypatch.setattr(lan, "_read", lambda path: "Iface\n")

    with pytest.raises(RuntimeError):
        lan.scan()
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_devices_lan.py -q`
Expected: FAIL (ModuleNotFoundError `atlas.devices.lan`).

- [ ] **Step 3: Implement** `atlas/devices/lan.py`

```python
"""
Whole-LAN discovery without ping or raw sockets: a TCP connect to every
address makes the kernel ARP-resolve it, so every live device's MAC lands
in /proc/net/arp whether or not the port is open. Needs only host
networking (network_mode: host), no NET_RAW, no new dependency.
"""

import ipaddress
import socket
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from atlas.devices import Sighting


MAX_HOSTS = 1024

POKE_PORT = 9


def _read(path):

    return Path(path).read_text()


def _hex_ip(value):

    # /proc/net/route stores addresses as little-endian hex.
    return socket.inet_ntoa(struct.pack("<L", int(value, 16)))


def _route_rows(text):

    return [line.split() for line in text.splitlines()[1:] if len(line.split()) >= 8]


def default_interface(text):

    return next((row[0] for row in _route_rows(text) if row[1] == "00000000"), None)


def parse_route(text):
    """Networks directly attached to the default-route interface - the LAN."""

    interface = default_interface(text)

    if interface is None:
        return []

    return sorted({
        str(ipaddress.IPv4Network(f"{_hex_ip(row[1])}/{_hex_ip(row[7])}"))
        for row in _route_rows(text)
        if row[0] == interface and row[1] != "00000000"
    })


def parse_arp(text):
    """Complete neighbour entries only (flag 0x2); incomplete means nobody answered."""

    table = {}

    for line in text.splitlines()[1:]:

        parts = line.split()

        if len(parts) >= 6 and int(parts[2], 16) & 0x2 and parts[3] != "00:00:00:00:00:00":
            table[parts[0]] = parts[3].lower()

    return table


def _poke(ip, timeout):

    try:
        with socket.socket() as sock:
            sock.settimeout(timeout)
            sock.connect_ex((ip, POKE_PORT))

    except OSError:
        pass


def sweep(subnets, timeout=0.5):

    hosts = [str(host) for subnet in subnets for host in ipaddress.IPv4Network(subnet, strict=False).hosts()]

    if len(hosts) > MAX_HOSTS:
        raise ValueError(f"{len(hosts)} addresses - atlas scans at most {MAX_HOSTS}; narrow scan.subnets")

    with ThreadPoolExecutor(max_workers=64) as pool:
        list(pool.map(lambda ip: _poke(ip, timeout), hosts))


def _reverse_dns(ip):

    try:
        return socket.gethostbyaddr(ip)[0]

    except OSError:
        return None


def local_sighting(interface):
    """This host never appears in its own ARP table - add it explicitly."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", POKE_PORT))  # no packet is sent for UDP connect
            ip = sock.getsockname()[0]

        mac = _read(f"/sys/class/net/{interface}/address").strip().lower()

    except OSError:
        return None

    return Sighting("lan", mac, ip=ip, mac=mac, hostname=socket.gethostname(), detail={"self": True})


def scan(subnets=None, timeout=0.5):

    route = _read("/proc/net/route")
    subnets = list(subnets or parse_route(route))

    if not subnets:
        raise RuntimeError("no subnet to scan - set scan.subnets in atlas.yaml")

    sweep(subnets, timeout)

    networks = [ipaddress.IPv4Network(subnet, strict=False) for subnet in subnets]
    arp = {
        ip: mac for ip, mac in parse_arp(_read("/proc/net/arp")).items()
        if any(ipaddress.IPv4Address(ip) in network for network in networks)
    }

    with ThreadPoolExecutor(max_workers=16) as pool:
        names = dict(zip(arp, pool.map(_reverse_dns, arp)))

    sightings = [Sighting("lan", mac, ip=ip, mac=mac, hostname=names[ip]) for ip, mac in arp.items()]

    interface = default_interface(route)
    me = local_sighting(interface) if interface else None

    if me and me.mac not in {sighting.mac for sighting in sightings}:
        sightings.append(me)

    return subnets, sightings
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_devices_lan.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/devices/lan.py tests/test_devices_lan.py
git commit -m "feat(devices): LAN discovery via TCP-poke + /proc/net/arp (no ping, no NET_RAW)"
```

---

### Task 3: Linking and status rules (pure)

**Files:**
- Create: `atlas/devices/linking.py`, `atlas/devices/status.py`
- Test: `tests/test_devices_rules.py`

**Interfaces:**
- Consumes: `Sighting`.
- Produces:
  - `match(new: Sighting, known: list[dict]) -> tuple[str, int | None]`. The verdict is `"link"`, `"suggest"` or `"new"`. Each known dict has keys `device_id, device_name, source, ip, mac, hostname`.
  - `device_status(sightings: list[dict], ok_runs: dict[str, list[datetime]]) -> str`, one of `"seen"`, `"quiet"` or `"invisible"`. Sighting dicts have `source` and `last_seen`. `ok_runs` holds successful run start times, newest first.

- [ ] **Step 1: Write the failing test** in `tests/test_devices_rules.py`

```python
from datetime import datetime, timedelta

from atlas.devices import Sighting
from atlas.devices.linking import match
from atlas.devices.status import device_status


def known(device_id, name, source, ip=None, mac=None, hostname=None):

    return {"device_id": device_id, "device_name": name, "source": source, "ip": ip, "mac": mac, "hostname": hostname}


def test_same_mac_from_another_source_links():

    assert match(Sighting("proxmox", "pve:200", mac="aa:01"), [known(1, "x", "lan", mac="aa:01")]) == ("link", 1)


def test_lan_ip_matching_a_configured_host_links():

    assert match(Sighting("lan", "aa:57", ip="192.168.10.57"),
                 [known(3, "mediabox", "manual", ip="192.168.10.57")]) == ("link", 3)


def test_proxmox_ip_matching_lan_links():

    assert match(Sighting("proxmox", "pve:110", ip="192.168.10.134"),
                 [known(4, "media-tools", "lan", ip="192.168.10.134")]) == ("link", 4)


def test_two_lan_sightings_on_one_ip_do_not_link():

    # DHCP reuse: a different MAC on a known lan IP is a different device.
    assert match(Sighting("lan", "aa:02", ip="192.168.10.50"),
                 [known(5, "old", "lan", ip="192.168.10.50", mac="aa:01")]) == ("new", None)


def test_name_match_is_only_a_suggestion():

    assert match(Sighting("proxmox", "pve:200", hostname="mediabox"),
                 [known(3, "mediabox", "manual", ip="192.168.10.57")]) == ("suggest", 3)


def test_hostname_domain_is_ignored_for_suggestions():

    assert match(Sighting("lan", "aa:09", hostname="MediaBox.lan"),
                 [known(3, "x", "proxmox", hostname="mediabox")]) == ("suggest", 3)


def test_unknown_is_new():

    assert match(Sighting("lan", "aa:77", ip="192.168.10.77"), []) == ("new", None)


NOW = datetime(2026, 9, 29, 12, 0)
RUNS = {"lan": [NOW, NOW - timedelta(minutes=15), NOW - timedelta(minutes=30)]}


def test_seen_in_latest_run():

    assert device_status([{"source": "lan", "last_seen": NOW}], RUNS) == "seen"


def test_missing_only_latest_run_is_still_seen():

    assert device_status([{"source": "lan", "last_seen": NOW - timedelta(minutes=15)}], RUNS) == "seen"


def test_missing_last_two_runs_is_quiet():

    assert device_status([{"source": "lan", "last_seen": NOW - timedelta(minutes=30)}], RUNS) == "quiet"


def test_seen_by_any_source_wins():

    sightings = [{"source": "lan", "last_seen": NOW - timedelta(hours=5)},
                 {"source": "proxmox", "last_seen": NOW}]

    assert device_status(sightings, {**RUNS, "proxmox": [NOW]}) == "seen"


def test_source_without_two_runs_cannot_call_quiet():

    assert device_status([{"source": "lan", "last_seen": NOW - timedelta(hours=5)}], {"lan": [NOW]}) == "seen"


def test_manual_only_is_invisible():

    assert device_status([{"source": "manual", "last_seen": NOW}], RUNS) == "invisible"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_devices_rules.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

`atlas/devices/linking.py`:

```python
"""
Which device a newly seen sighting belongs to. Links only on evidence that
can't be a coincidence (same MAC; a configured host's address; a Proxmox
guest's IP matching a LAN sighting). A name match is only a suggestion -
a wrong automatic merge is worse than a visible duplicate.
"""


def short_name(name):

    return (name or "").split(".")[0].strip().lower()


def match(new, known):

    if new.mac:
        for entry in known:
            if entry["mac"] == new.mac and entry["source"] != new.source:
                return "link", entry["device_id"]

    if new.ip:
        for entry in known:
            if entry["ip"] == new.ip and (entry["source"] == "manual" or {entry["source"], new.source} == {"lan", "proxmox"}):
                return "link", entry["device_id"]

    name = short_name(new.hostname)

    if name:
        for entry in known:
            if name in (short_name(entry["device_name"]), short_name(entry["hostname"])):
                return "suggest", entry["device_id"]

    return "new", None
```

`atlas/devices/status.py`:

```python
def device_status(sightings, ok_runs):
    """
    seen      - some source saw it on its latest successful run (or it's in its
                one-run grace window)
    quiet     - every source that has seen it missed its last two successful runs
    invisible - only the operator's manual entry; no source has ever seen it

    Only successful runs count, so a failed scan or an unreachable Proxmox
    never makes devices look like they vanished.
    """

    observed = [sighting for sighting in sightings if sighting["source"] != "manual"]

    if not observed:
        return "invisible"

    def runs(sighting):
        return ok_runs.get(sighting["source"], [])

    if all(len(runs(s)) >= 2 and s["last_seen"] < runs(s)[1] for s in observed):
        return "quiet"

    return "seen"
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_devices_rules.py -q`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/devices/linking.py atlas/devices/status.py tests/test_devices_rules.py
git commit -m "feat(devices): certain-only linking rules and seen/quiet/invisible status"
```

---

### Task 4: `InventoryStore`

**Files:**
- Modify: `atlas/devices/store.py`
- Test: `tests/test_devices_store.py`

**Interfaces:**
- Consumes:
  - `match` and `device_status` (Task 3).
  - The models (Task 1).
  - `MapHost` (existing: `name, address, role, ports`).
- Produces `InventoryStore(engine=None)` with:
  - `import_manual_hosts(hosts, now=None) -> int`: the number added.
  - `record_run(source, sightings, ok=True, error="", now=None) -> dict`, with keys `new` (list of names), `linked`, `suggested`, `seen` and `baseline` (bool).
  - `devices(now=None) -> list[dict]`. Keys: `id, name, kind, tags, notes, important, state, suggested_merge_id, status, ip, last_seen, sightings`. Each sighting has `id, source, external_id, ip, mac, hostname, detail, first_seen, last_seen`, with ISO strings.
  - `queue_offline(now=None) -> list[str]`.
  - `due_notifications(now=None) -> dict[str, list[dict]]`. Items have `id, device, ip, last_seen`.
  - `mark_sent(ids, now=None) -> None`.
  - `source_runs(limit=20) -> list[dict]`, for Coverage in PR 2.

- [ ] **Step 1: Write the failing test** in `tests/test_devices_store.py`

```python
from datetime import datetime, timedelta

from atlas.config.models import MapHost
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore


T0 = datetime(2026, 9, 29, 12, 0)


def at(minutes):

    return T0 + timedelta(minutes=minutes)


def by_name(store):

    return {device["name"]: device for device in store.devices(now=at(999))}


def test_manual_hosts_import_once_as_known(temp_db):

    store = InventoryStore(temp_db)
    hosts = [MapHost(name="mediabox", address="192.168.10.57", role="LXC")]

    assert store.import_manual_hosts(hosts, now=T0) == 1
    assert store.import_manual_hosts(hosts, now=T0) == 0

    device = by_name(store)["mediabox"]
    assert device["state"] == "known"
    assert device["status"] == "invisible"
    assert device["notes"] == "LXC"


def test_lan_sighting_joins_configured_host_and_proxmox_name_is_suggested(temp_db):

    store = InventoryStore(temp_db)
    store.import_manual_hosts([MapHost(name="mediabox", address="192.168.10.57")], now=T0)

    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")], now=at(0))
    result = store.record_run("proxmox", [Sighting("proxmox", "pve:200", hostname="mediabox",
                                                   detail={"type": "lxc"})], now=at(0))

    devices = store.devices(now=at(0))
    mediabox = [d for d in devices if d["state"] == "known"][0]
    guest = [d for d in devices if d["state"] == "new"][0]

    assert {s["source"] for s in mediabox["sightings"]} == {"manual", "lan"}
    assert mediabox["status"] == "seen"
    assert guest["suggested_merge_id"] == mediabox["id"]
    assert guest["kind"] == "lxc"
    assert result["suggested"] == 1


def test_first_run_is_baseline_without_alerts_then_new_devices_alert(temp_db):

    store = InventoryStore(temp_db)

    first = store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01", hostname="router.lan")], now=at(0))
    assert first["baseline"] is True
    assert store.due_notifications(now=at(0)) == {}

    second = store.record_run("lan", [Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")], now=at(15))
    assert second["new"] == ["192.168.10.2"]
    assert [item["device"] for item in store.due_notifications(now=at(15))["new"]] == ["192.168.10.2"]
    assert by_name(store)["router"]["name"] == "router"


def test_resighting_updates_not_duplicates(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.9", mac="aa:01")], now=at(15))

    devices = store.devices(now=at(15))
    assert len(devices) == 1
    assert devices[0]["ip"] == "192.168.10.9"
    assert len(devices[0]["sightings"]) == 1


def test_failed_run_does_not_make_devices_quiet(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.record_run("lan", [], ok=False, error="boom", now=at(15))
    store.record_run("lan", [], ok=False, error="boom", now=at(30))

    assert store.devices(now=at(30))[0]["status"] == "seen"
    assert store.source_runs()[0]["error"] == "boom"


def test_important_device_offline_queues_once_and_new_alerts_roll_up(temp_db):

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01")], now=at(0))
    store.set_fields(store.devices()[0]["id"], {"important": True})

    store.record_run("lan", [], now=at(15))
    store.record_run("lan", [], now=at(30))

    assert store.queue_offline(now=at(30)) == ["192.168.10.1"]
    assert store.queue_offline(now=at(45)) == []
    offline = store.due_notifications(now=at(30))["offline"]
    store.mark_sent([item["id"] for item in offline], now=at(30))

    store.record_run("lan", [Sighting("lan", "aa:03", mac="aa:03", ip="192.168.10.3")], now=at(45))
    new = store.due_notifications(now=at(45))["new"]
    store.mark_sent([item["id"] for item in new], now=at(45))
    store.record_run("lan", [Sighting("lan", "aa:04", mac="aa:04", ip="192.168.10.4")], now=at(60))

    assert "new" not in store.due_notifications(now=at(60))
    assert "new" in store.due_notifications(now=at(60 + 24 * 60))
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_devices_store.py -q`
Expected: FAIL (ImportError `InventoryStore`).

- [ ] **Step 3: Implement** `atlas/devices/store.py`

This replaces the stub. `set_fields` is included because the offline test needs `important`. PR 2's edit API reuses it.

```python
"""
The device inventory: sightings from each source are upserted, linked to a
device by atlas.devices.linking's certain-only rules, and turned into a
status plus queued alerts. Takes an explicit engine (tests pass a temp one);
defaults to this module's `engine`, which tests/conftest.py's temp_db also
patches.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import DeviceRecord, NotificationRecord, SightingRecord, SourceRunRecord
from atlas.devices.linking import match
from atlas.devices.status import device_status


ROLLUP = timedelta(hours=24)

EDITABLE = {"name", "kind", "tags", "notes", "important", "state"}

GUEST_KINDS = {"qemu": "vm", "lxc": "lxc"}


def _iso(value):

    return value.isoformat() if value else None


class InventoryStore:

    def __init__(self, target_engine=None):

        self.engine = target_engine or engine
        initialize_database(self.engine)

    def import_manual_hosts(self, hosts, now=None):
        """map.hosts become known devices with a locked name - once per address."""

        now = now or datetime.utcnow()
        added = 0

        with Session(self.engine) as session:

            for host in hosts:

                exists = session.scalar(select(SightingRecord.id).where(
                    SightingRecord.source == "manual", SightingRecord.external_id == host.address))

                if exists:
                    continue

                device = DeviceRecord(name=host.name, state="known", notes=host.role,
                                      locked_fields=json.dumps(["name"]), created_at=now, updated_at=now)
                session.add(device)
                session.flush()
                session.add(SightingRecord(source="manual", external_id=host.address, ip=host.address,
                                           device_id=device.id, first_seen=now, last_seen=now))
                added += 1

            session.commit()

        return added

    def _known(self, session):

        rows = session.execute(
            select(SightingRecord, DeviceRecord.name).join(DeviceRecord, SightingRecord.device_id == DeviceRecord.id)
        ).all()

        return [{"device_id": row.device_id, "device_name": name, "source": row.source,
                 "ip": row.ip, "mac": row.mac, "hostname": row.hostname} for row, name in rows]

    def record_run(self, source, sightings, ok=True, error="", now=None):

        now = now or datetime.utcnow()
        result = {"new": [], "linked": 0, "suggested": 0, "seen": len(sightings) if ok else 0, "baseline": False}

        with Session(self.engine) as session:

            result["baseline"] = ok and not session.scalar(select(SourceRunRecord.id).where(
                SourceRunRecord.source == source, SourceRunRecord.ok.is_(True)))

            session.add(SourceRunRecord(source=source, started_at=now, ok=ok, error=error, seen_count=result["seen"]))

            if not ok:
                session.commit()
                return result

            for new in sightings:

                row = session.scalar(select(SightingRecord).where(
                    SightingRecord.source == source, SightingRecord.external_id == new.external_id))

                if row is None:

                    verdict, device_id = match(new, self._known(session))

                    if verdict == "link":
                        result["linked"] += 1

                    else:
                        device = DeviceRecord(
                            name=(new.hostname or "").split(".")[0] or new.ip or new.external_id,
                            kind=GUEST_KINDS.get(new.detail.get("type"), "other"),
                            suggested_merge_id=device_id if verdict == "suggest" else None,
                            created_at=now, updated_at=now)
                        session.add(device)
                        session.flush()
                        device_id = device.id
                        result["new"].append(device.name)
                        result["suggested"] += verdict == "suggest"

                        if not result["baseline"]:
                            session.add(NotificationRecord(device_id=device.id, kind="new", created_at=now))

                    row = SightingRecord(source=source, external_id=new.external_id, first_seen=now, device_id=device_id)
                    session.add(row)

                row.ip, row.mac, row.hostname = new.ip, new.mac, new.hostname
                row.detail, row.last_seen = json.dumps(new.detail), now
                session.flush()

            session.commit()

        return result

    def set_fields(self, device_id, fields, now=None):
        """Operator edit: applies only EDITABLE fields and locks each one it sets."""

        with Session(self.engine) as session:

            device = session.get(DeviceRecord, device_id)

            if device is None:
                return {"found": False}

            locked = set(json.loads(device.locked_fields))

            for key, value in fields.items():

                if key not in EDITABLE:
                    continue

                setattr(device, key, json.dumps(value) if key == "tags" else value)
                locked.add(key)

            device.locked_fields = json.dumps(sorted(locked))
            device.updated_at = now or datetime.utcnow()
            session.commit()

        return {"found": True}

    def _ok_runs(self, session):

        runs = {}

        for run in session.scalars(select(SourceRunRecord).where(SourceRunRecord.ok.is_(True))
                                   .order_by(SourceRunRecord.started_at.desc())):
            runs.setdefault(run.source, []).append(run.started_at)

        return runs

    def devices(self, now=None):

        with Session(self.engine) as session:

            ok_runs = self._ok_runs(session)
            sightings = {}

            for row in session.scalars(select(SightingRecord)):
                sightings.setdefault(row.device_id, []).append(row)

            output = []

            for device in session.scalars(select(DeviceRecord).order_by(DeviceRecord.name)):

                rows = sightings.get(device.id, [])
                observed = [row for row in rows if row.source != "manual"] or rows
                preferred = sorted(observed, key=lambda row: (row.source != "lan", row.ip is None))

                output.append({
                    "id": device.id, "name": device.name, "kind": device.kind,
                    "tags": json.loads(device.tags), "notes": device.notes, "important": device.important,
                    "state": device.state, "suggested_merge_id": device.suggested_merge_id,
                    "status": device_status([{"source": row.source, "last_seen": row.last_seen} for row in rows], ok_runs),
                    "ip": next((row.ip for row in preferred if row.ip), None),
                    "last_seen": _iso(max((row.last_seen for row in observed), default=None)),
                    "sightings": [{"id": row.id, "source": row.source, "external_id": row.external_id,
                                   "ip": row.ip, "mac": row.mac, "hostname": row.hostname,
                                   "detail": json.loads(row.detail), "first_seen": _iso(row.first_seen),
                                   "last_seen": _iso(row.last_seen)} for row in rows],
                })

        return output

    def queue_offline(self, now=None):
        """One offline alert per episode: skipped if one was queued since it was last seen."""

        now = now or datetime.utcnow()
        queued = []

        candidates = [device for device in self.devices(now)
                      if device["important"] and device["status"] == "quiet" and device["state"] != "ignored"]

        with Session(self.engine) as session:

            for device in candidates:

                since = datetime.fromisoformat(device["last_seen"]) if device["last_seen"] else datetime.min
                already = session.scalar(select(NotificationRecord.id).where(
                    NotificationRecord.device_id == device["id"], NotificationRecord.kind == "offline",
                    NotificationRecord.created_at >= since))

                if not already:
                    session.add(NotificationRecord(device_id=device["id"], kind="offline", created_at=now))
                    queued.append(device["name"])

            session.commit()

        return queued

    def due_notifications(self, now=None):

        now = now or datetime.utcnow()
        devices = {device["id"]: device for device in self.devices(now)}
        due = {}

        with Session(self.engine) as session:

            last_new = session.scalar(select(NotificationRecord.sent_at).where(
                NotificationRecord.kind == "new", NotificationRecord.sent_at.is_not(None))
                .order_by(NotificationRecord.sent_at.desc()))

            for note in session.scalars(select(NotificationRecord).where(NotificationRecord.sent_at.is_(None))
                                        .order_by(NotificationRecord.created_at)):

                if note.kind == "new" and last_new and now - last_new < ROLLUP:
                    continue

                device = devices.get(note.device_id, {})
                due.setdefault(note.kind, []).append({
                    "id": note.id, "device": device.get("name", "?"),
                    "ip": device.get("ip"), "last_seen": device.get("last_seen")})

        return due

    def mark_sent(self, ids, now=None):

        with Session(self.engine) as session:

            for note in session.scalars(select(NotificationRecord).where(NotificationRecord.id.in_(ids))):
                note.sent_at = now or datetime.utcnow()

            session.commit()

    def source_runs(self, limit=20):

        with Session(self.engine) as session:

            return [{"source": run.source, "started_at": _iso(run.started_at), "ok": run.ok,
                     "error": run.error, "seen_count": run.seen_count}
                    for run in session.scalars(select(SourceRunRecord)
                                               .order_by(SourceRunRecord.started_at.desc()).limit(limit))]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_devices_store.py tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add atlas/devices/store.py tests/test_devices_store.py
git commit -m "feat(devices): InventoryStore - runs, linking, status, offline + rolled-up new alerts"
```

---

### Task 5: Signal delivery (`atlas/devices/notify.py`)

**Files:**
- Create: `atlas/devices/notify.py`
- Test: `tests/test_devices_notify.py`

**Interfaces:**
- Consumes:
  - `InventoryStore.due_notifications` and `.mark_sent` (Task 4).
  - `SignalNotifyConfig` (Task 1).
- Produces:
  - `format_message(kind, items) -> str`.
  - `send_signal(config, text) -> tuple[bool, str]`.
  - `deliver(store, config, now=None) -> list[str]`: the error messages.

- [ ] **Step 1: Write the failing test** in `tests/test_devices_notify.py`

```python
import json

import atlas.devices.notify as notify
from atlas.config.models import SignalNotifyConfig


ITEMS = [{"id": 1, "device": "Pixel-7", "ip": "192.168.10.88", "last_seen": "2026-09-29T12:00:00"},
         {"id": 2, "device": "192.168.10.90", "ip": "192.168.10.90", "last_seen": None}]


def test_format_new_message_is_bold_headline_and_short_lines():

    text = notify.format_message("new", ITEMS)

    assert text.splitlines()[0] == "**🆕 2 new devices on the network**"
    assert "• Pixel-7 (192.168.10.88)" in text
    assert text.rstrip().endswith("Triage them in atlas.")


def test_format_offline_message():

    text = notify.format_message("offline", ITEMS[:1])

    assert text.splitlines()[0] == "**🔴 Important device offline**"
    assert "last seen 2026-09-29 12:00" in text


def test_send_signal_posts_styled_json(monkeypatch):

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"], captured["body"] = request.full_url, json.loads(request.data)

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    config = SignalNotifyConfig(url="http://signal-cli:8080/", number="+1555", recipients=["+1555"])

    assert notify.send_signal(config, "hi") == (True, "")
    assert captured["url"] == "http://signal-cli:8080/v2/send"
    assert captured["body"] == {"message": "hi", "number": "+1555", "recipients": ["+1555"], "text_mode": "styled"}


def test_send_signal_failure_is_returned_not_raised(monkeypatch):

    def boom(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)

    assert notify.send_signal(SignalNotifyConfig(url="http://x"), "hi") == (False, "connection refused")


class FakeStore:

    def __init__(self):
        self.sent = []

    def due_notifications(self, now=None):
        return {"new": ITEMS}

    def mark_sent(self, ids, now=None):
        self.sent += ids


def test_deliver_marks_sent_only_on_success(monkeypatch):

    store = FakeStore()
    monkeypatch.setattr(notify, "send_signal", lambda config, text: (False, "down"))
    assert notify.deliver(store, SignalNotifyConfig(url="http://x")) == ["down"]
    assert store.sent == []

    monkeypatch.setattr(notify, "send_signal", lambda config, text: (True, ""))
    assert notify.deliver(store, SignalNotifyConfig(url="http://x")) == []
    assert store.sent == [1, 2]


def test_deliver_without_url_does_nothing():

    store = FakeStore()

    assert notify.deliver(store, SignalNotifyConfig()) == []
    assert store.sent == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_devices_notify.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement** `atlas/devices/notify.py`

```python
"""
Signal alerts through signal-cli-rest-api (POST /v2/send, styled text so
**bold** renders). A failed send leaves the items queued for the next run.
"""

import json
import urllib.request


def _line(item):

    where = f" ({item['ip']})" if item.get("ip") and item["ip"] != item["device"] else ""

    return f"• {item['device']}{where}"


def format_message(kind, items):

    if kind == "offline":
        lines = ["**🔴 Important device offline**" if len(items) == 1 else f"**🔴 {len(items)} important devices offline**"]
        lines += [_line(item) + (f" - last seen {item['last_seen'][:16].replace('T', ' ')}" if item.get("last_seen") else "")
                  for item in items]
        return "\n".join(lines)

    lines = ["**🆕 New device on the network**" if len(items) == 1 else f"**🆕 {len(items)} new devices on the network**"]
    lines += [_line(item) for item in items]
    lines += ["", "Triage them in atlas."]

    return "\n".join(lines)


def send_signal(config, text):

    body = json.dumps({"message": text, "number": config.number,
                       "recipients": config.recipients, "text_mode": "styled"}).encode()
    request = urllib.request.Request(config.url.rstrip("/") + "/v2/send", data=body,
                                     headers={"Content-Type": "application/json"})

    try:
        urllib.request.urlopen(request, timeout=15)
        return True, ""

    except (OSError, ValueError) as error:
        return False, str(error)


def deliver(store, config, now=None):

    if not config.url:
        return []

    errors = []

    for kind, items in store.due_notifications(now).items():

        ok, error = send_signal(config, format_message(kind, items))

        if ok:
            store.mark_sent([item["id"] for item in items], now)
        else:
            errors.append(error)

    return errors
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_devices_notify.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/devices/notify.py tests/test_devices_notify.py
git commit -m "feat(devices): Signal alerts for new/offline devices, retried until sent"
```

---

### Task 6: CLI (`atlas scan`, `atlas devices`, Proxmox sightings in `atlas map`)

**Files:**
- Modify: `atlas/cli/main.py`. Add the two commands just after `network_map` and extend `network_map`.
- Test: `tests/test_devices_cli.py`

**Interfaces:**
- Consumes: `lan.scan`, `InventoryStore`, `deliver`, `Sighting`, and `load_config` (whose `settings.scan`, `settings.notify.signal` and `settings.map.hosts` exist).
- Produces:
  - `atlas scan [--json]`: exit 0 on success, 1 on scan failure (recorded as a failed run).
  - `atlas devices [--json]`.
  - The event `atlas.devices.scan.completed` (source `LanScan`).
  - `atlas map` writes a `proxmox` source run.

- [ ] **Step 1: Write the failing test** in `tests/test_devices_cli.py`

```python
import json

from typer.testing import CliRunner

import atlas.devices.lan as lan
from atlas.cli.main import app
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore


runner = CliRunner()


def test_scan_records_devices_and_devices_lists_them(temp_db, isolated_cwd, monkeypatch):

    (isolated_cwd / "atlas.yaml").write_text(
        "map:\n  hosts:\n    - name: mediabox\n      address: 192.168.10.57\n")
    monkeypatch.setattr(lan, "scan", lambda subnets, timeout: (
        ["192.168.10.0/24"], [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")]))

    result = runner.invoke(app, ["scan", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["linked"] == 1

    listed = runner.invoke(app, ["devices", "--json"])
    devices = json.loads(listed.output)
    assert [d["name"] for d in devices] == ["mediabox"]
    assert devices[0]["status"] == "seen"


def test_scan_failure_is_recorded_and_exits_1(temp_db, isolated_cwd, monkeypatch):

    def boom(subnets, timeout):
        raise RuntimeError("no subnet to scan")

    (isolated_cwd / "atlas.yaml").write_text("name: test\n")
    monkeypatch.setattr(lan, "scan", boom)

    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 1
    run = InventoryStore().source_runs()[0]
    assert (run["source"], run["ok"], run["error"]) == ("lan", False, "no subnet to scan")


def test_scan_disabled_does_nothing(temp_db, isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text("scan:\n  enabled: false\n")

    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 0
    assert InventoryStore().source_runs() == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_devices_cli.py -q`
Expected: FAIL (`No such command 'scan'`).

- [ ] **Step 3: Implement.** In `atlas/cli/main.py`, directly after the `network_map` function:

```python
@app.command(name="scan")
def lan_scan(
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON")
):
    """
    Find every device on the LAN and update the device inventory: links
    each sighting to a known device when certain, queues new devices for
    triage, and sends Signal alerts (notify.signal) for new devices and
    for important devices gone quiet. Run by the atlas-scan container.
    """

    from atlas.devices import lan
    from atlas.devices.notify import deliver
    from atlas.devices.store import InventoryStore

    settings = load_config()

    if not settings.scan.enabled:
        console.print("LAN scanning is off (scan.enabled: false in atlas.yaml).")
        return

    store = InventoryStore()
    store.import_manual_hosts(settings.map.hosts)

    try:
        subnets, sightings = lan.scan(settings.scan.subnets, settings.scan.timeout)

    except Exception as error:  # any failure is a failed source run, shown on Coverage
        store.record_run("lan", [], ok=False, error=str(error))
        console.print(f"[red]Scan failed:[/red] {error}")
        raise typer.Exit(1)

    result = store.record_run("lan", sightings)
    result["subnets"] = subnets
    result["offline"] = store.queue_offline()
    result["notify_errors"] = deliver(store, settings.notify.signal)

    application.runtime.events.publish(
        AtlasEvent(event_type="atlas.devices.scan.completed", source="LanScan", payload=result)
    )

    if json_output:
        print(json.dumps(result, indent=2))
        return

    console.print(f"Scanned {', '.join(subnets)}: {result['seen']} devices, "
                  f"{len(result['new'])} new, {result['linked']} linked"
                  + (" (baseline - no alerts on the first scan)" if result["baseline"] else ""))

    for name in result["offline"]:
        console.print(f"[red]Offline:[/red] {name}")

    for error in result["notify_errors"]:
        console.print(f"[yellow]Signal alert not sent:[/yellow] {error}")


@app.command()
def devices(
    json_output: bool = typer.Option(False, "--json", help="Print the inventory as JSON")
):
    """The device inventory: every device atlas knows, its status and where it was seen."""

    from atlas.devices.store import InventoryStore

    inventory = InventoryStore().devices()

    if json_output:
        print(json.dumps(inventory, indent=2))
        return

    colors = {"seen": "green", "quiet": "yellow", "invisible": "dim"}

    for device in inventory:
        sources = ",".join(sorted({sighting["source"] for sighting in device["sightings"]}))
        console.print(f"[{colors.get(device['status'], 'white')}]{device['status']:<9}[/] "
                      f"{device['name']:<24} {device['ip'] or '-':<16} {device['state']:<7} {sources}")
```

In `network_map`, directly after the `if settings.proxmox.enabled:` block that fills `guests`, add:

```python
    if settings.proxmox.enabled:

        from atlas.devices import Sighting
        from atlas.devices.store import InventoryStore

        InventoryStore().record_run(
            "proxmox",
            [Sighting("proxmox", f"pve:{guest['vmid']}", hostname=guest.get("name"),
                      detail={"type": guest.get("type"), "status": guest.get("status")})
             for guest in guests if not guest.get("template")],
            ok=client is not None,
            error="" if client else "could not connect to Proxmox"
        )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, including `test_cli_smoke.py`. If the smoke test enumerates commands, add `scan` and `devices` to its list.

- [ ] **Step 5: Commit**

```bash
git add atlas/cli/main.py tests/test_devices_cli.py tests/test_cli_smoke.py
git commit -m "feat(devices): atlas scan / atlas devices; atlas map records Proxmox guests"
```

---

### Task 7: `atlas-scan` container and docs

**Files:**
- Modify: `docker-compose.yml`, `docs/configuration.md`, `docs/cli-reference.md`, `README.md`, and `docs/superpowers/specs/2026-09-29-network-inventory-design.md`
- Test: `tests/test_stack_ready.py` (extend the existing compose assertions)

- [ ] **Step 1: Write the failing test.** Append to `tests/test_stack_ready.py`:

```python
def test_compose_has_host_network_scanner():

    import yaml
    from pathlib import Path

    compose = yaml.safe_load(Path(__file__).resolve().parents[1].joinpath("docker-compose.yml").read_text())
    scanner = compose["services"]["atlas-scan"]

    assert scanner["network_mode"] == "host"
    assert "atlas scan" in " ".join(scanner["command"])
    assert "atlas-refresh" not in compose["services"]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_stack_ready.py -q`
Expected: FAIL (KeyError `atlas-scan`).

- [ ] **Step 3: Implement.** In `docker-compose.yml`, replace the whole `atlas-refresh:` service, and the "Optional: ... --profile refresh" header comment, with the following. Update the header comment to say atlas-scan keeps the inventory and map fresh.

```yaml
  # Finds every device on the LAN and refreshes discover / Proxmox / map every
  # ATLAS_SCAN_MINUTES (default 15). Host networking is what lets it see the
  # LAN's MAC addresses (it reads the host's ARP table); it needs no extra
  # capabilities. Writes the same database the atlas web container reads.
  atlas-scan:
    <<: *atlas
    network_mode: host
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      ATLAS_SCAN_MINUTES: ${ATLAS_SCAN_MINUTES:-15}
    healthcheck:
      disable: true
    command:
      - sh
      - -c
      - |
        while :; do
          atlas scan
          atlas discover >/dev/null 2>&1
          atlas proxmox scan >/dev/null 2>&1
          atlas map >/dev/null 2>&1 && echo "$$(date -u +%FT%TZ) map refreshed"
          sleep "$${ATLAS_SCAN_MINUTES:-15}m"
        done
```

Docs:
- `docs/configuration.md`: add `## scan` (the four keys, the TCP-poke/ARP explanation, and the 1024-address cap) and `## notify` (the `signal.url/number/recipients` example pointing at `http://signal-cli:8080`, the baseline and 24h roll-up behaviour, and "empty url = off"), after `## map`.
- `docs/cli-reference.md`: rows for `atlas scan` and `atlas devices`, next to `atlas map`.
- `README.md`: one line in the features list: "Device inventory: finds every device on your LAN, links duplicates, and alerts on new or offline devices".
- The spec's "LAN discovery" section: replace step 1 (ping + NET_RAW) with "TCP connect to port 9 on every address (the kernel ARP-resolves each one); no ping or NET_RAW". Also fix the table row (`cap_add` removed) and the error-handling line about NET_RAW.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/ -q && docker compose config -q`
Expected: all pass, and the compose file validates.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml docs README.md tests/test_stack_ready.py
git commit -m "feat(devices): atlas-scan container replaces atlas-refresh; docs"
```

---

### Task 8: Real-infrastructure verification on cyberpac (before the PR merges)

No code. This proves the feature against the real LAN, which is a project rule: a mocked suite is necessary but not sufficient.

- [ ] **Step 1: Build a test image from the branch on cyberpac and run a scan in a throwaway copy of the database**

```bash
ssh sentinel@192.168.10.157 'cd ~/atlas && git fetch -q && git checkout -q feat/network-inventory \
  && docker build -q -t atlas:inventory-test . \
  && mkdir -p /tmp/atlas-inv && cp data/inventory/atlas.db /tmp/atlas-inv/ \
  && docker run --rm --network host -u 1000:1000 -v ~/atlas/atlas.yaml:/data/atlas.yaml:ro \
       -v /tmp/atlas-inv:/data/inventory atlas:inventory-test sh -c "atlas scan && atlas devices"'
```

Expected:
- 20 or more devices on 192.168.10.0/24.
- The configured hosts are `seen` and state `known`. Desktop GT32R shows `invisible` if it's off.
- "baseline" is printed.

- [ ] **Step 2: Proxmox linking.** Run `atlas map` in the same container (add `-v /var/run/docker.sock:/var/run/docker.sock --group-add 983`), then `atlas devices --json`.

Expected: the mediabox and media-tools guests appear as `new` devices whose `suggested_merge_id` points at the known mediabox / media-tools. They are not linked automatically.

- [ ] **Step 3: Signal.** With a temporary `notify.signal` block (`url: http://127.0.0.1:<signal-cli host port or container IP>:8080`, the operator's number as both `number` and `recipients`), delete one LAN sighting row from `/tmp/atlas-inv/atlas.db` with sqlite3 and scan again.

Expected: one "🆕 New device" Signal Note-to-Self arrives.

- [ ] **Step 4: Clean up.** `rm -rf /tmp/atlas-inv; docker rmi atlas:inventory-test; git checkout -q main`. Deploy is PR 5; the live database is untouched.

- [ ] **Step 5: Open the PR**, with the verification output in the body. Merge only after `gh pr checks` is green and the user says so.
