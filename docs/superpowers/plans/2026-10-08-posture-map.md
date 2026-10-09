# Atlas Posture Map + New Shell (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Atlas's web front door with a posture page (status strip + zone map of inbound / outbound / VPN traffic + details panel + chat drawer) fed by a new `atlas posture watch` collector, and extend the Homepage tile.

**Architecture:** New `atlas/posture/` package: pure collectors (conntrack, ASN, Traefik routes, gluetun, CrowdSec, public IP) → an `Accountant` that turns cumulative conntrack counters into per-hour deltas → `PostureStore` (SQLite, same engine as everything else) → `build_posture()` model served as JSON by the existing stdlib web server and drawn by vendored Cytoscape with preset positions. The collector runs as a second loop inside the existing `atlas-scan` container.

**Tech Stack:** Python 3.11+, SQLAlchemy (existing), stdlib `http.server` (existing), `requests` (existing), `pyyaml` (existing), vendored `cytoscape.min.js` (existing), Debian `conntrack` + `libcap2-bin` in the image. No new Python dependencies.

**Spec:** `docs/superpowers/specs/2026-10-08-posture-map-design.md`

## Global Constraints

- No new Python dependencies (pyproject `dependencies` unchanged); no frontend build step; no runtime fetch of fonts or scripts from the internet.
- The page stays read-only except `POST /api/posture/known`, which goes through the existing `do_POST` path (same-origin check, 64 KB cap).
- Atlas never writes netfilter state; `NET_ADMIN` is only for `conntrack -L`.
- Secrets (`posture.crowdsec_api_key`, `posture.gluetun_api_key`) are never rendered, logged, or returned by any API.
- ASN/country lookups are offline (local iptoasn file); destination IPs are never sent to a third party. Note: clicking a destination does one PTR lookup of its top address through the host's resolver (1 s bound) - the only time a destination IP leaves the host.
- A failing source never fails a page or the collector loop: it is recorded in `posture_status` with `ok=False` and shown grey.
- Every user-visible string from data goes through `_esc()` (server) or `textContent` (browser).
- Test fixtures use documentation/sanitized IPs only (the repo is public): `203.0.113.0/24`, `198.51.100.0/24`, `192.0.2.0/24`, private ranges, `100.64.0.0/10`.
- Commits: no `Co-Authored-By` or AI trailer (workspace rule). Run `python -m pytest tests/` before each commit.
- Match the style of the file you edit; new modules follow `atlas/devices/store.py`'s compact style.

## File Map

| File | Responsibility |
|---|---|
| `atlas/config/models.py` (modify) | `PostureConfig`, `AtlasConfig.posture` |
| `atlas/database/models.py` (modify) | 5 posture tables |
| `atlas/posture/__init__.py` | package marker |
| `atlas/posture/store.py` | `PostureStore` - all posture reads/writes |
| `atlas/posture/collectors/__init__.py` | package marker |
| `atlas/posture/collectors/conntrack.py` | parse/read `conntrack -L -o extended,id` |
| `atlas/posture/collectors/asn.py` | iptoasn parse, lookup table, weekly refresh |
| `atlas/posture/collectors/traefik.py` | routes from Docker labels + file-provider YAML |
| `atlas/posture/collectors/services.py` | container IP lookup, gluetun, CrowdSec, public IP |
| `atlas/posture/aggregate.py` | `Accountant` (counter deltas, classification), inbound/tunnel counts |
| `atlas/posture/collect.py` | `collect_once()` orchestration |
| `atlas/posture/model.py` | `build_posture()`, `node_details()` - JSON for the UI |
| `atlas/cli/main.py` (modify) | `atlas posture watch` |
| `atlas/web/api.py` (modify) | `/api/posture`, `/api/posture/node`, `/api/posture/known` |
| `atlas/web/chat_assets.py` | shared chat CSS/JS (moved out of `chat_page.py`) |
| `atlas/web/render.py` (modify) | new nav shell, tabs, chat drawer, `build_summary` posture block |
| `atlas/web/posture_page.py` | posture page markup + map/panel JS |
| `atlas/web/server.py` (modify) | `/` → posture page, `/overview` keeps the old overview |
| `Dockerfile`, `docker-compose.yml` (modify) | conntrack + setcap; scan loop runs `atlas posture watch` |
| `tests/fixtures/posture/*` | sanitized samples |
| `tests/test_posture_*.py` | per-unit tests |

---

## PR 1 - collectors + storage

### Task 1: Config + tables + PostureStore

**Files:**
- Modify: `atlas/config/models.py` (add class before `AtlasConfig`, add field)
- Modify: `atlas/database/models.py` (append 5 models)
- Create: `atlas/posture/__init__.py`, `atlas/posture/store.py`
- Modify: `tests/conftest.py` (patch the posture store engine in `temp_db`)
- Test: `tests/test_posture_store.py`

**Interfaces:**
- Produces:
  - `PostureConfig` fields: `enabled: bool=False`, `interval: int=30`, `retention_days: int=30`, `host_ip: str=""`, `gluetun_container: str="gluetun"`, `gluetun_port: int=8000`, `gluetun_api_key: str=""`, `crowdsec_container: str="crowdsec"`, `crowdsec_port: int=8080`, `crowdsec_api_key: str=""`, `cloudflared_container: str="cloudflared"`, `traefik_container: str="traefik"`, `traefik_dynamic_dir: str=""`, `auth_middleware: str="authelia"`, `ip_echo_url: str="https://api.ipify.org"`, `asn_url: str="https://iptoasn.com/data/ip2asn-v4.tsv.gz"`, `asn_path: str="inventory/ip2asn-v4.tsv.gz"`.
  - `asn_key(asn: int, dest_ip: str) -> str` → `"AS<n>"` or `"ip:<dest_ip>"` when `asn` is 0.
  - `PostureStore(engine=None)` with:
    - `record_flows(deltas: list[dict], now: datetime) -> list[dict]` - each delta dict has keys `source, band, dest_ip, dest_port, proto, asn, org, cc, bytes_out, bytes_in, new_conn`; returns newly first-seen `{"source","asn_key","org","cc"}` that are not in `posture_known`.
    - `flows(since: datetime) -> list[dict]` (row dicts incl. `hour`).
    - `seen() -> list[dict]` keys `source, asn_key, org, cc, first_seen, last_seen, known`.
    - `mark_known(source: str, asn_key: str, note: str="") -> dict` → `{"ok": True}` or `{"ok": False, "error": ...}`.
    - `set_status(source: str, ok: bool, detail: dict, now: datetime) -> None`; `statuses() -> dict[str, dict]` (`{"ok","detail","updated_at"}`).
    - `save_routes(routes: list[dict], now: datetime) -> bool` (True when the set changed); `latest_routes() -> list[dict]` (keys `name, hosts, entrypoints, protection, provider`).
    - `prune(before: datetime) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_posture_store.py
from datetime import datetime, timedelta

from atlas.posture.store import PostureStore, asn_key


NOW = datetime(2026, 10, 8, 13, 42, 10)


def delta(**overrides):
    base = {"source": "sonarr", "band": "direct", "dest_ip": "203.0.113.7", "dest_port": 443, "proto": "tcp",
            "asn": 64500, "org": "EXAMPLE-NET", "cc": "US", "bytes_out": 100, "bytes_in": 900, "new_conn": True}
    return {**base, **overrides}


def test_asn_key_falls_back_to_ip_when_asn_unknown():
    assert asn_key(64500, "203.0.113.7") == "AS64500"
    assert asn_key(0, "203.0.113.7") == "ip:203.0.113.7"


def test_record_flows_accumulates_per_hour_and_reports_first_seen(temp_db):
    store = PostureStore(temp_db)

    new = store.record_flows([delta()], NOW)
    assert new == [{"source": "sonarr", "asn_key": "AS64500", "org": "EXAMPLE-NET", "cc": "US"}]

    again = store.record_flows([delta(bytes_out=50, bytes_in=50, new_conn=False)], NOW + timedelta(minutes=5))
    assert again == []

    rows = store.flows(NOW - timedelta(hours=1))
    assert len(rows) == 1
    assert (rows[0]["bytes_out"], rows[0]["bytes_in"], rows[0]["conns"]) == (150, 950, 1)
    assert rows[0]["hour"] == datetime(2026, 10, 8, 13)


def test_new_hour_gets_its_own_bucket(temp_db):
    store = PostureStore(temp_db)
    store.record_flows([delta()], NOW)
    store.record_flows([delta(new_conn=False)], NOW + timedelta(hours=1))
    assert len(store.flows(NOW - timedelta(hours=2))) == 2


def test_mark_known_hides_from_new_and_flags_seen(temp_db):
    store = PostureStore(temp_db)
    assert store.mark_known("sonarr", "AS64500") == {"ok": True}
    assert store.record_flows([delta()], NOW) == []
    assert store.seen()[0]["known"] is True


def test_mark_known_validates(temp_db):
    store = PostureStore(temp_db)
    assert store.mark_known("", "AS1")["ok"] is False
    assert store.mark_known("sonarr", "nonsense")["ok"] is False


def test_status_roundtrip(temp_db):
    store = PostureStore(temp_db)
    store.set_status("gluetun", True, {"exit_ip": "198.51.100.9"}, NOW)
    store.set_status("gluetun", False, {"error": "timeout"}, NOW + timedelta(seconds=30))
    status = store.statuses()["gluetun"]
    assert status["ok"] is False and status["detail"] == {"error": "timeout"}
    assert status["updated_at"] == NOW + timedelta(seconds=30)


def test_save_routes_reports_change_only_when_set_differs(temp_db):
    store = PostureStore(temp_db)
    routes = [{"name": "atlas", "hosts": ["atlas.example.test"], "entrypoints": ["websecure"],
               "protection": "authelia", "provider": "docker"}]
    assert store.save_routes(routes, NOW) is True
    assert store.save_routes(routes, NOW + timedelta(minutes=1)) is False
    assert store.latest_routes() == routes


def test_prune_drops_old_flow_buckets(temp_db):
    store = PostureStore(temp_db)
    store.record_flows([delta()], NOW - timedelta(days=40))
    store.record_flows([delta(new_conn=False)], NOW)
    assert store.prune(NOW - timedelta(days=30)) == 1
    assert len(store.flows(NOW - timedelta(days=100))) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'atlas.posture'`

- [ ] **Step 3: Implement config, models, store**

Add to `atlas/config/models.py` (before `class AtlasConfig`):

```python
class PostureConfig(BaseModel):
    """Egress/posture collector (atlas posture watch). Off unless enabled."""
    enabled: bool = False
    interval: int = 30
    retention_days: int = 30
    host_ip: str = ""
    gluetun_container: str = "gluetun"
    gluetun_port: int = 8000
    gluetun_api_key: str = ""
    crowdsec_container: str = "crowdsec"
    crowdsec_port: int = 8080
    crowdsec_api_key: str = ""
    cloudflared_container: str = "cloudflared"
    traefik_container: str = "traefik"
    traefik_dynamic_dir: str = ""
    auth_middleware: str = "authelia"
    ip_echo_url: str = "https://api.ipify.org"
    asn_url: str = "https://iptoasn.com/data/ip2asn-v4.tsv.gz"
    asn_path: str = "inventory/ip2asn-v4.tsv.gz"
```

and in `AtlasConfig` add the line `posture: PostureConfig = PostureConfig()` after `notify`.

Append to `atlas/database/models.py` (`UniqueConstraint` is already imported):

```python
class PostureFlowRecord(Base):
    """Bytes/connections per hour per (source container, destination ip:port/proto)."""

    __tablename__ = "posture_flows"
    __table_args__ = (UniqueConstraint("hour", "source", "dest_ip", "dest_port", "proto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hour: Mapped[datetime]
    source: Mapped[str]
    band: Mapped[str]
    dest_ip: Mapped[str]
    dest_port: Mapped[int]
    proto: Mapped[str]
    asn: Mapped[int] = mapped_column(default=0)
    org: Mapped[str] = mapped_column(default="")
    cc: Mapped[str] = mapped_column(default="")
    bytes_out: Mapped[int] = mapped_column(default=0)
    bytes_in: Mapped[int] = mapped_column(default=0)
    conns: Mapped[int] = mapped_column(default=0)


class PostureSeenRecord(Base):
    """First/last time a source talked to a network (ASN, or the bare IP when unknown)."""

    __tablename__ = "posture_seen"
    __table_args__ = (UniqueConstraint("source", "asn_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    asn_key: Mapped[str]
    org: Mapped[str] = mapped_column(default="")
    cc: Mapped[str] = mapped_column(default="")
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]


class PostureKnownRecord(Base):
    """Operator said this source->network pair is expected (Mark as expected)."""

    __tablename__ = "posture_known"
    __table_args__ = (UniqueConstraint("source", "asn_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    asn_key: Mapped[str]
    note: Mapped[str] = mapped_column(default="")
    marked_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class PostureRouteRecord(Base):
    """Snapshot of public routes; a new snapshot is written only when the set changes."""

    __tablename__ = "posture_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_at: Mapped[datetime]
    routes: Mapped[str]


class PostureStatusRecord(Base):
    """Last result per collector source - drives greying out stale bands."""

    __tablename__ = "posture_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(unique=True)
    ok: Mapped[bool]
    detail: Mapped[str] = mapped_column(default="{}")
    updated_at: Mapped[datetime]
```

Create `atlas/posture/__init__.py` with a single docstring line: `"""Egress/posture collection and model (atlas posture watch, the posture page)."""`

Create `atlas/posture/store.py`:

```python
"""
Posture storage: hourly flow buckets, first-seen networks per source, the
operator's "expected" list, route snapshots and per-collector status. Takes an
explicit engine (tests pass a temp one); defaults to this module's `engine`,
which tests/conftest.py's temp_db also patches.
"""

import json
import re
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import (PostureFlowRecord, PostureKnownRecord, PostureRouteRecord, PostureSeenRecord,
                                   PostureStatusRecord)


ASN_KEY = re.compile(r"^(AS\d+|ip:[0-9.]+)$")


def asn_key(asn, dest_ip):
    return f"AS{asn}" if asn else f"ip:{dest_ip}"


def _hour(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def _row(record, *fields):
    return {field: getattr(record, field) for field in fields}


FLOW_FIELDS = ("hour", "source", "band", "dest_ip", "dest_port", "proto", "asn", "org", "cc",
               "bytes_out", "bytes_in", "conns")


class PostureStore:

    def __init__(self, engine_=None):
        self.engine = engine_ or engine
        initialize_database(self.engine)

    def record_flows(self, deltas, now):

        hour = _hour(now)
        new = []

        with Session(self.engine) as session:

            known = {(k.source, k.asn_key) for k in session.scalars(select(PostureKnownRecord))}

            for d in deltas:

                row = session.scalars(select(PostureFlowRecord).where(
                    PostureFlowRecord.hour == hour, PostureFlowRecord.source == d["source"],
                    PostureFlowRecord.dest_ip == d["dest_ip"], PostureFlowRecord.dest_port == d["dest_port"],
                    PostureFlowRecord.proto == d["proto"])).first()

                if row is None:
                    row = PostureFlowRecord(hour=hour, source=d["source"], band=d["band"], dest_ip=d["dest_ip"],
                                            dest_port=d["dest_port"], proto=d["proto"], asn=d["asn"], org=d["org"],
                                            cc=d["cc"], bytes_out=0, bytes_in=0, conns=0)
                    session.add(row)

                row.bytes_out += d["bytes_out"]
                row.bytes_in += d["bytes_in"]
                row.conns += 1 if d["new_conn"] else 0

                key = asn_key(d["asn"], d["dest_ip"])
                seen = session.scalars(select(PostureSeenRecord).where(
                    PostureSeenRecord.source == d["source"], PostureSeenRecord.asn_key == key)).first()

                if seen is None:
                    session.add(PostureSeenRecord(source=d["source"], asn_key=key, org=d["org"], cc=d["cc"],
                                                  first_seen=now, last_seen=now))
                    session.flush()
                    if (d["source"], key) not in known:
                        new.append({"source": d["source"], "asn_key": key, "org": d["org"], "cc": d["cc"]})
                else:
                    seen.last_seen = now

            session.commit()

        return new

    def flows(self, since):
        with Session(self.engine) as session:
            rows = session.scalars(select(PostureFlowRecord).where(PostureFlowRecord.hour >= _hour(since)))
            return [_row(r, *FLOW_FIELDS) for r in rows]

    def seen(self):
        with Session(self.engine) as session:
            known = {(k.source, k.asn_key) for k in session.scalars(select(PostureKnownRecord))}
            return [{**_row(r, "source", "asn_key", "org", "cc", "first_seen", "last_seen"),
                     "known": (r.source, r.asn_key) in known}
                    for r in session.scalars(select(PostureSeenRecord))]

    def mark_known(self, source, key, note=""):

        if not (isinstance(source, str) and source.strip() and len(source) <= 128):
            return {"ok": False, "error": "source must be a container name"}

        if not (isinstance(key, str) and ASN_KEY.match(key)):
            return {"ok": False, "error": "asn_key must look like AS123 or ip:1.2.3.4"}

        with Session(self.engine) as session:
            exists = session.scalars(select(PostureKnownRecord).where(
                PostureKnownRecord.source == source, PostureKnownRecord.asn_key == key)).first()
            if exists is None:
                session.add(PostureKnownRecord(source=source, asn_key=key, note=str(note)[:500]))
                session.commit()

        return {"ok": True}

    def set_status(self, source, ok, detail, now):
        with Session(self.engine) as session:
            row = session.scalars(select(PostureStatusRecord).where(PostureStatusRecord.source == source)).first()
            if row is None:
                row = PostureStatusRecord(source=source, ok=ok, updated_at=now)
                session.add(row)
            row.ok, row.detail, row.updated_at = ok, json.dumps(detail), now
            session.commit()

    def statuses(self):
        with Session(self.engine) as session:
            return {r.source: {"ok": r.ok, "detail": json.loads(r.detail), "updated_at": r.updated_at}
                    for r in session.scalars(select(PostureStatusRecord))}

    def save_routes(self, routes, now):
        encoded = json.dumps(sorted(routes, key=lambda r: r["name"]), sort_keys=True)
        with Session(self.engine) as session:
            last = session.scalars(select(PostureRouteRecord).order_by(PostureRouteRecord.id.desc())).first()
            if last is not None and last.routes == encoded:
                return False
            session.add(PostureRouteRecord(snapshot_at=now, routes=encoded))
            session.commit()
            return True

    def latest_routes(self):
        with Session(self.engine) as session:
            last = session.scalars(select(PostureRouteRecord).order_by(PostureRouteRecord.id.desc())).first()
            return json.loads(last.routes) if last else []

    def prune(self, before):
        with Session(self.engine) as session:
            result = session.execute(delete(PostureFlowRecord).where(PostureFlowRecord.hour < _hour(before)))
            session.commit()
            return result.rowcount
```

Note: `save_routes` sorts by name and `latest_routes` returns that sorted list; callers must not rely on input order (the test uses one route).

In `tests/conftest.py`: import `atlas.posture.store as posture_store_module` next to the other store imports and add `monkeypatch.setattr(posture_store_module, "engine", engine)` inside `temp_db` after the existing three `setattr` lines.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_store.py tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite, then commit**

Run: `python -m pytest tests/ -q` → all pass.

```bash
git add atlas/config/models.py atlas/database/models.py atlas/posture/ tests/conftest.py tests/test_posture_store.py
git commit -m "feat(posture): config, tables and PostureStore"
```

---

### Task 2: conntrack collector

**Files:**
- Create: `atlas/posture/collectors/__init__.py` (docstring only), `atlas/posture/collectors/conntrack.py`
- Create: `tests/fixtures/posture/conntrack.txt`
- Test: `tests/test_posture_conntrack.py`

**Interfaces:**
- Produces: `Flow` frozen dataclass (`id: int|None, proto: str, state: str, src: str, dst: str, sport: int|None, dport: int|None, reply_src: str, reply_dst: str, bytes_out: int, bytes_in: int`); `parse_conntrack(text: str) -> list[Flow]`; `read_conntrack(run=subprocess.run) -> list[Flow]` (raises `RuntimeError` with stderr on failure).

- [ ] **Step 1: Add the sanitized fixture** (`tests/fixtures/posture/conntrack.txt` - shape copied from real cyberpac output 2026-10-08 with accounting on, IPs replaced):

```
ipv4     2 tcp      6 431999 ESTABLISHED src=100.64.0.10 dst=192.168.10.157 sport=62456 dport=443 packets=12 bytes=2048 src=172.18.0.9 dst=100.64.0.10 sport=443 dport=62456 packets=10 bytes=8192 [ASSURED] mark=0 use=1 id=1001
ipv4     2 tcp      6 431999 ESTABLISHED src=172.18.0.13 dst=203.0.113.75 sport=48088 dport=443 packets=40 bytes=5000 src=203.0.113.75 dst=192.168.10.157 sport=443 dport=48088 packets=90 bytes=120000 [ASSURED] mark=0 use=1 id=1002
ipv4     2 tcp      6 431993 ESTABLISHED src=192.168.10.157 dst=198.51.100.208 sport=43998 dport=443 packets=5 bytes=700 src=198.51.100.208 dst=192.168.10.157 sport=443 dport=43998 packets=6 bytes=900 [ASSURED] mark=0 use=1 id=1003
ipv4     2 udp      17 7 src=192.168.10.157 dst=192.168.10.1 sport=52500 dport=53 packets=1 bytes=70 src=192.168.10.1 dst=192.168.10.157 sport=53 dport=52500 packets=1 bytes=150 mark=0 use=1 id=1004
ipv4     2 udp      17 170 src=172.18.0.38 dst=198.51.100.44 sport=40000 dport=7844 packets=300 bytes=60000 src=198.51.100.44 dst=192.168.10.157 sport=7844 dport=40000 packets=280 bytes=90000 [ASSURED] mark=0 use=1 id=1005
ipv4     2 udp      17 175 src=172.18.0.3 dst=203.0.113.200 sport=51820 dport=51820 packets=900 bytes=800000 src=203.0.113.200 dst=192.168.10.157 sport=51820 dport=51820 packets=950 bytes=9000000 [ASSURED] mark=0 use=1 id=1006
ipv4     2 unknown  2 590 src=192.168.10.1 dst=224.0.0.1 packets=1 bytes=32 [UNREPLIED] src=224.0.0.1 dst=192.168.10.1 packets=0 bytes=0 mark=0 use=1 id=1007
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_posture_conntrack.py
import subprocess
from pathlib import Path

import pytest

from atlas.posture.collectors.conntrack import Flow, parse_conntrack, read_conntrack


SAMPLE = (Path(__file__).parent / "fixtures" / "posture" / "conntrack.txt").read_text()


def test_parses_tcp_tuple_bytes_and_id():
    flows = parse_conntrack(SAMPLE)
    first = flows[0]
    assert first == Flow(id=1001, proto="tcp", state="ESTABLISHED", src="100.64.0.10", dst="192.168.10.157",
                         sport=62456, dport=443, reply_src="172.18.0.9", reply_dst="100.64.0.10",
                         bytes_out=2048, bytes_in=8192)


def test_udp_has_no_state_and_unknown_proto_has_no_ports():
    flows = parse_conntrack(SAMPLE)
    udp = next(f for f in flows if f.id == 1004)
    assert (udp.proto, udp.state, udp.dport) == ("udp", "", 53)
    other = next(f for f in flows if f.id == 1007)
    assert (other.proto, other.sport, other.dport) == ("unknown", None, None)


def test_missing_accounting_means_zero_bytes():
    line = ("ipv4     2 tcp      6 10 ESTABLISHED src=10.0.0.1 dst=203.0.113.1 sport=1 dport=443 "
            "src=203.0.113.1 dst=10.0.0.1 sport=443 dport=1 [ASSURED] mark=0 use=1")
    (flow,) = parse_conntrack(line)
    assert (flow.bytes_out, flow.bytes_in, flow.id) == (0, 0, None)


def test_skips_summary_and_garbage_lines():
    text = SAMPLE + "conntrack v1.4.7 (conntrack-tools): 7 flow entries have been shown.\n\nnot a flow\n"
    assert len(parse_conntrack(text)) == 7


def test_read_conntrack_runs_extended_id_listing():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=SAMPLE, stderr="7 flow entries")

    assert len(read_conntrack(run=fake_run)) == 7
    assert calls == [["conntrack", "-L", "-o", "extended,id"]]


def test_read_conntrack_raises_with_stderr_on_failure():

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="Operation not permitted")

    with pytest.raises(RuntimeError, match="Operation not permitted"):
        read_conntrack(run=fake_run)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_conntrack.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement**

```python
# atlas/posture/collectors/conntrack.py
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
```

Note on the `orig`/`reply` split: conntrack prints the original tuple's keys first, then the same keys again for the reply tuple, so "first occurrence → orig, second → reply" is exact. `mark`/`use` only appear once and land in `orig`, which is harmless.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_conntrack.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add atlas/posture/collectors/ tests/fixtures/posture/conntrack.txt tests/test_posture_conntrack.py
git commit -m "feat(posture): conntrack collector"
```

---

### Task 3: ASN lookup (iptoasn, offline)

**Files:**
- Create: `atlas/posture/collectors/asn.py`
- Create: `tests/fixtures/posture/ip2asn-v4.tsv`
- Test: `tests/test_posture_asn.py`

**Interfaces:**
- Produces: `AsnInfo(asn: int, cc: str, org: str)`; `AsnTable(rows)` with `.lookup(ip: str) -> AsnInfo | None` and `len()`; `parse_ip2asn(lines) -> list[tuple[int,int,int,str,str]]`; `load_table(path) -> AsnTable` (empty table when the file is missing); `refresh(path, url, now, max_age=timedelta(days=7), get=requests.get) -> bool`.

- [ ] **Step 1: Add the fixture** (`tests/fixtures/posture/ip2asn-v4.tsv`, tab-separated: start, end, ASN, country, description - same format as iptoasn.com):

```
1.0.0.0	1.0.0.255	13335	US	CLOUDFLARENET
198.51.100.0	198.51.100.255	64501	NL	EXAMPLE-VPN
203.0.113.0	203.0.113.127	64500	US	EXAMPLE-NET
203.0.113.128	203.0.113.255	0	None	Not routed
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_posture_asn.py
import gzip
from datetime import datetime, timedelta
from pathlib import Path

from atlas.posture.collectors.asn import AsnInfo, AsnTable, load_table, parse_ip2asn, refresh


FIXTURE = Path(__file__).parent / "fixtures" / "posture" / "ip2asn-v4.tsv"


def test_lookup_finds_range_and_skips_unrouted():
    table = AsnTable(parse_ip2asn(FIXTURE.read_text().splitlines()))
    assert table.lookup("203.0.113.75") == AsnInfo(asn=64500, cc="US", org="EXAMPLE-NET")
    assert table.lookup("198.51.100.44") == AsnInfo(asn=64501, cc="NL", org="EXAMPLE-VPN")
    assert table.lookup("203.0.113.200") is None
    assert table.lookup("192.168.10.1") is None
    assert table.lookup("not-an-ip") is None
    assert len(table) == 3


def test_load_table_reads_gzip_and_tolerates_missing(tmp_path):
    path = tmp_path / "ip2asn-v4.tsv.gz"
    assert len(load_table(path)) == 0
    path.write_bytes(gzip.compress(FIXTURE.read_bytes()))
    assert load_table(path).lookup("1.0.0.1").org == "CLOUDFLARENET"


class FakeResponse:
    def __init__(self, content):
        self.content = content
    def raise_for_status(self):
        pass


def test_refresh_downloads_when_missing_or_stale_only(tmp_path):
    path = tmp_path / "inventory" / "ip2asn-v4.tsv.gz"
    calls = []
    get = lambda url, timeout: calls.append(url) or FakeResponse(gzip.compress(FIXTURE.read_bytes()))
    now = datetime.now()

    assert refresh(path, "https://example.test/a.gz", now, get=get) is True
    assert refresh(path, "https://example.test/a.gz", now, get=get) is False
    assert refresh(path, "https://example.test/a.gz", now + timedelta(days=8), get=get) is True
    assert len(calls) == 2 and load_table(path).lookup("1.0.0.1") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_asn.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement**

```python
# atlas/posture/collectors/asn.py
"""
IPv4 -> (ASN, country, organisation) from the free iptoasn.com table, looked up
locally (bisect over sorted ranges) so no destination IP ever leaves the host.
Refreshed at most weekly; a missing file just means unknown owners.
"""

import bisect
import gzip
import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests


@dataclass(frozen=True)
class AsnInfo:
    asn: int
    cc: str
    org: str


def parse_ip2asn(lines):

    rows = []

    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 5 or parts[2] == "0":
            continue
        try:
            start, end = int(ipaddress.IPv4Address(parts[0])), int(ipaddress.IPv4Address(parts[1]))
        except ValueError:
            continue
        rows.append((start, end, int(parts[2]), parts[3], parts[4]))

    return sorted(rows)


class AsnTable:

    def __init__(self, rows):
        self.rows = rows
        self.starts = [row[0] for row in rows]

    def __len__(self):
        return len(self.rows)

    def lookup(self, ip):
        try:
            value = int(ipaddress.IPv4Address(ip))
        except ValueError:
            return None
        index = bisect.bisect_right(self.starts, value) - 1
        if index < 0 or value > self.rows[index][1]:
            return None
        _, _, asn, cc, org = self.rows[index]
        return AsnInfo(asn=asn, cc=cc, org=org)


def load_table(path):
    path = Path(path)
    if not path.exists():
        return AsnTable([])
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        return AsnTable(parse_ip2asn(handle))


def refresh(path, url, now, max_age=timedelta(days=7), get=requests.get):

    path = Path(path)

    if path.exists() and now - datetime.fromtimestamp(path.stat().st_mtime) < max_age:
        return False

    response = get(url, timeout=60)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_asn.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add atlas/posture/collectors/asn.py tests/fixtures/posture/ip2asn-v4.tsv tests/test_posture_asn.py
git commit -m "feat(posture): offline ASN lookup from iptoasn"
```

---

### Task 4: Traefik routes (labels + file provider)

**Files:**
- Create: `atlas/posture/collectors/traefik.py`
- Test: `tests/test_posture_traefik.py`

**Interfaces:**
- Produces: `routes_from_labels(containers: list[dict], auth_middleware: str) -> list[dict]` where each container dict is `{"name": str, "labels": dict}`; `routes_from_files(directory: str|Path, auth_middleware: str) -> list[dict]`; `collect_routes(client, directory: str, auth_middleware: str) -> list[dict]`. Route dict keys: `name, hosts (list[str]), entrypoints (list[str]), protection ("authelia"|"public"), provider ("docker"|"file")`. A file-provider router pointing at `api@internal` (the Traefik dashboard) is a real public route and is kept.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_posture_traefik.py
from atlas.posture.collectors.traefik import collect_routes, routes_from_files, routes_from_labels


CONTAINERS = [
    {"name": "atlas", "labels": {
        "traefik.enable": "true",
        "traefik.http.routers.atlas.rule": "Host(`atlas.example.test`)",
        "traefik.http.routers.atlas.entrypoints": "websecure,tunnel",
        "traefik.http.routers.atlas.middlewares": "authelia@docker"}},
    {"name": "jellyfin", "labels": {
        "traefik.enable": "true",
        "traefik.http.routers.jellyfin.rule": "Host(`jellyfin.example.test`) || Host(`jf.example.test`)",
        "traefik.http.routers.jellyfin.entrypoints": "websecure"}},
    {"name": "hidden", "labels": {"traefik.http.routers.x.rule": "Host(`x.example.test`)"}},
    {"name": "plain", "labels": {}},
]


def test_routes_from_labels_reads_rule_entrypoints_and_protection():
    routes = routes_from_labels(CONTAINERS, "authelia")
    assert routes == [
        {"name": "atlas", "hosts": ["atlas.example.test"], "entrypoints": ["websecure", "tunnel"],
         "protection": "authelia", "provider": "docker"},
        {"name": "jellyfin", "hosts": ["jellyfin.example.test", "jf.example.test"], "entrypoints": ["websecure"],
         "protection": "public", "provider": "docker"},
    ]


def test_routes_from_files_reads_dynamic_yaml_and_skips_backups(tmp_path):
    (tmp_path / "immich.yml").write_text(
        "http:\n  routers:\n    immich:\n      rule: Host(`immich.example.test`)\n"
        "      entryPoints: [websecure, tunnel]\n      middlewares: [crowdsec@docker]\n"
        "    api:\n      rule: Host(`traefik.example.test`)\n      service: api@internal\n"
        "      middlewares: [authelia@docker]\n")
    (tmp_path / "immich.yml.bak-1").write_text("http: {routers: {old: {rule: 'Host(`old.example.test`)'}}}")
    (tmp_path / "tls.yml").write_text("tls:\n  options: {}\n")
    (tmp_path / "broken.yml").write_text(":\n  - [")
    routes = routes_from_files(tmp_path, "authelia")
    assert [r["name"] for r in routes] == ["api", "immich"]
    assert routes[1] == {"name": "immich", "hosts": ["immich.example.test"], "entrypoints": ["websecure", "tunnel"],
                         "protection": "public", "provider": "file"}
    assert routes[0]["protection"] == "authelia"


def test_routes_from_files_with_no_directory_is_empty():
    assert routes_from_files("", "authelia") == []


def test_collect_routes_merges_docker_and_files(tmp_path):
    (tmp_path / "a.yml").write_text("http:\n  routers:\n    a:\n      rule: Host(`a.example.test`)\n")

    class C:
        def __init__(self, name, labels):
            self.name, self.labels = name, labels

    class Client:
        class containers:
            @staticmethod
            def list():
                return [C(c["name"], c["labels"]) for c in CONTAINERS]

    names = [r["name"] for r in collect_routes(Client, str(tmp_path), "authelia")]
    assert names == ["a", "atlas", "jellyfin"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_traefik.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# atlas/posture/collectors/traefik.py
"""
Public routes as Traefik sees them, without needing Traefik's API: docker-label
routers (traefik.enable=true containers) plus file-provider routers from the
dynamic config directory (mounted read-only). A route whose middlewares include
the auth middleware (default "authelia") is "authelia"; anything else is
"public" (the app's own login, if any, is all that stands in front of it).
"""

import re
from pathlib import Path

import yaml


HOST = re.compile(r"Host\(([^)]*)\)")
ROUTER_LABEL = re.compile(r"^traefik\.http\.routers\.([^.]+)\.(rule|entrypoints|middlewares)$")


def _hosts(rule):
    return [host for group in HOST.findall(rule or "") for host in re.findall(r"`([^`]+)`", group)]


def _split(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _route(name, rule, entrypoints, middlewares, auth_middleware, provider):
    protected = any(m.split("@")[0].startswith(auth_middleware) for m in middlewares)
    return {"name": name, "hosts": _hosts(rule), "entrypoints": entrypoints,
            "protection": "authelia" if protected else "public", "provider": provider}


def routes_from_labels(containers, auth_middleware):

    routes = []

    for container in containers:
        labels = container.get("labels") or {}
        if labels.get("traefik.enable") != "true":
            continue
        routers = {}
        for key, value in labels.items():
            match = ROUTER_LABEL.match(key)
            if match:
                routers.setdefault(match.group(1), {})[match.group(2)] = value
        for name, fields in sorted(routers.items()):
            if "rule" not in fields:
                continue
            routes.append(_route(name, fields["rule"], _split(fields.get("entrypoints")),
                                 _split(fields.get("middlewares")), auth_middleware, "docker"))

    return routes


def routes_from_files(directory, auth_middleware):

    if not directory or not Path(directory).is_dir():
        return []

    routes = []

    for path in sorted(Path(directory).iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except (yaml.YAMLError, OSError):
            continue
        routers = ((data.get("http") or {}).get("routers") or {}) if isinstance(data, dict) else {}
        for name, fields in routers.items():
            if not isinstance(fields, dict) or "rule" not in fields:
                continue
            routes.append(_route(name, fields["rule"], _split(fields.get("entryPoints")),
                                 _split(fields.get("middlewares")), auth_middleware, "file"))

    return sorted(routes, key=lambda r: r["name"])


def collect_routes(client, directory, auth_middleware):
    containers = [{"name": c.name, "labels": c.labels or {}} for c in client.containers.list()]
    routes = routes_from_labels(containers, auth_middleware) + routes_from_files(directory, auth_middleware)
    return sorted(routes, key=lambda r: r["name"])
```


- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_traefik.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add atlas/posture/collectors/traefik.py tests/test_posture_traefik.py
git commit -m "feat(posture): traefik routes from labels and file provider"
```

---

### Task 5: gluetun, CrowdSec, public IP, container IPs

**Files:**
- Create: `atlas/posture/collectors/services.py`
- Create: `tests/posture_fakes.py` (Docker/HTTP test doubles reused by Task 7; `tests/` has no `__init__.py`, so pytest's default import mode puts `tests/` on `sys.path` and `import posture_fakes` works)
- Test: `tests/test_posture_services.py`

**Interfaces:**
- Produces:
  - `container_ips(client) -> dict[str, str]` - every bridge IP → container name (containers sharing another's network namespace contribute nothing; they are handled by `vpn_members`).
  - `vpn_members(client, gluetun_name: str) -> list[str]` - names of containers whose `HostConfig.NetworkMode` is `container:<gluetun id or name>`.
  - `container_ip(client, name: str) -> str | None`.
  - `gluetun_status(base_url: str, api_key: str, get=requests.get) -> dict` → `{"ok": True, "exit_ip": str, "country": str}` or `{"ok": False, "error": str}`.
  - `crowdsec_bans(base_url: str, api_key: str, get=requests.get) -> dict` → `{"ok": True, "active": int}` or error dict.
  - `public_ip(url: str, get=requests.get) -> dict` → `{"ok": True, "ip": str}` or error dict.

- [ ] **Step 1: Write the failing tests**

```python
# tests/posture_fakes.py
import requests


class Response:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text
    def json(self):
        return self._data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class Container:
    def __init__(self, name, cid, mode, networks):
        self.name, self.id = name, cid
        self.attrs = {"HostConfig": {"NetworkMode": mode},
                      "NetworkSettings": {"Networks": {n: {"IPAddress": ip} for n, ip in networks.items()}}}


class Client:
    def __init__(self, items):
        self.items = items
        outer = self
        class containers:
            @staticmethod
            def list():
                return outer.items
            @staticmethod
            def get(name):
                return next(c for c in outer.items if c.name == name)
        self.containers = containers


def make_client(extra=()):
    items = [
        Container("gluetun", "abc123", "stack_default", {"stack_default": "172.18.0.3"}),
        Container("qbittorrent", "q1", "container:abc123", {}),
        Container("sonarr", "s1", "stack_default", {"stack_default": "172.18.0.13", "other": ""}),
        Container("atlas-scan", "a1", "host", {"host": ""}),
        *extra,
    ]
    for item in items:
        item.labels = {}
    return Client(items)
```

```python
# tests/test_posture_services.py
import requests

from atlas.posture.collectors.services import (container_ip, container_ips, crowdsec_bans, gluetun_status,
                                               public_ip, vpn_members)
from posture_fakes import Response, make_client


CLIENT = make_client()


def test_container_ips_maps_bridge_ips_only():
    assert container_ips(CLIENT) == {"172.18.0.3": "gluetun", "172.18.0.13": "sonarr"}
    assert container_ip(CLIENT, "sonarr") == "172.18.0.13"


def test_vpn_members_by_id_or_name():
    assert vpn_members(CLIENT, "gluetun") == ["qbittorrent"]


def test_gluetun_status_sends_key_and_parses():
    seen = {}
    def get(url, headers, timeout):
        seen.update(url=url, headers=headers)
        return Response(data={"public_ip": "198.51.100.9", "country": "Netherlands"})
    assert gluetun_status("http://172.18.0.3:8000", "k", get=get) == {
        "ok": True, "exit_ip": "198.51.100.9", "country": "Netherlands"}
    assert seen == {"url": "http://172.18.0.3:8000/v1/publicip/ip", "headers": {"X-API-Key": "k"}}


def test_gluetun_status_reports_errors_without_raising():
    def get(url, headers, timeout):
        raise requests.ConnectionError("refused")
    result = gluetun_status("http://x", "k", get=get)
    assert result["ok"] is False and "refused" in result["error"]
    assert gluetun_status("http://x", "k", get=lambda url, headers, timeout: Response(401))["ok"] is False


def test_crowdsec_counts_active_decisions_including_null():
    def get(url, headers, timeout):
        assert url == "http://172.18.0.7:8080/v1/decisions" and headers == {"X-Api-Key": "b"}
        return Response(data=[{"value": "203.0.113.5"}, {"value": "203.0.113.6"}])
    assert crowdsec_bans("http://172.18.0.7:8080", "b", get=get) == {"ok": True, "active": 2}
    assert crowdsec_bans("http://x", "b", get=lambda url, headers, timeout: Response(data=None)) == {
        "ok": True, "active": 0}


def test_public_ip_strips_and_validates():
    assert public_ip("https://ip.example.test", get=lambda url, timeout: Response(text=" 192.0.2.10\n")) == {
        "ok": True, "ip": "192.0.2.10"}
    assert public_ip("https://ip.example.test", get=lambda url, timeout: Response(text="<html>"))["ok"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_services.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# atlas/posture/collectors/services.py
"""
Small HTTP/Docker lookups for the posture collector. The collector runs with
host networking, where Docker DNS names don't resolve, so service URLs are
built from each container's current bridge IP (looked up per run - IPs change
when containers are recreated). Every function returns a result dict and never
raises; failures become {"ok": False, "error": ...}.
"""

import ipaddress

import requests


def _networks(container):
    return (container.attrs.get("NetworkSettings") or {}).get("Networks") or {}


def container_ips(client):
    return {net["IPAddress"]: c.name for c in client.containers.list()
            for net in _networks(c).values() if net.get("IPAddress")}


def container_ip(client, name):
    try:
        container = client.containers.get(name)
    except Exception:
        return None
    return next((net["IPAddress"] for net in _networks(container).values() if net.get("IPAddress")), None)


def vpn_members(client, gluetun_name):
    try:
        gluetun = client.containers.get(gluetun_name)
    except Exception:
        return []
    targets = {f"container:{gluetun.id}", f"container:{gluetun_name}"}
    return [c.name for c in client.containers.list()
            if (c.attrs.get("HostConfig") or {}).get("NetworkMode") in targets]


def _fail(error):
    return {"ok": False, "error": str(error)[:300]}


def gluetun_status(base_url, api_key, get=requests.get):
    try:
        response = get(f"{base_url}/v1/publicip/ip", headers={"X-API-Key": api_key}, timeout=5)
        response.raise_for_status()
        data = response.json() or {}
        return {"ok": bool(data.get("public_ip")), "exit_ip": data.get("public_ip", ""),
                "country": data.get("country", "")}
    except (requests.RequestException, ValueError) as error:
        return _fail(error)


def crowdsec_bans(base_url, api_key, get=requests.get):
    try:
        response = get(f"{base_url}/v1/decisions", headers={"X-Api-Key": api_key}, timeout=5)
        response.raise_for_status()
        return {"ok": True, "active": len(response.json() or [])}
    except (requests.RequestException, ValueError) as error:
        return _fail(error)


def public_ip(url, get=requests.get):
    try:
        response = get(url, timeout=5)
        response.raise_for_status()
        ip = response.text.strip()
        ipaddress.ip_address(ip)
        return {"ok": True, "ip": ip}
    except (requests.RequestException, ValueError) as error:
        return _fail(error)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_services.py -v`
Expected: PASS

- [ ] **Step 5: Full suite + commit (end of PR 1)**

Run: `python -m pytest tests/ -q` → all pass.

```bash
git add atlas/posture/collectors/services.py tests/posture_fakes.py tests/test_posture_services.py
git commit -m "feat(posture): gluetun, crowdsec, public ip and container lookups"
```

Open PR 1 (`gh pr create --base main --title "posture: collectors + storage" --body ...`), wait for `gh pr checks` green; the user merges.

---

## PR 2 - aggregation, collector loop, API

### Task 6: Accountant (deltas + classification)

**Files:**
- Create: `atlas/posture/aggregate.py`
- Test: `tests/test_posture_aggregate.py`

**Interfaces:**
- Consumes: `Flow` (Task 2), `AsnTable.lookup` (Task 3).
- Produces:
  - `is_public(ip: str) -> bool` (global unicast, not CGNAT/private/loopback/multicast).
  - `Accountant()` with `.deltas(flows, sources: dict[str,str], host_ip: str, vpn_sources: set[str], asn) -> list[dict]` (dicts exactly as `PostureStore.record_flows` expects; `asn` is an `AsnTable`).
  - `inbound_counts(flows, host_ip: str, traefik_ip: str|None) -> dict` → `{"public": int, "private": int}` (connections to ports 80/443 on the host or Traefik).
  - `tunnel_connections(flows, cloudflared_ip: str|None) -> int` (flows from cloudflared to port 7844).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_posture_aggregate.py
from pathlib import Path

from atlas.posture.aggregate import Accountant, inbound_counts, is_public, tunnel_connections
from atlas.posture.collectors.asn import AsnTable, parse_ip2asn
from atlas.posture.collectors.conntrack import parse_conntrack


FIX = Path(__file__).parent / "fixtures" / "posture"
FLOWS = parse_conntrack((FIX / "conntrack.txt").read_text())
ASN = AsnTable(parse_ip2asn((FIX / "ip2asn-v4.tsv").read_text().splitlines()))
SOURCES = {"172.18.0.13": "sonarr", "172.18.0.3": "gluetun", "172.18.0.38": "cloudflared", "172.18.0.9": "traefik"}
HOST = "192.168.10.157"


def test_is_public():
    assert is_public("203.0.113.1") is False   # documentation range is not global
    assert is_public("8.8.8.8") is True
    assert is_public("100.64.0.10") is False and is_public("192.168.10.1") is False


def test_first_pass_counts_outbound_flows_with_owner_and_band(monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: not ip.startswith(("192.168.", "172.", "100.64.", "224.")))
    deltas = Accountant().deltas(FLOWS, SOURCES, HOST, {"gluetun"}, ASN)
    by_source = {d["source"]: d for d in deltas}
    assert set(by_source) == {"sonarr", "host", "cloudflared", "gluetun"}
    sonarr = by_source["sonarr"]
    assert (sonarr["band"], sonarr["dest_ip"], sonarr["dest_port"], sonarr["asn"], sonarr["org"]) == (
        "direct", "203.0.113.75", 443, 64500, "EXAMPLE-NET")
    assert (sonarr["bytes_out"], sonarr["bytes_in"], sonarr["new_conn"]) == (5000, 120000, True)
    assert by_source["gluetun"]["band"] == "vpn"


def test_second_pass_counts_only_growth_and_forgets_closed(monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: not ip.startswith(("192.168.", "172.", "100.64.", "224.")))
    acct = Accountant()
    acct.deltas(FLOWS, SOURCES, HOST, set(), ASN)
    grown = [f.__class__(**{**f.__dict__, "bytes_out": f.bytes_out + 10}) if f.id == 1002 else f for f in FLOWS]
    deltas = acct.deltas(grown, SOURCES, HOST, set(), ASN)
    assert [(d["source"], d["bytes_out"], d["bytes_in"], d["new_conn"]) for d in deltas] == [("sonarr", 10, 0, False)]
    assert acct.deltas([], SOURCES, HOST, set(), ASN) == []
    assert len(acct.deltas(grown, SOURCES, HOST, set(), ASN)) == 4   # reopened ids count as new again


def test_counter_reset_counts_full_value(monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: ip.startswith("203."))
    acct = Accountant()
    acct.deltas(FLOWS, SOURCES, HOST, set(), ASN)
    shrunk = [f.__class__(**{**f.__dict__, "bytes_out": 1, "bytes_in": 2}) for f in FLOWS if f.id == 1002]
    (d,) = acct.deltas(shrunk, SOURCES, HOST, set(), ASN)
    assert (d["bytes_out"], d["bytes_in"]) == (1, 2)


def test_inbound_and_tunnel_counts(monkeypatch):
    assert inbound_counts(FLOWS, HOST, "172.18.0.9") == {"public": 0, "private": 1}
    assert tunnel_connections(FLOWS, "172.18.0.38") == 1
    assert tunnel_connections(FLOWS, None) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_aggregate.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# atlas/posture/aggregate.py
"""
Turns conntrack snapshots into per-poll deltas. conntrack byte counters are
cumulative per connection, so the Accountant remembers the last counters per
connection key and emits only the growth; a connection seen for the first time
counts in full (including after an atlas restart - a bounded over-count that is
documented rather than worked around). Only outbound flows to public addresses
are kept: source = the container that owns the original source IP (or "host"),
band = "vpn" for containers routed through gluetun, else "direct".
"""

import ipaddress


CGNAT = ipaddress.ip_network("100.64.0.0/10")


def is_public(ip):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return address.is_global and address not in CGNAT and not address.is_multicast


def _key(flow):
    return flow.id if flow.id is not None else (flow.proto, flow.src, flow.sport, flow.dst, flow.dport)


class Accountant:

    def __init__(self):
        self.last = {}

    def deltas(self, flows, sources, host_ip, vpn_sources, asn):

        current, out = {}, []

        for flow in flows:

            source = sources.get(flow.src) or ("host" if flow.src == host_ip else None)
            if source is None or not is_public(flow.dst):
                continue

            key = _key(flow)
            current[key] = (flow.bytes_out, flow.bytes_in)
            previous = self.last.get(key)

            if previous and flow.bytes_out >= previous[0] and flow.bytes_in >= previous[1]:
                bytes_out, bytes_in, new_conn = flow.bytes_out - previous[0], flow.bytes_in - previous[1], False
            else:
                bytes_out, bytes_in, new_conn = flow.bytes_out, flow.bytes_in, previous is None

            if not (bytes_out or bytes_in or new_conn):
                continue

            info = asn.lookup(flow.dst)
            out.append({"source": source, "band": "vpn" if source in vpn_sources else "direct",
                        "dest_ip": flow.dst, "dest_port": flow.dport or 0, "proto": flow.proto,
                        "asn": info.asn if info else 0, "org": info.org if info else "",
                        "cc": info.cc if info else "", "bytes_out": bytes_out, "bytes_in": bytes_in,
                        "new_conn": new_conn})

        self.last = current
        return out


def inbound_counts(flows, host_ip, traefik_ip):

    counts = {"public": 0, "private": 0}

    for flow in flows:
        if flow.dport in (80, 443) and flow.dst in (host_ip, traefik_ip):
            counts["public" if is_public(flow.src) else "private"] += 1

    return counts


def tunnel_connections(flows, cloudflared_ip):
    return sum(1 for f in flows if cloudflared_ip and f.src == cloudflared_ip and f.dport == 7844)
```

Note: `test_counter_reset_counts_full_value` expects `new_conn` False there (the key existed); the dict asserted only checks bytes, which is the point.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_aggregate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add atlas/posture/aggregate.py tests/test_posture_aggregate.py
git commit -m "feat(posture): accountant turns conntrack counters into deltas"
```

---

### Task 7: collect_once + `atlas posture watch` + image/compose

**Files:**
- Create: `atlas/posture/collect.py`
- Modify: `atlas/cli/main.py` (new `posture_app` sub-app, mounted like `proxmox_app`)
- Modify: `Dockerfile`, `docker-compose.yml`
- Test: `tests/test_posture_collect.py`, extend `tests/test_compose.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces:
  - `Collector(settings: PostureConfig, store: PostureStore, client, read_flows=read_conntrack, get=requests.get, asn_table=None)` with `.run_once(now: datetime) -> dict` returning `{"flows": int, "deltas": int, "new": list[dict]}`.
  - Status sources written each run (exact names the model relies on): `conntrack`, `tunnel`, `inbound`, `routes`, `gluetun`, `public_ip`, `crowdsec`, `asn`.
  - CLI: `atlas posture watch [--once] [--json]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_posture_collect.py
from datetime import datetime, timedelta
from pathlib import Path

from atlas.config.models import PostureConfig
from atlas.posture.collect import Collector
from atlas.posture.collectors.asn import AsnTable, parse_ip2asn
from atlas.posture.collectors.conntrack import parse_conntrack
from atlas.posture.store import PostureStore
from posture_fakes import Container, Response, make_client


FIX = Path(__file__).parent / "fixtures" / "posture"
NOW = datetime(2026, 10, 8, 13, 0, 0)


def client():
    return make_client([Container("cloudflared", "c1", "stack_default", {"stack_default": "172.18.0.38"}),
                        Container("traefik", "t1", "stack_default", {"stack_default": "172.18.0.9"}),
                        Container("crowdsec", "cs", "stack_default", {"stack_default": "172.18.0.7"})])


def fake_get(url, headers=None, timeout=None):
    if url.endswith("/v1/publicip/ip"):
        return Response(data={"public_ip": "198.51.100.9", "country": "NL"})
    if url.endswith("/v1/decisions"):
        return Response(data=[{"value": "203.0.113.5"}])
    return Response(text="192.0.2.10")


def make(temp_db, read=None):
    settings = PostureConfig(enabled=True, host_ip="192.168.10.157", gluetun_api_key="g", crowdsec_api_key="c")
    flows = parse_conntrack((FIX / "conntrack.txt").read_text())
    table = AsnTable(parse_ip2asn((FIX / "ip2asn-v4.tsv").read_text().splitlines()))
    return Collector(settings, PostureStore(temp_db), client(), read_flows=read or (lambda: flows),
                     get=fake_get, asn_table=table)


def test_run_once_records_statuses_and_flows(temp_db, monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: ip.startswith(("203.", "198.")))
    collector = make(temp_db)
    result = collector.run_once(NOW)
    statuses = collector.store.statuses()
    assert {"conntrack", "tunnel", "inbound", "routes", "gluetun", "public_ip", "crowdsec", "asn"} <= set(statuses)
    assert statuses["tunnel"]["detail"] == {"connections": 1}
    assert statuses["gluetun"]["detail"]["exit_ip"] == "198.51.100.9"
    assert statuses["public_ip"]["detail"] == {"ip": "192.0.2.10"}
    assert statuses["crowdsec"]["detail"] == {"active": 1}
    assert result["deltas"] == 4 and {n["source"] for n in result["new"]} == {"sonarr", "host", "cloudflared", "gluetun"}


def test_conntrack_failure_is_recorded_not_raised(temp_db):
    def broken():
        raise RuntimeError("Operation not permitted")
    collector = make(temp_db, read=broken)
    collector.run_once(NOW)
    status = collector.store.statuses()["conntrack"]
    assert status["ok"] is False and "not permitted" in status["detail"]["error"]


def test_public_ip_is_fetched_at_most_every_10_minutes(temp_db):
    calls = []
    collector = make(temp_db)
    collector.get = lambda url, headers=None, timeout=None: calls.append(url) or fake_get(url, headers, timeout)
    collector.run_once(NOW)
    collector.run_once(NOW + timedelta(minutes=5))
    collector.run_once(NOW + timedelta(minutes=11))
    assert sum(url == "https://api.ipify.org" for url in calls) == 2


def test_missing_keys_mark_sources_unconfigured(temp_db):
    collector = make(temp_db)
    collector.settings = PostureConfig(enabled=True, host_ip="192.168.10.157")
    collector.run_once(NOW)
    assert collector.store.statuses()["gluetun"]["detail"] == {"error": "not configured (posture.gluetun_api_key)"}
```

Extend `tests/test_compose.py` with:

```python
def test_atlas_scan_runs_posture_watch_with_net_admin():
    import yaml
    data = yaml.safe_load(open("docker-compose.yml"))
    scan = data["services"]["atlas-scan"]
    assert "NET_ADMIN" in scan["cap_add"]
    assert "atlas posture watch" in "\n".join(scan["command"])
```

(If `tests/test_compose.py` reads the compose file with a helper or fixture already, reuse it instead of `open(...)`; it runs from the repo root via `isolated_cwd`-free tests - check the existing tests there first and copy their loading pattern.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_collect.py tests/test_compose.py -v`
Expected: FAIL (`ModuleNotFoundError` / missing `cap_add`)

- [ ] **Step 3: Implement `atlas/posture/collect.py`**

```python
# atlas/posture/collect.py
"""
One posture poll: read the connection table, account deltas into hourly
buckets, refresh routes/tunnel/inbound counts, and query gluetun, CrowdSec and
the public-IP echo. Each source's outcome lands in posture_status, so the page
can grey out exactly the part that is stale; nothing here raises.
"""

from datetime import timedelta
from pathlib import Path

import requests

from atlas.posture.aggregate import Accountant, inbound_counts, tunnel_connections
from atlas.posture.collectors.asn import load_table, refresh
from atlas.posture.collectors.conntrack import read_conntrack
from atlas.posture.collectors.services import (container_ip, container_ips, crowdsec_bans, gluetun_status,
                                               public_ip, vpn_members)
from atlas.posture.collectors.traefik import collect_routes


PUBLIC_IP_EVERY = timedelta(minutes=10)
ASN_CHECK_EVERY = timedelta(hours=24)
PRUNE_EVERY = timedelta(hours=1)


class Collector:

    def __init__(self, settings, store, client, read_flows=read_conntrack, get=requests.get, asn_table=None):
        self.settings, self.store, self.client = settings, store, client
        self.read_flows, self.get = read_flows, get
        self.accountant = Accountant()
        self.asn_table = asn_table
        self.last_public_ip = None
        self.last_asn_check = None
        self.last_prune = None

    def _status(self, source, result, now):
        ok = bool(result.get("ok"))
        self.store.set_status(source, ok, {k: v for k, v in result.items() if k != "ok"}, now)
        return ok

    def _asn(self, now):
        self.last_asn_check = now
        try:
            refresh(Path(self.settings.asn_path), self.settings.asn_url, now, get=self.get)
            self.asn_table = load_table(self.settings.asn_path)
            self._status("asn", {"ok": len(self.asn_table) > 0, "ranges": len(self.asn_table)}, now)
        except Exception as error:
            self.asn_table = self.asn_table or load_table(self.settings.asn_path)
            self._status("asn", {"ok": False, "error": str(error)[:300]}, now)

    def _service(self, source, container, port, key_field, call, now):
        key = getattr(self.settings, key_field)
        if not key:
            return self._status(source, {"ok": False, "error": f"not configured (posture.{key_field})"}, now)
        ip = container_ip(self.client, container)
        if not ip:
            return self._status(source, {"ok": False, "error": f"container {container} not found"}, now)
        return self._status(source, call(f"http://{ip}:{port}", key, get=self.get), now)

    def run_once(self, now):

        s = self.settings

        if self.last_asn_check is None and self.asn_table is not None:
            # A table handed in (tests, or a caller that loaded it) is used as-is until the next daily check.
            self.last_asn_check = now
            self._status("asn", {"ok": len(self.asn_table) > 0, "ranges": len(self.asn_table)}, now)
        elif self.last_asn_check is None or now - self.last_asn_check >= ASN_CHECK_EVERY:
            self._asn(now)

        sources = container_ips(self.client)
        cloudflared_ip = container_ip(self.client, s.cloudflared_container)
        traefik_ip = container_ip(self.client, s.traefik_container)
        vpn = {s.gluetun_container, *vpn_members(self.client, s.gluetun_container)}

        result = {"flows": 0, "deltas": 0, "new": []}

        try:
            flows = self.read_flows()
            self._status("conntrack", {"ok": True, "flows": len(flows)}, now)
        except Exception as error:
            flows = []
            self._status("conntrack", {"ok": False, "error": str(error)[:300]}, now)

        if flows:
            deltas = self.accountant.deltas(flows, sources, s.host_ip, vpn, self.asn_table)
            result.update(flows=len(flows), deltas=len(deltas), new=self.store.record_flows(deltas, now))

        tunnel = tunnel_connections(flows, cloudflared_ip)
        self._status("tunnel", {"ok": tunnel > 0, "connections": tunnel}, now)
        self._status("inbound", {"ok": bool(flows), **inbound_counts(flows, s.host_ip, traefik_ip)}, now)

        try:
            routes = collect_routes(self.client, s.traefik_dynamic_dir, s.auth_middleware)
            self.store.save_routes(routes, now)
            self._status("routes", {"ok": True, "count": len(routes)}, now)
        except Exception as error:
            self._status("routes", {"ok": False, "error": str(error)[:300]}, now)

        self._service("gluetun", s.gluetun_container, s.gluetun_port, "gluetun_api_key", gluetun_status, now)
        self._service("crowdsec", s.crowdsec_container, s.crowdsec_port, "crowdsec_api_key", crowdsec_bans, now)

        if self.last_public_ip is None or now - self.last_public_ip >= PUBLIC_IP_EVERY:
            self.last_public_ip = now
            self._status("public_ip", public_ip(s.ip_echo_url, get=self.get), now)

        if self.last_prune is None or now - self.last_prune >= PRUNE_EVERY:
            self.last_prune = now
            self.store.prune(now - timedelta(days=s.retention_days))

        return result
```

`fake_get` accepts `headers=None` because `public_ip` calls `get(url, timeout=5)` while gluetun/CrowdSec pass headers.

- [ ] **Step 4: Add the CLI command** in `atlas/cli/main.py`, next to the other sub-apps (create `posture_app = typer.Typer(help="Egress/posture collector")` near `proxmox_app` and mount it with `app.add_typer(posture_app, name="posture")` beside the existing `add_typer` calls):

```python
@posture_app.command("watch")
def posture_watch(
    once: bool = typer.Option(False, "--once", help="Collect a single sample and exit"),
    json_output: bool = typer.Option(False, "--json", help="Print each sample's result as JSON")
):
    """
    Poll the connection table, routes, tunnel, VPN and CrowdSec every
    posture.interval seconds for the posture page. Runs in the atlas-scan
    container; needs NET_ADMIN for conntrack (read-only listing).
    """

    import time
    from datetime import datetime

    from atlas.docker.manager import get_client
    from atlas.posture.collect import Collector
    from atlas.posture.store import PostureStore

    settings = load_config()

    if not settings.posture.enabled:
        console.print("Posture collection is off (posture.enabled: false in atlas.yaml).")
        return

    client = get_client()

    if client is None:
        console.print("[red]Docker is unavailable - posture needs the Docker socket.[/red]")
        raise typer.Exit(1)

    collector = Collector(settings.posture, PostureStore(), client)

    while True:
        result = collector.run_once(datetime.utcnow())
        if json_output:
            print(json.dumps(result, default=str))
        elif result["new"]:
            for item in result["new"]:
                console.print(f"new destination: {item['source']} -> {item['asn_key']} {item['org']} {item['cc']}")
        if once:
            return
        time.sleep(settings.posture.interval)
```

(Check `get_client`'s real name/signature in `atlas/docker/manager.py` first - the plan assumes `get_client()` returns a client or `None`, as documented in CLAUDE.md.)

- [ ] **Step 5: Image + compose**

`Dockerfile` - after `WORKDIR /app` and before `COPY`, add:

```dockerfile
# conntrack lists the kernel connection table for the posture page. The file
# capability lets the non-root atlas user use NET_ADMIN (granted only to the
# atlas-scan service via cap_add) without running as root.
RUN apt-get update \
    && apt-get install -y --no-install-recommends conntrack libcap2-bin \
    && setcap cap_net_admin+ep /usr/sbin/conntrack \
    && rm -rf /var/lib/apt/lists/*
```

`docker-compose.yml` `atlas-scan` service: add

```yaml
    cap_add:
      - NET_ADMIN   # conntrack -L only (posture page); atlas never writes netfilter state
```

and change the command so the watch loop runs alongside the scan loop:

```yaml
    command:
      - sh
      - -c
      - |
        atlas posture watch &
        while :; do
          atlas scan
          atlas discover >/dev/null 2>&1
          atlas proxmox scan >/dev/null 2>&1
          atlas map >/dev/null 2>&1 && echo "$$(date -u +%FT%TZ) map refreshed"
          sleep "$${ATLAS_SCAN_MINUTES:-15}m"
        done
```

Update the comment above `atlas-scan` ("it needs no extra capabilities") to say it needs `NET_ADMIN` only for the posture collector's read-only conntrack listing.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_collect.py tests/test_compose.py tests/test_cli_smoke.py -v`
Expected: PASS

- [ ] **Step 7: Build the image locally to prove setcap works**

Run: `docker build -t atlas:posture-test . && docker run --rm --cap-add NET_ADMIN --net host --user 10001 atlas:posture-test conntrack -L -o extended,id | head -3`
Expected: conntrack lines (not "Operation not permitted"). Without `--cap-add NET_ADMIN` it must fail - that's the boundary working.

- [ ] **Step 8: Commit**

```bash
git add atlas/posture/collect.py atlas/cli/main.py Dockerfile docker-compose.yml tests/test_posture_collect.py tests/test_compose.py
git commit -m "feat(posture): collector loop (atlas posture watch) in atlas-scan"
```

---

### Task 8: Posture model + API

**Files:**
- Create: `atlas/posture/model.py`
- Modify: `atlas/web/api.py` (GET `/api/posture`, GET `/api/posture/node`, POST `/api/posture/known`)
- Test: `tests/test_posture_model.py`, extend `tests/test_web_api.py`

**Interfaces:**
- Consumes: `PostureStore` (Task 1) and the status source names from Task 7.
- Produces:
  - `build_posture(store, now: datetime, window: str = "24h") -> dict` with keys:
    - `strip`: list of 5 dicts `{"key","label","value","detail","state"}` where `key` ∈ `ingress, vpn, exposure, blocked, new` and `state` ∈ `ok, warn, review, unknown`.
    - `nodes`: list of `{"id","label","sub","band","state","x","y","w"}`; `edges`: list of `{"id","source","target","bytes","state"}`.
    - `bands`: list of `{"id","label","y","h","stale"}` for `inbound`, `direct`, `vpn`.
    - `exposure`: list of route dicts (Task 4 shape).
    - `review`: list of unreviewed new destinations `{"source","asn_key","org","cc","first_seen"}` (first seen within 7 days).
    - `generated_at`: ISO string.
  - `node_details(store, node_id: str, now: datetime, resolve=_reverse_dns) -> dict | None`.
  - `WINDOWS = {"live": timedelta(minutes=0), "1h": timedelta(hours=1), "24h": timedelta(hours=24)}` (`live` = the current hour bucket).
  - Node id scheme (UI relies on it): inbound `in:internet`, `in:cloudflare`, `in:tunnel`, `in:traefik`, `in:auth`, `in:svc-auth`, `in:svc-public`; direct `src:<name>`, `out:router`, `dst:<asn_key>`, `dst:others`; vpn `vpn:members`, `vpn:gluetun`, `vpn:exit`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_posture_model.py
from datetime import datetime, timedelta

from atlas.posture.model import build_posture, node_details
from atlas.posture.store import PostureStore


NOW = datetime(2026, 10, 8, 13, 42, 0)


def seed(store):
    d = lambda **o: {**{"source": "sonarr", "band": "direct", "dest_ip": "203.0.113.75", "dest_port": 443,
                       "proto": "tcp", "asn": 64500, "org": "EXAMPLE-NET", "cc": "US", "bytes_out": 5000,
                       "bytes_in": 120000, "new_conn": True}, **o}
    store.record_flows([d(), d(source="jellyfin", dest_ip="198.51.100.10", asn=64501, org="EXAMPLE-CDN",
                            bytes_in=10, bytes_out=900000),
                        d(source="gluetun", band="vpn", dest_ip="198.51.100.44", asn=64502, org="EXAMPLE-VPN",
                          bytes_out=800000, bytes_in=9000000)], NOW - timedelta(minutes=10))
    store.mark_known("jellyfin", "AS64501")
    store.set_status("tunnel", True, {"connections": 4}, NOW)
    store.set_status("gluetun", True, {"exit_ip": "198.51.100.9", "country": "NL"}, NOW)
    store.set_status("public_ip", True, {"ip": "192.0.2.10"}, NOW)
    store.set_status("crowdsec", True, {"active": 37}, NOW)
    store.set_status("conntrack", True, {"flows": 330}, NOW)
    store.save_routes([
        {"name": "atlas", "hosts": ["atlas.example.test"], "entrypoints": ["tunnel"], "protection": "authelia", "provider": "docker"},
        {"name": "jellyfin", "hosts": ["jellyfin.example.test"], "entrypoints": ["tunnel"], "protection": "public", "provider": "docker"},
    ], NOW)


def strip(result):
    return {item["key"]: item for item in result["strip"]}


def test_strip_states(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    s = strip(build_posture(store, NOW))
    assert (s["ingress"]["state"], s["ingress"]["value"]) == ("ok", "Tunnel up")
    assert (s["vpn"]["state"], s["vpn"]["value"]) == ("ok", "Verified")
    assert (s["exposure"]["value"], s["exposure"]["detail"]) == ("2 routes", "1 without Authelia")
    assert s["blocked"]["value"] == "37"
    assert (s["new"]["state"], s["new"]["value"]) == ("review", "2")   # sonarr + gluetun; jellyfin marked known


def test_vpn_leak_and_unknown(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    store.set_status("gluetun", True, {"exit_ip": "192.0.2.10", "country": "US"}, NOW)
    assert strip(build_posture(store, NOW))["vpn"]["state"] == "warn"
    store.set_status("gluetun", False, {"error": "timeout"}, NOW)
    assert strip(build_posture(store, NOW))["vpn"]["state"] == "unknown"


def test_nodes_edges_and_bands(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    result = build_posture(store, NOW)
    ids = {n["id"] for n in result["nodes"]}
    assert {"in:internet", "in:tunnel", "in:traefik", "src:sonarr", "src:jellyfin", "out:router",
            "dst:AS64500", "dst:AS64501", "vpn:gluetun", "vpn:exit"} <= ids
    assert "src:gluetun" not in ids
    new_edge = next(e for e in result["edges"] if e["target"] == "dst:AS64500")
    assert new_edge["state"] == "review" and new_edge["bytes"] == 125000
    assert next(e for e in result["edges"] if e["target"] == "dst:AS64501")["state"] == "ok"
    assert [b["id"] for b in result["bands"]] == ["inbound", "direct", "vpn"]
    assert all(isinstance(n["x"], int) and isinstance(n["y"], int) for n in result["nodes"])


def test_stale_sources_grey_out_bands(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    store.set_status("conntrack", False, {"error": "Operation not permitted"}, NOW)
    bands = {b["id"]: b for b in build_posture(store, NOW)["bands"]}
    assert bands["direct"]["stale"] and not bands["inbound"]["stale"]


def test_window_live_uses_current_hour_only(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    old = NOW - timedelta(hours=3)
    store.record_flows([{"source": "radarr", "band": "direct", "dest_ip": "203.0.113.9", "dest_port": 443,
                         "proto": "tcp", "asn": 64500, "org": "EXAMPLE-NET", "cc": "US", "bytes_out": 1,
                         "bytes_in": 1, "new_conn": True}], old)
    assert "src:radarr" in {n["id"] for n in build_posture(store, NOW, "24h")["nodes"]}
    assert "src:radarr" not in {n["id"] for n in build_posture(store, NOW, "live")["nodes"]}


def test_node_details_for_destination(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    details = node_details(store, "dst:AS64500", NOW, resolve=lambda ip: "edge.example.test")
    assert details["org"] == "EXAMPLE-NET" and details["known"] is False
    assert details["sources"] == [{"source": "sonarr", "bytes": 125000}]
    assert details["ips"][0] == {"ip": "203.0.113.75", "rdns": "edge.example.test"}
    assert node_details(store, "dst:AS99999", NOW) is None
    assert node_details(store, "bogus", NOW) is None
```

Extend `tests/test_web_api.py` (it already has helpers for calling `api.handle`; follow them):

```python
def test_posture_endpoints(temp_db):
    from atlas.posture.store import PostureStore
    from atlas.web import api
    store = PostureStore(temp_db)
    store.set_status("conntrack", True, {"flows": 1}, datetime.utcnow())
    status, body = api.handle("GET", "/api/posture?window=1h")
    assert status == 200 and {"strip", "nodes", "edges", "bands", "exposure", "review"} <= set(body)
    assert api.handle("GET", "/api/posture?window=bogus")[0] == 400
    assert api.handle("GET", "/api/posture/node?id=dst:AS1")[0] == 404
    assert api.handle("POST", "/api/posture/known", {"source": "sonarr", "asn_key": "AS64500"}) == (200, {"ok": True})
    assert api.handle("POST", "/api/posture/known", {"source": "sonarr", "asn_key": "x"})[0] == 400
    assert api.handle("POST", "/api/posture/known", ["x"])[0] == 400
```

(add `from datetime import datetime` at the top of that test file if missing.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_posture_model.py tests/test_web_api.py -v`
Expected: FAIL with `ModuleNotFoundError: atlas.posture.model`

- [ ] **Step 3: Implement `atlas/posture/model.py`**

```python
# atlas/posture/model.py
"""
The posture page's data: status strip, zone-map nodes/edges with preset
positions (three bands: inbound, outbound direct, outbound via VPN), public
exposure and unreviewed new destinations. Pure over PostureStore reads.
"""

import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta

from atlas.posture.store import asn_key


WINDOWS = {"live": timedelta(0), "1h": timedelta(hours=1), "24h": timedelta(hours=24)}
NEW_FOR = timedelta(days=7)
STALE_AFTER = timedelta(minutes=5)
MAX_SOURCES, MAX_DESTS = 8, 10
COL, ROW = 200, 64
BANDS = {"inbound": 40, "direct": 220, "vpn": 0}   # vpn y is computed after direct's height


def _fmt_bytes(value):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000


def _fresh(statuses, name, now):
    status = statuses.get(name)
    return bool(status and status["ok"] and now - status["updated_at"] <= STALE_AFTER)


def _strip(statuses, routes, review, now):

    tunnel = statuses.get("tunnel")
    gluetun, home = statuses.get("gluetun"), statuses.get("public_ip")
    crowdsec = statuses.get("crowdsec")
    public = [r for r in routes if r["protection"] != "authelia"]

    if not tunnel or now - tunnel["updated_at"] > STALE_AFTER:
        ingress = ("unknown", "No data", "")
    elif tunnel["ok"]:
        ingress = ("ok", "Tunnel up", f"{tunnel['detail'].get('connections', 0)} connections")
    else:
        ingress = ("warn", "Tunnel down", "no connections to Cloudflare")

    exit_ip = (gluetun or {}).get("detail", {}).get("exit_ip") if gluetun and gluetun["ok"] else None
    home_ip = (home or {}).get("detail", {}).get("ip") if home and home["ok"] else None
    if not exit_ip or not home_ip:
        vpn = ("unknown", "Unknown", "gluetun or public IP unavailable")
    elif exit_ip == home_ip:
        vpn = ("warn", "Leaking", "VPN exit IP equals the home IP")
    else:
        vpn = ("ok", "Verified", "exit IP differs from home")

    blocked = (("ok", str(crowdsec["detail"].get("active", 0)), "active CrowdSec bans")
               if crowdsec and crowdsec["ok"] else ("unknown", "-", "CrowdSec unavailable"))

    item = lambda key, label, state_value_detail: {"key": key, "label": label, "state": state_value_detail[0],
                                                    "value": state_value_detail[1], "detail": state_value_detail[2]}

    return [
        item("ingress", "Ingress", ingress),
        item("vpn", "VPN egress", vpn),
        item("exposure", "Exposure", ("ok" if routes else "unknown", f"{len(routes)} routes",
                                      f"{len(public)} without Authelia")),
        item("blocked", "Blocked", blocked),
        item("new", "New destinations", ("review" if review else "ok", str(len(review)),
                                         "need review" if review else "nothing new")),
    ]


def _node(node_id, label, sub, band, x, y, state="ok", w=170):
    return {"id": node_id, "label": label, "sub": sub, "band": band, "state": state, "x": x, "y": y, "w": w}


def _edge(source, target, bytes_=0, state="ok"):
    return {"id": f"{source}->{target}", "source": source, "target": target, "bytes": bytes_, "state": state}


def build_posture(store, now, window="24h"):

    statuses, routes = store.statuses(), store.latest_routes()
    seen = store.seen()
    review = sorted(({k: s[k] for k in ("source", "asn_key", "org", "cc", "first_seen")}
                     for s in seen if not s["known"] and now - s["first_seen"] <= NEW_FOR),
                    key=lambda s: s["first_seen"], reverse=True)
    review_keys = {(r["source"], r["asn_key"]) for r in review}
    flows = store.flows(now - WINDOWS[window])
    nodes, edges = [], []

    # Inbound band - fixed chain.
    y = BANDS["inbound"]
    authed = sum(r["protection"] == "authelia" for r in routes)
    tunnel_ok = _fresh(statuses, "tunnel", now)
    chain = [("in:internet", "Internet", "visitors"), ("in:cloudflare", "Cloudflare", "DNS + proxy"),
             ("in:tunnel", "cloudflared", f"{statuses.get('tunnel', {}).get('detail', {}).get('connections', 0)} connections"),
             ("in:traefik", "Traefik", f"{len(routes)} routes"), ("in:auth", "Authelia", f"{authed} routes")]
    for i, (node_id, label, sub) in enumerate(chain):
        nodes.append(_node(node_id, label, sub, "inbound", i * COL, y,
                           state="ok" if node_id != "in:tunnel" or tunnel_ok else "warn"))
        if i:
            edges.append(_edge(chain[i - 1][0], node_id))
    nodes.append(_node("in:svc-auth", "Behind Authelia", f"{authed} services", "inbound", 5 * COL, y))
    nodes.append(_node("in:svc-public", "Public", f"{len(routes) - authed} services", "inbound", 5 * COL, y + ROW,
                       state="review" if len(routes) - authed else "ok"))
    edges += [_edge("in:auth", "in:svc-auth"), _edge("in:traefik", "in:svc-public")]

    # Outbound direct band.
    direct = [f for f in flows if f["band"] == "direct"]
    by_source, by_dest, dest_meta, pair_state = {}, {}, {}, {}
    for f in direct:
        total = f["bytes_out"] + f["bytes_in"]
        key = asn_key(f["asn"], f["dest_ip"])
        by_source[f["source"]] = by_source.get(f["source"], 0) + total
        by_dest[key] = by_dest.get(key, 0) + total
        dest_meta[key] = (f["org"] or f["dest_ip"], f["cc"])
        if (f["source"], key) in review_keys:
            pair_state[key] = "review"

    top_sources = sorted(by_source, key=by_source.get, reverse=True)[:MAX_SOURCES]
    shown = sorted(by_dest, key=by_dest.get, reverse=True)[:MAX_DESTS]
    shown += [k for k in pair_state if k not in shown]
    others = sum(v for k, v in by_dest.items() if k not in shown)

    y0 = BANDS["direct"]
    for i, name in enumerate(top_sources):
        nodes.append(_node(f"src:{name}", name, _fmt_bytes(by_source[name]), "direct", 0, y0 + i * ROW))
        edges.append(_edge(f"src:{name}", "out:router", by_source[name]))
    rows = max(len(top_sources), len(shown) + (1 if others else 0), 1)
    nodes.append(_node("out:router", "Home router", "WAN", "direct", COL + 40, y0 + (rows - 1) * ROW // 2))
    for i, key in enumerate(shown):
        org, cc = dest_meta[key]
        nodes.append(_node(f"dst:{key}", org, f"{key} · {cc}" if cc else key, "direct", 2 * COL + 120,
                           y0 + i * ROW, state=pair_state.get(key, "ok"), w=260))
        edges.append(_edge("out:router", f"dst:{key}", by_dest[key], pair_state.get(key, "ok")))
    if others:
        nodes.append(_node("dst:others", "Other destinations", _fmt_bytes(others), "direct", 2 * COL + 120,
                           y0 + len(shown) * ROW, w=260))
        edges.append(_edge("out:router", "dst:others", others))

    # VPN band.
    vpn_y = y0 + rows * ROW + 60
    vpn_bytes = sum(f["bytes_out"] + f["bytes_in"] for f in flows if f["band"] == "vpn")
    gluetun = statuses.get("gluetun") or {}
    vpn_state = {"ok": "ok", "warn": "warn"}.get(next(s["state"] for s in _strip(statuses, routes, review, now)
                                                       if s["key"] == "vpn"), "unknown")
    nodes += [_node("vpn:members", "VPN clients", "qBittorrent etc.", "vpn", 0, vpn_y),
              _node("vpn:gluetun", "gluetun", _fmt_bytes(vpn_bytes), "vpn", COL + 40, vpn_y),
              _node("vpn:exit", "VPN exit", gluetun.get("detail", {}).get("exit_ip", "unknown"), "vpn",
                    2 * COL + 120, vpn_y, state=vpn_state, w=260)]
    edges += [_edge("vpn:members", "vpn:gluetun"), _edge("vpn:gluetun", "vpn:exit", vpn_bytes, vpn_state)]

    bands = [
        {"id": "inbound", "label": "Inbound · public", "y": BANDS["inbound"] - 30, "h": 2 * ROW + 40,
         "stale": not _fresh(statuses, "tunnel", now) and not _fresh(statuses, "routes", now)},
        {"id": "direct", "label": "Outbound · direct", "y": y0 - 30, "h": rows * ROW + 40,
         "stale": not _fresh(statuses, "conntrack", now)},
        {"id": "vpn", "label": "Outbound · via VPN", "y": vpn_y - 30, "h": ROW + 40,
         "stale": not _fresh(statuses, "gluetun", now)},
    ]

    return {"generated_at": now.isoformat(), "window": window, "strip": _strip(statuses, routes, review, now),
            "nodes": nodes, "edges": edges, "bands": bands, "exposure": routes,
            "review": [{**r, "first_seen": r["first_seen"].isoformat()} for r in review]}


def _reverse_dns(ip):
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return pool.submit(lambda: socket.gethostbyaddr(ip)[0]).result(timeout=1)
        except (FutureTimeout, OSError):
            return ""


def node_details(store, node_id, now, resolve=_reverse_dns):

    if not node_id.startswith("dst:") or node_id == "dst:others":
        return None

    key = node_id[4:]
    flows = [f for f in store.flows(now - WINDOWS["24h"]) if asn_key(f["asn"], f["dest_ip"]) == key]
    if not flows:
        return None

    seen = [s for s in store.seen() if s["asn_key"] == key]
    sources, ips = {}, {}
    for f in flows:
        total = f["bytes_out"] + f["bytes_in"]
        sources[f["source"]] = sources.get(f["source"], 0) + total
        ips[f["dest_ip"]] = ips.get(f["dest_ip"], 0) + total
    top_ips = sorted(ips, key=ips.get, reverse=True)[:5]

    return {"id": node_id, "asn_key": key, "asn": flows[0]["asn"], "org": flows[0]["org"], "cc": flows[0]["cc"],
            "first_seen": min(s["first_seen"] for s in seen).isoformat() if seen else None,
            "known": all(s["known"] for s in seen) if seen else False,
            "sources": [{"source": s, "bytes": b} for s, b in sorted(sources.items(), key=lambda kv: -kv[1])],
            "ips": [{"ip": ip, "rdns": resolve(ip) if i == 0 else ""} for i, ip in enumerate(top_ips)],
            "ports": sorted({f["dest_port"] for f in flows})}
```

(`_strip` is computed twice in `build_posture`; that is fine at this size - call it once into a local and reuse it if you prefer, but keep one implementation.)

- [ ] **Step 4: Wire the API** in `atlas/web/api.py`:

At the top add `from datetime import datetime` and `from atlas.posture.model import WINDOWS, build_posture, node_details` and `from atlas.posture.store import PostureStore`.

At the start of `_get` (before `store = InventoryStore()`):

```python
    if path == "/api/posture":
        params = dict(part.partition("=")[::2] for part in query.split("&") if part)
        window = params.get("window", "24h")
        if window not in WINDOWS:
            return 400, {"error": "window must be one of: " + ", ".join(WINDOWS)}
        return 200, build_posture(PostureStore(), datetime.utcnow(), window)

    if path == "/api/posture/node":
        params = dict(part.partition("=")[::2] for part in query.split("&") if part)
        details = node_details(PostureStore(), params.get("id", ""), datetime.utcnow())
        return (200, details) if details else NOT_FOUND
```

At the start of `_post`:

```python
    if path == "/api/posture/known":
        if not isinstance(body, dict):
            return 400, {"error": "expected a JSON object"}
        result = PostureStore().mark_known(body.get("source"), body.get("asn_key"), body.get("note", ""))
        if not result["ok"]:
            return 400, {"error": result["error"]}
        _publish_event("atlas.posture.marked_known", {"source": body["source"], "asn_key": body["asn_key"]})
        return 200, result
```

Use whatever event-publishing helper `api.py` already uses for `atlas.devices.updated` (`_result` wraps it - read `_result` and call the same publish function it uses; do not invent `_publish_event` if a helper exists under another name). URL-decode the `id` query value with `urllib.parse.unquote` (`dst:ip:1.2.3.4` contains colons, which are fine, but encoded clients may send `%3A`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_posture_model.py tests/test_web_api.py -v`
Expected: PASS

- [ ] **Step 6: Full suite + commit (end of PR 2)**

Run: `python -m pytest tests/ -q` → all pass.

```bash
git add atlas/posture/model.py atlas/web/api.py tests/test_posture_model.py tests/test_web_api.py
git commit -m "feat(posture): posture model and /api/posture endpoints"
```

Open PR 2; `gh pr checks` green; user merges.

---

## PR 3 - new shell

### Task 9: Nav shell, tabs, posture page skeleton, `/` route

**Files:**
- Modify: `atlas/web/render.py` (`render_page`, `PAGE_STYLE`)
- Modify: `atlas/web/devices_pages.py`, `render_history_page`/`render_trends_page` in `render.py` (tab strip)
- Create: `atlas/web/posture_page.py`
- Modify: `atlas/web/server.py` (`/` → posture page; old overview at `/overview`)
- Test: `tests/test_web_render.py`, `tests/test_web_server.py`, new `tests/test_web_posture_page.py`

**Interfaces:**
- Produces:
  - `render_page(title, body_html, active="", tabs=None, drawer=True)` - `active` ∈ `posture, devices, lan, history`; `tabs` is a list of `(href, label, is_active)`; `drawer` reserved for Task 11 (accept and ignore for now).
  - `NAV = [("/", "Posture", "posture"), ("/devices", "Devices", "devices"), ("/map", "LAN map", "lan"), ("/history", "History", "history")]`.
  - `render_posture_page() -> str` - static shell: strip container `#strip`, map host `#posture-map`, window toggle buttons `data-window`, panel `#posture-panel`, exposure list `#exposure`; data is loaded by JS (Task 10) from `/api/posture`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_posture_page.py
from atlas.web.posture_page import render_posture_page
from atlas.web.render import NAV, render_page


def test_nav_has_four_sections_and_marks_active():
    html = render_page("Devices", "<p>x</p>", active="devices")
    for href, label, _ in NAV:
        assert f'href="{href}"' in html and label in html
    assert 'aria-current="page" href="/devices"' in html or 'href="/devices" aria-current="page"' in html


def test_tabs_render_with_current_marked():
    html = render_page("Triage", "", active="devices",
                       tabs=[("/devices", "Devices", False), ("/triage", "Triage", True)])
    assert 'class="tabs"' in html and ">Triage<" in html


def test_posture_page_shell():
    html = render_posture_page()
    for marker in ('id="strip"', 'id="posture-map"', 'data-window="live"', 'data-window="1h"',
                   'data-window="24h"', 'id="posture-panel"', 'id="exposure"', "/static/cytoscape.min.js"):
        assert marker in html
```

In `tests/test_web_server.py` add a test that `GET /` returns the posture page (look for `id="posture-map"`) and `GET /overview` returns the old overview (follow the file's existing server-request helper).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_web_posture_page.py tests/test_web_server.py -v`
Expected: FAIL (`ImportError: NAV` / no posture page)

- [ ] **Step 3: Implement the shell**

In `atlas/web/render.py` replace `render_page` with:

```python
NAV = [("/", "Posture", "posture"), ("/devices", "Devices", "devices"), ("/map", "LAN map", "lan"),
       ("/history", "History", "history")]


def render_page(title, body_html, active="", tabs=None, drawer=True):

    here = ' aria-current="page"'   # built outside the f-strings: backslashes in f-string expressions need 3.12
    links = "".join(
        f'<a href="{href}"{here if key == active else ""}>{_esc(label)}</a>'
        for href, label, key in NAV
    )
    tab_html = ""
    if tabs:
        tab_html = '<nav class="tabs" aria-label="Section">' + "".join(
            f'<a href="{href}"{here if current else ""}>{_esc(label)}</a>'
            for href, label, current in tabs) + "</nav>"

    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Atlas - {_esc(title)}</title>"
        f"<style>{PAGE_STYLE}</style></head><body>"
        "<header class=\"topbar\"><span class=\"brand\">ATLAS</span>"
        f"<nav class=\"main\" aria-label=\"Main\">{links}</nav>"
        "<span class=\"spacer\"></span>"
        "<a class=\"chat-link\" href=\"/chat\">Chat</a></header>"
        f"<main class=\"page\"><h1>{_esc(title)}</h1>{tab_html}{body_html}</main>"
        "</body></html>"
    )
```

Append to `PAGE_STYLE` (keep existing rules; these add the shell):

```css
:root { --bg:#0e131a; --surface:#151c25; --surface2:#1b2430; --line:#263140; --text:#e7edf3; --muted:#a3b0bd;
        --blue:#5aa7f0; --green:#43c08f; --orange:#f0a23a; --red:#f47a5c; }
body { margin:0; background:var(--bg); color:var(--text);
       font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }
.topbar { display:flex; flex-wrap:wrap; align-items:center; gap:16px; padding:12px 24px;
          background:#111821; border-bottom:1px solid #222c38; }
.topbar .brand { font-weight:600; letter-spacing:.14em; }
.topbar nav.main { display:flex; flex-wrap:wrap; gap:4px; }
.topbar nav.main a, .topbar .chat-link { padding:10px 14px; border-radius:8px; color:var(--muted); text-decoration:none; }
.topbar nav.main a[aria-current="page"] { background:var(--surface2); color:var(--text); }
.topbar .spacer { flex:1; }
.page { padding:16px 24px 32px; }
.tabs { display:flex; gap:4px; margin:0 0 16px; border-bottom:1px solid var(--line); }
.tabs a { padding:10px 14px; color:var(--muted); text-decoration:none; border-bottom:2px solid transparent; }
.tabs a[aria-current="page"] { color:var(--text); border-bottom-color:var(--blue); }
```

Remove the old `nav { ... }` rule in `PAGE_STYLE` if it conflicts (read it first; the old nav was a bare `<nav>` at the top - its selector would now also match `.tabs` and `nav.main`, so scope it or delete it).

Tabs: devices pages call `render_page(title, body, active="devices", tabs=DEVICE_TABS(current))` with

```python
def device_tabs(current):
    return [("/devices", "Devices", current == "devices"), ("/triage", "Triage", current == "triage"),
            ("/coverage", "Coverage", current == "coverage")]
```

defined in `devices_pages.py`; `render_device_page` uses `active="devices"` with no tabs. History/Trends use `active="history"` and tabs `[("/history", "Events", ...), ("/trends", "Trends", ...)]`. `render_map_page` uses `active="lan"`. `render_overview_page` uses `active="posture"` with tabs `[("/", "Posture", False), ("/overview", "Host overview", True)]`. `render_chat_page` passes `drawer=False` (it already shows chat).

Create `atlas/web/posture_page.py`:

```python
"""
/ - the posture page: status strip, zone map (inbound / outbound direct /
outbound via VPN), details panel and public exposure. Markup only here; data
comes from /api/posture via POSTURE_SCRIPT (Task 10).
"""

from atlas.web.render import render_page


POSTURE_STYLE = """
<style>
#strip { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-bottom:16px; }
#strip .chip { padding:14px 16px; background:var(--surface); border:1px solid var(--line); border-radius:12px;
               color:var(--text); text-align:left; font:inherit; cursor:pointer; }
#strip .chip .k { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
#strip .chip .v { font-size:20px; font-weight:600; margin-top:4px; }
#strip .chip .d { font-size:13px; color:var(--muted); }
#strip .chip.ok .v { color:#7fdcb5; } #strip .chip.warn { border-color:var(--red); } #strip .chip.warn .v { color:#ffb4a2; }
#strip .chip.review { border-color:var(--orange); background:#2b2213; } #strip .chip.review .v { color:#ffd08a; }
#strip .chip.unknown .v { color:var(--muted); }
.posture { display:flex; flex-wrap:wrap; gap:20px; }
.posture .mapcard { flex:999 1 720px; min-width:0; background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.posture aside { flex:1 1 320px; min-width:0; display:flex; flex-direction:column; gap:16px; }
.posture aside section { background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.mapbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:12px; }
.mapbar .windows { display:flex; gap:4px; padding:3px; border:1px solid var(--line); border-radius:8px; }
.mapbar .windows button { font:inherit; font-size:13px; padding:8px 12px; border:0; border-radius:6px;
                          background:transparent; color:var(--muted); cursor:pointer; }
.mapbar .windows button[aria-pressed="true"] { background:var(--surface2); color:var(--text); }
.legend { margin-left:auto; display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); }
.legend i { display:inline-block; width:18px; height:3px; margin-right:6px; vertical-align:middle; }
#posture-map { height:560px; border-radius:10px; background:var(--bg); }
#exposure li { display:flex; justify-content:space-between; gap:8px; padding:4px 0; }
.prot-authelia { color:#7fdcb5; } .prot-public { color:#ffd08a; }
@media (max-width: 900px) { #strip { grid-template-columns:repeat(2,minmax(0,1fr)); } #posture-map { height:420px; } }
</style>
"""


def render_posture_page():

    body = (
        POSTURE_STYLE
        + '<section id="strip" aria-label="Posture summary"><p class="muted">Loading...</p></section>'
        + '<div class="posture"><section class="mapcard">'
        + '<div class="mapbar"><h2 style="margin:0;font-size:16px">Network posture</h2>'
        + '<div class="windows" role="group" aria-label="Time window">'
        + '<button data-window="live" aria-pressed="false">Live</button>'
        + '<button data-window="1h" aria-pressed="false">1 h</button>'
        + '<button data-window="24h" aria-pressed="true">24 h</button></div>'
        + '<div class="legend"><span><i style="background:#5aa7f0"></i>Inbound</span>'
        + '<span><i style="background:#8b98a6"></i>Outbound</span>'
        + '<span><i style="background:#43c08f"></i>Via VPN</span>'
        + '<span><i style="background:#f0a23a"></i>New / unreviewed</span></div></div>'
        + '<div id="posture-map" role="img" aria-label="Zone map of inbound, outbound and VPN traffic"></div>'
        + '<p class="muted" id="posture-msg">Click a box for details. Line width = traffic; dashed orange = '
          'a network this container never used before.</p></section>'
        + '<aside><section id="posture-panel"><h2 style="margin:0 0 8px;font-size:15px">Details</h2>'
        + '<p class="muted">Select a destination on the map.</p></section>'
        + '<section><h2 style="margin:0 0 8px;font-size:15px">Public exposure</h2><ul id="exposure" '
          'style="list-style:none;margin:0;padding:0"></ul></section></aside></div>'
        + '<script src="/static/cytoscape.min.js?v=3.34.3"></script>'
    )

    return render_page("Posture", body, active="posture")
```

In `atlas/web/server.py`: `from atlas.web.posture_page import render_posture_page`; change `if path == "/":` to render `render_posture_page()`, and add `elif path == "/overview":` with the old `render_overview_page(query.latest_environment(), query.latest_analysis())` body.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_web_posture_page.py tests/test_web_server.py tests/test_web_render.py tests/test_web_devices_pages.py tests/test_web_chat_page.py -v`
Expected: PASS. Existing tests asserting the old `<nav>` links (e.g. `href="/trends"` in the nav) will fail - update those assertions to the new nav/tabs, they are describing the intended change.

- [ ] **Step 5: Commit (end of PR 3)**

```bash
git add atlas/web/ tests/
git commit -m "feat(web): new shell - posture home, four-section nav, section tabs"
```

Open PR 3; checks green; user merges.

---

## PR 4 - map + details panel

### Task 10: Posture JS (strip, Cytoscape map, panel, Mark as expected)

**Files:**
- Modify: `atlas/web/posture_page.py` (add `POSTURE_SCRIPT`, include it after the cytoscape tag)
- Test: `tests/test_web_posture_page.py`

**Interfaces:**
- Consumes: `/api/posture` and `/api/posture/node` JSON (Task 8), node id scheme (Task 8), `POST /api/posture/known`.
- Produces (DOM contract used by Task 11): a button `#ask-atlas` in the panel with `data-prefill` text, and a global `window.atlasAsk(text)` hook that Task 11 defines; Task 10 calls it if present, else navigates to `/chat?q=<text>` (encodeURIComponent).

- [ ] **Step 1: Write the failing test**

```python
def test_posture_script_contract():
    html = render_posture_page()
    for marker in ('fetch("/api/posture?window="', "/api/posture/node?id=", "/api/posture/known",
                   "preset", "textContent", "atlasAsk", "setInterval"):
        assert marker in html
    assert "innerHTML" not in html.split("<script>")[-1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_posture_page.py::test_posture_script_contract -v`
Expected: FAIL

- [ ] **Step 3: Implement `POSTURE_SCRIPT`** (append `+ POSTURE_SCRIPT` after the cytoscape `<script>` tag in `render_posture_page`):

```python
POSTURE_SCRIPT = """
<script>
(() => {
const strip = document.getElementById("strip");
const panel = document.getElementById("posture-panel");
const exposure = document.getElementById("exposure");
const msg = document.getElementById("posture-msg");
const COLORS = {inbound: "#5aa7f0", direct: "#8b98a6", vpn: "#43c08f"};
let windowName = "24h", cy = null, timer = null;

function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function fmt(n) { const u = ["B","KB","MB","GB","TB"]; let i = 0; while (n >= 1000 && i < 4) { n /= 1000; i++; } return (i ? n.toFixed(1) : n.toFixed(0)) + " " + u[i]; }

function renderStrip(items) {
  strip.replaceChildren(...items.map((item) => {
    const b = el("button", undefined, "chip " + item.state);
    b.append(el("div", item.label, "k"), el("div", item.value, "v"), el("div", item.detail, "d"));
    b.addEventListener("click", () => { if (cy) cy.nodes().removeClass("dim"); });
    return b;
  }));
}

function renderExposure(routes) {
  exposure.replaceChildren(...routes.map((r) => {
    const li = el("li");
    li.append(el("span", (r.hosts[0] || r.name)), el("span", r.protection === "authelia" ? "Authelia" : "public · own login", "prot-" + r.protection));
    return li;
  }));
  if (!routes.length) exposure.replaceChildren(el("li", "No routes seen yet.", "muted"));
}

function elements(data) {
  const out = [];
  data.bands.forEach((b) => out.push({group: "nodes", data: {id: "band:" + b.id, label: b.label + (b.stale ? " · no recent data" : "")},
    classes: "band" + (b.stale ? " stale" : ""), position: {x: 560, y: b.y + b.h / 2}, locked: true, grabbable: false, selectable: false,
    style: {width: 1180, height: b.h}}));
  data.nodes.forEach((n) => out.push({group: "nodes", data: {id: n.id, label: n.label + "\\n" + n.sub, band: n.band},
    classes: "box " + n.state + " " + n.band, position: {x: n.x + n.w / 2, y: n.y}, style: {width: n.w}}));
  const max = Math.max(1, ...data.edges.map((e) => e.bytes));
  data.edges.forEach((e) => out.push({group: "edges", data: {id: e.id, source: e.source, target: e.target,
    w: 1.5 + 6 * Math.sqrt(e.bytes / max)}, classes: e.state}));
  return out;
}

const STYLE = [
  {selector: "node.band", style: {"shape": "round-rectangle", "background-opacity": 0.06, "background-color": "#5aa7f0",
    "border-width": 1, "border-style": "dashed", "border-color": "#2c4560", "label": "data(label)", "color": "#a3b0bd",
    "font-size": 11, "text-valign": "top", "text-halign": "center", "text-margin-y": 16, "events": "no"}},
  {selector: "node.band.stale", style: {"background-color": "#8b98a6", "color": "#ffb4a2"}},
  {selector: "node.box", style: {"shape": "round-rectangle", "height": 44, "background-color": "#1b2430",
    "border-width": 1, "border-color": "#2f3b4c", "label": "data(label)", "color": "#e7edf3", "font-size": 11,
    "text-wrap": "wrap", "text-valign": "center", "text-halign": "center"}},
  {selector: "node.box.review", style: {"border-color": "#f0a23a", "background-color": "#2b2213", "color": "#ffd08a"}},
  {selector: "node.box.warn", style: {"border-color": "#f47a5c", "background-color": "#2a1d1a", "color": "#ffb4a2"}},
  {selector: "node.box.unknown", style: {"color": "#a3b0bd", "border-style": "dashed"}},
  {selector: "node.box:selected", style: {"border-color": "#5aa7f0", "border-width": 3}},
  {selector: "edge", style: {"width": "data(w)", "line-color": "#8b98a6", "target-arrow-color": "#8b98a6",
    "target-arrow-shape": "triangle", "curve-style": "taxi", "taxi-direction": "horizontal", "opacity": 0.8}},
  {selector: "edge.review", style: {"line-color": "#f0a23a", "target-arrow-color": "#f0a23a", "line-style": "dashed"}},
  {selector: "edge.warn", style: {"line-color": "#f47a5c", "target-arrow-color": "#f47a5c"}},
];

function draw(data) {
  const els = elements(data);
  els.forEach((e) => { if (e.group === "edges") {
    const src = data.nodes.find((n) => n.id === e.data.source);
    if (src && e.classes === "ok") e.classes = src.band; } });
  if (cy) cy.destroy();
  cy = cytoscape({container: document.getElementById("posture-map"), elements: els, style: STYLE.concat(
    Object.entries(COLORS).map(([band, color]) => ({selector: "edge." + band, style: {"line-color": color, "target-arrow-color": color}}))),
    layout: {name: "preset", fit: true, padding: 24}, userZoomingEnabled: true, wheelSensitivity: 0.2, autoungrabify: true});
  cy.on("tap", "node.box", (event) => select(event.target.id()));
}

async function select(id) {
  panel.replaceChildren(el("h2", "Details"));
  panel.firstChild.style.cssText = "margin:0 0 8px;font-size:15px";
  if (!id.startsWith("dst:") || id === "dst:others") { panel.append(el("p", "Pick a destination box to see who talks to it.", "muted")); return; }
  panel.append(el("p", "Loading...", "muted"));
  const response = await fetch("/api/posture/node?id=" + encodeURIComponent(id), {credentials: "same-origin"});
  const d = response.ok ? await response.json() : null;
  panel.lastChild.remove();
  if (!d) { panel.append(el("p", "No traffic recorded for this in the last 24 h.", "muted")); return; }
  panel.append(el("div", d.known ? "Expected destination" : "Not reviewed yet", d.known ? "muted" : "review-label"));
  panel.append(el("div", d.org || d.asn_key, "big"));
  const dl = el("dl");
  [["Network", d.asn_key], ["Country", d.cc || "?"], ["First seen", d.first_seen ? new Date(d.first_seen + "Z").toLocaleString() : "?"],
   ["Ports", d.ports.join(", ")], ["Top address", d.ips[0] ? d.ips[0].ip + (d.ips[0].rdns ? " (" + d.ips[0].rdns + ")" : "") : "?"]]
    .forEach(([k, v]) => dl.append(el("dt", k), el("dd", v)));
  panel.append(dl, el("h3", "From"));
  const ul = el("ul");
  d.sources.forEach((s) => ul.append(el("li", s.source + " · " + fmt(s.bytes))));
  panel.append(ul);
  const ask = el("button", "Ask Atlas about this", "primary");
  ask.id = "ask-atlas";
  ask.dataset.prefill = "Why is " + d.sources.map((s) => s.source).join(", ") + " talking to " + (d.org || d.asn_key) +
    " (" + d.asn_key + ", " + (d.cc || "?") + ", ports " + d.ports.join(",") + ")? Is this expected?";
  ask.addEventListener("click", () => { const text = ask.dataset.prefill;
    if (window.atlasAsk) window.atlasAsk(text); else location.href = "/chat?q=" + encodeURIComponent(text); });
  panel.append(ask);
  if (!d.known) d.sources.forEach((s) => {
    const mark = el("button", "Mark expected for " + s.source);
    mark.addEventListener("click", async () => {
      mark.disabled = true;
      const r = await fetch("/api/posture/known", {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify({source: s.source, asn_key: d.asn_key})});
      mark.textContent = r.ok ? "Marked expected" : "Failed (" + r.status + ")";
      if (r.ok) load();
    });
    panel.append(mark);
  });
}

async function load() {
  try {
    const response = await fetch("/api/posture?window=" + windowName, {credentials: "same-origin"});
    if (!response.ok) { msg.textContent = "Could not load posture data (" + response.status + ")."; return; }
    const data = await response.json();
    renderStrip(data.strip); renderExposure(data.exposure); draw(data);
  } catch (error) { msg.textContent = "Could not load posture data: " + error; }
}

document.querySelectorAll("[data-window]").forEach((b) => b.addEventListener("click", () => {
  windowName = b.dataset.window;
  document.querySelectorAll("[data-window]").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
  clearInterval(timer);
  if (windowName === "live") timer = setInterval(load, 30000);
  load();
}));

load();
})();
</script>
"""
```

Also add to `POSTURE_STYLE`: `#posture-panel dl { display:grid; grid-template-columns:auto 1fr; gap:6px 12px; font-size:13px; } #posture-panel dt { color:var(--muted); } #posture-panel .big { font-size:18px; margin:4px 0 12px; } .review-label { color:#ffd08a; font-size:12px; text-transform:uppercase; letter-spacing:.06em; } #posture-panel button { margin:8px 8px 0 0; }`.

The `select` arrow-key behaviour is not required; nodes are reachable with a mouse/touch, and every fact in the map is also listed in the strip/exposure/panel text (the map has `role="img"` + label).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_web_posture_page.py -v`
Expected: PASS

- [ ] **Step 5: Manual check against seeded data** (the JS has no unit tests; this is its test)

```bash
mkdir -p /tmp/atlas-ui && cd /tmp/atlas-ui && python - <<'EOF'
from datetime import datetime
from atlas.posture.store import PostureStore
s = PostureStore(); now = datetime.utcnow()
s.record_flows([{"source": "sonarr", "band": "direct", "dest_ip": "203.0.113.75", "dest_port": 443, "proto": "tcp",
  "asn": 64500, "org": "EXAMPLE-NET", "cc": "US", "bytes_out": 5000, "bytes_in": 120000, "new_conn": True}], now)
for src, ok, d in [("tunnel", True, {"connections": 4}), ("conntrack", True, {"flows": 3}),
                   ("gluetun", True, {"exit_ip": "198.51.100.9"}), ("public_ip", True, {"ip": "192.0.2.10"}),
                   ("crowdsec", True, {"active": 3})]:
    s.set_status(src, ok, d, now)
EOF
atlas web --port 8421
```

Open `http://127.0.0.1:8421/`: strip shows 5 chips; map shows three bands; clicking `EXAMPLE-NET` fills the panel; "Mark expected for sonarr" turns the edge grey after reload; the 24 h/1 h/Live toggle reloads. Stop the server.

- [ ] **Step 6: Commit (end of PR 4)**

```bash
git add atlas/web/posture_page.py tests/test_web_posture_page.py
git commit -m "feat(web): posture zone map, details panel, mark as expected"
```

Open PR 4; checks green; user merges.

---

## PR 5 - chat side panel

### Task 11: Shared chat assets + drawer on every page

**Files:**
- Create: `atlas/web/chat_assets.py` (move `CHAT_STYLE`, `CHAT_SCRIPT` here from `chat_page.py`)
- Modify: `atlas/web/chat_page.py` (import from `chat_assets`; read `?q=` prefill)
- Modify: `atlas/web/render.py` (`render_page(..., drawer=True)` renders the drawer + script)
- Modify: `atlas/web/server.py` (`/chat?q=` prefill)
- Test: `tests/test_web_chat_page.py`, `tests/test_web_render.py`

**Interfaces:**
- Consumes: existing `POST /api/chat`, `POST /api/actions/execute`; `window.atlasAsk` hook from Task 10.
- Produces: `CHAT_STYLE`, `CHAT_SCRIPT`, `DRAWER_HTML` in `atlas/web/chat_assets.py`; `CHAT_SCRIPT` additionally (a) persists the visible log in `sessionStorage["atlasChatLog"]` (list of `{who, text}`, max 50) and restores it on load, (b) defines `window.atlasAsk(text)` which opens the drawer, puts `text` in `#ask` and focuses it.

- [ ] **Step 1: Write the failing tests**

```python
# in tests/test_web_render.py
def test_every_page_gets_the_chat_drawer_except_chat():
    from atlas.web.render import render_page
    html = render_page("Devices", "", active="devices")
    assert 'id="chat-drawer"' in html and 'id="ask"' in html and "atlasAsk" in html
    assert 'id="chat-drawer"' not in render_page("Chat", "", drawer=False)

# in tests/test_web_chat_page.py
def test_chat_page_prefills_from_q_and_has_no_drawer():
    from atlas.web.chat_page import render_chat_page
    html = render_chat_page("hello <b>")
    assert "hello &lt;b&gt;" in html and 'id="chat-drawer"' not in html
    assert html.count('id="ask"') == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_web_render.py tests/test_web_chat_page.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

`atlas/web/chat_assets.py`: move `CHAT_STYLE` and `CHAT_SCRIPT` verbatim from `chat_page.py`, then extend `CHAT_SCRIPT`:

1. Right after `const status = ...` add:

```javascript
const drawer = document.getElementById("chat-drawer");
const LOG_KEY = "atlasChatLog";
function saveLog(who, text) {
  try { const items = JSON.parse(sessionStorage.getItem(LOG_KEY) || "[]"); items.push({who, text});
        sessionStorage.setItem(LOG_KEY, JSON.stringify(items.slice(-50))); } catch (error) {}
}
function restoreLog() {
  try { JSON.parse(sessionStorage.getItem(LOG_KEY) || "[]").forEach((m) => bubble(m.text, m.who, true)); } catch (error) {}
}
window.atlasAsk = (text) => { if (drawer) drawer.hidden = false; ask.value = text; ask.focus(); };
```

2. Change `function bubble(text, who)` to `function bubble(text, who, restoring)` and add `if (!restoring) saveLog(who, text);` before `return div;`.
3. In the `newChat` click handler also `try { sessionStorage.removeItem(LOG_KEY); } catch (error) {}`.
4. Before the closing `</script>` add `restoreLog();` and, if `drawer`, wire `document.getElementById("chat-toggle")` and `document.getElementById("chat-close")` to toggle `drawer.hidden`.

`DRAWER_HTML`:

```python
DRAWER_HTML = (
    '<aside id="chat-drawer" hidden aria-label="Chat with Atlas">'
    '<div class="drawer-head"><h2>Chat with Atlas</h2>'
    '<button id="chat-close" aria-label="Close chat">Close</button></div>'
    '<div id="log"></div>'
    '<label for="ask" class="sr-only">Message Atlas</label>'
    '<textarea id="ask" placeholder="Ask, troubleshoot, diagnose..."></textarea>'
    '<p><button class="primary" id="send">Send</button> <button id="new-chat">New conversation</button> '
    '<span class="muted" id="chat-status"></span></p></aside>'
)

DRAWER_STYLE = """
<style>
#chat-drawer { position:fixed; top:0; right:0; bottom:0; width:min(420px,100vw); box-sizing:border-box;
  background:#111821; border-left:1px solid #222c38; padding:16px; display:flex; flex-direction:column; gap:12px; z-index:10; }
#chat-drawer[hidden] { display:none; }
#chat-drawer .drawer-head { display:flex; justify-content:space-between; align-items:center; }
#chat-drawer .drawer-head h2 { margin:0; font-size:15px; }
#chat-drawer #log { flex:1; overflow-y:auto; }
.sr-only { position:absolute; left:-9999px; }
@media (min-width: 1400px) { body.drawer-open .page { margin-right:420px; } }
</style>
"""
```

When the drawer opens/closes also toggle `document.body.classList.toggle("drawer-open", !drawer.hidden)` so wide screens dock it beside the content (layout C) instead of covering it.

In `render_page`: change the top-bar chat link to `<button id="chat-toggle" class="chat-link">Atlas</button>` when `drawer` is True (keep the `/chat` link when False), and append `CHAT_STYLE + DRAWER_STYLE + DRAWER_HTML + CHAT_SCRIPT` before `</body>` when `drawer` is True. Import from `atlas.web.chat_assets` inside `render.py` (no circular import: `chat_assets` imports nothing from `render`).

`chat_page.py`: `from atlas.web.chat_assets import CHAT_STYLE, CHAT_SCRIPT`; `render_page("Chat", body, drawer=False)`. `server.py` `/chat`: if the query has `q=`, use `urllib.parse.parse_qs(...)["q"][0][:2000]` as `prefill` (the existing `device=` prefill stays).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: Manual check** - with the Task 10 seeded server: open `/`, click "Atlas" → drawer opens; on a ≥1400 px window the page shifts left instead of being covered; click a destination → "Ask Atlas about this" fills the drawer; send a message (Ollama reachable or not - the error bubble is fine); go to `/devices` → drawer log restores; `/chat` has no drawer.

- [ ] **Step 6: Commit (end of PR 5)**

```bash
git add atlas/web/ tests/
git commit -m "feat(web): chat side panel on every page, ask-about-this from the map"
```

Open PR 5; checks green; user merges.

---

## PR 6 - tile + deployment

### Task 12: `/api/summary` posture block + Homepage tile

**Files:**
- Modify: `atlas/web/render.py` (`build_summary(topology, devices=(), posture=None)`)
- Modify: `atlas/web/server.py` (`/api/summary` passes `build_posture(PostureStore(), datetime.utcnow(), "24h")`, wrapped in try/except → `None` on failure)
- Test: `tests/test_web_render.py`
- Docs: `docs/` page that documents the Homepage tile (find it with `grep -rn customapi docs/`), plus homelab-ops `cyberpac/` services.yaml copy (Task 13)

**Interfaces:**
- Consumes: `build_posture()` output (Task 8).
- Produces: `summary["posture"] = {"state": "ok"|"review"|"warn"|"unknown", "tunnel": str, "vpn": str, "routes": int, "blocked": str, "review_count": int, "message": str, "link": str}`. `state` = `warn` if any strip item is `warn`, else `review` if `new` is `review`, else `unknown` if ingress is `unknown`, else `ok`. `message` = `"All good"`, or for review `"<source> reached <org> (<cc>)"` from `posture["review"][0]`, or the first warn item's `"<label>: <value>"`. `link` = `"/"`.

- [ ] **Step 1: Write the failing test**

```python
def test_summary_posture_block():
    from atlas.web.render import build_summary
    posture = {"strip": [
        {"key": "ingress", "state": "ok", "value": "Tunnel up", "label": "Ingress", "detail": ""},
        {"key": "vpn", "state": "ok", "value": "Verified", "label": "VPN egress", "detail": ""},
        {"key": "exposure", "state": "ok", "value": "14 routes", "label": "Exposure", "detail": ""},
        {"key": "blocked", "state": "ok", "value": "37", "label": "Blocked", "detail": ""},
        {"key": "new", "state": "review", "value": "1", "label": "New destinations", "detail": ""}],
        "exposure": [{}] * 14,
        "review": [{"source": "sonarr", "asn_key": "AS64500", "org": "EXAMPLE-NET", "cc": "US", "first_seen": ""}]}
    block = build_summary(None, (), posture)["posture"]
    assert block == {"state": "review", "tunnel": "Tunnel up", "vpn": "Verified", "routes": 14, "blocked": "37",
                     "review_count": 1, "message": "sonarr reached EXAMPLE-NET (US)", "link": "/"}
    assert "posture" not in build_summary(None, (), None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web_render.py::test_summary_posture_block -v`
Expected: FAIL

- [ ] **Step 3: Implement** - add to `render.py`:

```python
def _posture_block(posture):

    items = {item["key"]: item for item in posture["strip"]}
    warn = next((item for item in posture["strip"] if item["state"] == "warn"), None)

    if warn:
        state, message = "warn", f"{warn['label']}: {warn['value']}"
    elif items["new"]["state"] == "review" and posture["review"]:
        first = posture["review"][0]
        state, message = "review", f"{first['source']} reached {first['org'] or first['asn_key']} ({first['cc'] or '?'})"
    elif items["ingress"]["state"] == "unknown":
        state, message = "unknown", "No posture data yet"
    else:
        state, message = "ok", "All good"

    return {"state": state, "tunnel": items["ingress"]["value"], "vpn": items["vpn"]["value"],
            "routes": len(posture["exposure"]), "blocked": items["blocked"]["value"],
            "review_count": len(posture["review"]), "message": message, "link": "/"}
```

Change the signature to `build_summary(topology, devices=(), posture=None)`; in both return paths add `**({"posture": _posture_block(posture)} if posture else {})` (for the no-topology early return, merge it into that dict too).

In `server.py` `/api/summary`:

```python
            try:
                posture = build_posture(PostureStore(), datetime.utcnow(), "24h")
            except Exception as error:
                self.log_error("posture summary failed: %r", error)
                posture = None
            self._send(200, "application/json",
                       json.dumps(build_summary(query.latest_topology(), InventoryStore().devices(), posture)))
```

Docs: in the Homepage tile docs page, add the new mappings:

```yaml
- Atlas:
    href: https://atlas.example.test/
    widget:
      type: customapi
      url: http://atlas:8420/api/summary
      mappings:
        - field: { posture: message }
          label: Posture
        - field: { posture: tunnel }
          label: Tunnel
        - field: { posture: vpn }
          label: VPN
        - field: { posture: routes }
          label: Public routes
```

- [ ] **Step 4: Run tests, commit**

Run: `python -m pytest tests/ -q` → PASS.

```bash
git add atlas/web/ docs/ tests/test_web_render.py
git commit -m "feat(web): posture block in /api/summary for the Homepage tile"
```

---

### Task 13: Deploy to cyberpac + real-infrastructure verification

This task changes a live host. Every host change is backed up first and mirrored into homelab-ops. Steps marked **(user)** need sudo or a secret only the user has; do not attempt them.

- [ ] **Step 1 (user): enable byte accounting, persistently**

```bash
echo 'net.netfilter.nf_conntrack_acct = 1' | sudo tee /etc/sysctl.d/90-atlas-conntrack.conf
sudo sysctl --system | grep conntrack_acct
```

Expected: `net.netfilter.nf_conntrack_acct = 1`.

- [ ] **Step 2: CrowdSec bouncer key** (sentinel is in the docker group)

```bash
ssh 192.168.10.157 'docker exec crowdsec cscli bouncers add atlas-posture -o raw'
```

Copy the printed key straight into `~/atlas/atlas.yaml` (Step 4) on the host - never into chat, git or logs.

- [ ] **Step 3 (user decides): gluetun API key** - add a role to gluetun's `HTTP_CONTROL_SERVER_AUTH_CONFIG_FILEPATH` file allowing `GET /v1/publicip/ip` with an `apikey` auth (back up the file first; gluetun docs: control-server auth `roles` with `auth = "apikey"`), restart gluetun only with the user's OK (it briefly drops qBittorrent's VPN).

- [ ] **Step 4: Atlas config + override on cyberpac** (back up both: `cp atlas.yaml atlas.yaml.bak-posture-$(date +%Y%m%d)`, same for the override)

Add to `~/atlas/atlas.yaml`:

```yaml
posture:
  enabled: true
  host_ip: 192.168.10.157
  gluetun_api_key: <from step 3>
  crowdsec_api_key: <from step 2>
  traefik_dynamic_dir: /traefik-dynamic
```

In `~/atlas/docker-compose.override.yml` `atlas-scan`: add the read-only dynamic-config mount (the base file now supplies `cap_add: NET_ADMIN` and the command):

```yaml
    volumes:
      - ./data/inventory:/data/inventory
      - ./data/reports:/data/reports
      - ./data/logs:/data/logs
      - /home/sentinel/vulcan/stack/config/traefik/dynamic:/traefik-dynamic:ro
```

Copy the override into homelab-ops `cyberpac/atlas/docker-compose.override.yml` (secrets live only in atlas.yaml, which is not mirrored).

- [ ] **Step 5: Roll out** after the PRs are merged and the GHCR image built (`gh run list --workflow image.yml -L 1` shows success):

```bash
ssh 192.168.10.157 'cd ~/atlas && docker compose pull && docker compose up -d atlas atlas-scan && sleep 60 && docker logs --tail 20 atlas-scan'
```

- [ ] **Step 6: Verify against real infrastructure** (all must hold before calling Phase 1 done):

```bash
ssh 192.168.10.157 'docker exec atlas-scan atlas posture watch --once --json'
```

Expected: `"flows"` > 100 and `"deltas"` > 0.

```bash
ssh 192.168.10.157 'docker exec atlas python -c "
import json,urllib.request
d=json.load(urllib.request.urlopen(\"http://127.0.0.1:8420/api/posture?window=1h\"))
print({s[\"key\"]:(s[\"state\"],s[\"value\"]) for s in d[\"strip\"]}); print(len(d[\"nodes\"]), len(d[\"exposure\"]))"'
```

Check each against ground truth:
- conntrack: `docker run --rm --net host --cap-add NET_ADMIN atlas-image conntrack -C` count is in the same range as `posture_status.conntrack.flows`.
- routes: `jellyfin` shows `public`, `atlas` shows `authelia` (matches the override labels above).
- VPN: `docker exec gluetun wget -qO- http://127.0.0.1:8000/v1/publicip/ip` (with the key) equals the strip's exit IP, and differs from `curl -s https://api.ipify.org` on the host.
- CrowdSec: `docker exec crowdsec cscli decisions list -o raw | tail -n +2 | wc -l` equals the Blocked value.
- Tile: `curl -s http://127.0.0.1:8420/api/summary | jq .posture` (from inside the atlas container) has `state` and `message`; then update Homepage `services.yaml` on cyberpac (backup `.bak-atlas-posture-<date>`) with the Task 12 mappings, mirror to homelab-ops, and check the tile in a browser in both states (force `review` by marking nothing expected right after first deploy - every destination starts as new).

- [ ] **Step 7: Open https://atlas.totallylegitmedia.us/** and walk the Task 10/11 manual checks on real data. Record results (counts, the IPs compared, screenshots if the user wants them) in the PR description of the last PR, then update `docs/` deployment notes with the `nf_conntrack_acct`, `NET_ADMIN`, bouncer-key and gluetun-key steps.

- [ ] **Step 8: Commit docs + push the homelab-ops mirror (with the user's OK)**

```bash
git add docs/
git commit -m "docs: posture collector deployment (conntrack accounting, NET_ADMIN, keys)"
```

---

## Self-Review Notes

- Spec coverage: data sources (Tasks 2-5, 7), aggregator/new-destination (6), storage + retention (1, 7), failure greying (7 statuses, 8 bands/strip), shell + nav fold-in (9), map + panel + Mark as expected (8, 10), chat drawer (11), tile + summary (12), security constraints (Global Constraints, 7, 8), real-infra verification (13). Out-of-scope items (Claude chat, digest, external scan, DNS names) have no tasks by design.
- Spec deviations, deliberate: (1) Traefik routes come from Docker labels + the file-provider directory instead of the Traefik API (the API has no internal entrypoint on cyberpac; this avoids exposing it). (2) Protection is `authelia` / `public` - Authelia's per-domain 1FA/2FA policy isn't read, so the UI says "Authelia", not "2FA". (3) "Blocked 24 h" is "active CrowdSec bans" (the LAPI decisions endpoint returns active decisions, not a 24 h history). (4) The VPN band shows gluetun's tunnel, not BitTorrent peers - flows inside gluetun's network namespace are invisible to the host's conntrack. (5) `atlas posture watch` is a long-running loop inside atlas-scan (the existing loop already runs forever there); it is still an explicit, visible command (rerun 30 s after it exits by a `while :` loop in atlas-scan). (6) The tile's `link` is always "/" (no `?node=`), and the summary field is `blocked`, not `blocked_24h`. (7) Clicking a strip chip does not highlight bands; the chips are plain status cards. (8) ASN groups don't expand on click - the direct band shows the top 10 destinations (plus any under review) and one "Other destinations" box. (9) Stale bands say "no recent data", not "no data since HH:MM". (10) Tunnel health is counted from conntrack flows from cloudflared to :7844, not cloudflared's metrics endpoint. (11) Routes are not filtered by entrypoint, so LAN-only routers count toward exposure. (12) Live refresh redraws the map, so zoom/pan reset every 30 s. (13) posture_seen's first 24 h are a learning baseline (no review items), and no first-seen rows are recorded while the ASN table is empty - both avoid a review flood on a fresh deploy. (14) The "live" window is labelled "This hour" (it is the current hourly bucket); the API value stays `live`.
- Type/name consistency checked: status source names (`conntrack, tunnel, inbound, routes, gluetun, public_ip, crowdsec, asn`), node id scheme, `asn_key` format, delta dict keys, `build_posture` keys and `build_summary(..., posture)` all match across tasks.
