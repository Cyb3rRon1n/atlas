# Device Triage in the Web UI — Implementation Plan (PR 2 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin act on the device inventory from the atlas web UI. That means a **Triage** tab (name/keep, merge, ignore), a **Devices** tab (search list plus a per-device edit page with merge and split), a **Coverage** tab (per-source health, quiet devices, invisible devices), and Homepage counts, all through atlas's first write endpoints behind a same-origin check.

**Architecture:**
- **Store:** `InventoryStore` (PR 1) gains validation and merge/split/triage/coverage methods.
- **API:** a new `atlas/web/api.py` maps `/api/*` device routes onto the store and publishes events.
- **Server:** `atlas/web/server.py` gains `do_POST` with the security gate.
- **Pages:** a new `atlas/web/devices_pages.py` renders the three tabs and the device page as server-rendered HTML, plus one small inline script that POSTs JSON. There is no build step and no new dependency.

**Tech Stack:** Python stdlib `http.server`, SQLAlchemy 2.0 (existing), vanilla JS `fetch`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-29-network-inventory-design.md`. This plan covers delivery step 2. Map v2, the side panel and chat come in later plans.

## Global Constraints

- No new dependency. The web server stays on stdlib `http.server`.
- Every POST needs a same-origin check. It passes if `Sec-Fetch-Site: same-origin`, or if the `Origin` (fallback `Referer`) netloc equals the `Host` header. Anything else gets **403**. That includes a request with none of these headers.
- POST bodies are capped at **65536 bytes** (413 when larger) and must be JSON (400 otherwise).
- Store methods return plain dicts and never raise for expected failures: `{"found": False}` for a missing id, `{"found": True, "error": "..."}` for a validation failure. The API maps these to 404 and 400.
- Every successful write publishes an event with source `"AtlasWeb"`: `atlas.devices.updated`, `atlas.devices.merged`, `atlas.devices.split`.
- Every interpolated value in HTML goes through `html.escape` (`_esc`). The JS never uses `innerHTML` with data. It reads `data-*` attributes and sets `textContent` only.
- Valid values: `STATES = ("new", "known", "ignored")`. `KINDS = ("server", "vm", "lxc", "container-host", "workstation", "phone", "tv", "iot", "network", "other")`.
- Tests assert shape and logic, never the machine's state. Commits carry no AI-attribution trailer. Code follows the repo's heavy vertical spacing style.
- Run tests with `.venv/bin/python -m pytest tests/ -q` from the repo root.

## File Structure

| File | Responsibility |
|---|---|
| `atlas/devices/store.py` (modify) | validated `set_fields`, `merge`, `split`, `device`, `triage`, `coverage`; `_ok_runs` limited to the last 2 per source |
| `atlas/web/api.py` (create) | `handle(method, path, body) -> (status, payload) or None` for the `/api/*` device routes, plus event publishing |
| `atlas/web/server.py` (modify) | `do_POST` with the same-origin check, body cap and JSON parsing; the new GET page and API routes; summary counts |
| `atlas/web/render.py` (modify) | nav links, form/button CSS, `build_summary(topology, devices=())` counts |
| `atlas/web/devices_pages.py` (create) | `render_triage_page`, `render_devices_page`, `render_device_page`, `render_coverage_page`, `ACTIONS_SCRIPT` |
| `tests/test_devices_store_edits.py`, `tests/test_web_api.py`, `tests/test_web_devices_pages.py` (create); `tests/test_web_server.py` (modify) | tests |
| `docs/cli-reference.md`, `README.md` (modify) | docs |

---

### Task 1: Store edits, merge, split, triage, coverage

**Files:**
- Modify: `atlas/devices/store.py`
- Test: `tests/test_devices_store_edits.py`

**Interfaces:**
- Produces:
  - `KINDS`, `STATES` (module constants).
  - `set_fields(device_id, fields, now=None) -> {"found": bool, "error"?: str}`. This validates every field first and applies nothing if any field is invalid. Setting state to known or ignored clears `suggested_merge_id`.
  - `merge(device_id, into_id, now=None) -> {"found", "error"?, "device_id"?}`.
  - `split(sighting_id, now=None) -> {"found", "error"?, "device_id"?}`.
  - `device(device_id) -> dict | None`, in the same shape as a `devices()` item.
  - `triage() -> {"new": [device + "suggested_merge_name"], "quiet": [device]}`.
  - `coverage() -> {"sources": [{"source", "last_run", "ok", "error", "seen_count", "last_ok"}], "quiet": [device], "invisible": [device]}`.

- [ ] **Step 1: Write the failing test** in `tests/test_devices_store_edits.py`

```python
from datetime import datetime, timedelta

from atlas.config.models import MapHost
from atlas.devices import Sighting
from atlas.devices.store import KINDS, InventoryStore


T0 = datetime(2026, 9, 30, 12, 0)


def at(minutes):

    return T0 + timedelta(minutes=minutes)


def seeded(temp_db):
    """mediabox (known: manual + lan) and a proxmox guest suggested into it, plus a new phone."""

    store = InventoryStore(temp_db)
    store.import_manual_hosts([MapHost(name="mediabox", address="192.168.10.57")], now=T0)
    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57"),
                             Sighting("lan", "aa:88", ip="192.168.10.88", mac="aa:88", hostname="pixel.lan")], now=at(0))
    store.record_run("proxmox", [Sighting("proxmox", "pve:200", hostname="mediabox", detail={"type": "lxc"})], now=at(0))

    devices = store.devices()  # a list: the guest and the known device are both named "mediabox"
    known = next(d for d in devices if d["state"] == "known")
    guest = next(d for d in devices if d["suggested_merge_id"] == known["id"])
    phone = next(d for d in devices if d["name"] == "pixel")

    return store, known, guest, phone


def test_set_fields_validates_everything_before_applying(temp_db):

    store, known, guest, phone = seeded(temp_db)

    assert store.set_fields(phone["id"], {"name": "Pixel 7", "kind": "toaster"}) == \
        {"found": True, "error": f"kind must be one of: {', '.join(KINDS)}"}
    assert store.device(phone["id"])["name"] == "pixel"

    for bad in ({"name": "  "}, {"state": "gone"}, {"important": "yes"}, {"tags": "a,b"},
                {"tags": ["x" * 33]}, {"notes": "n" * 2001}, {"id": 5}):
        assert "error" in store.set_fields(phone["id"], bad), bad

    assert store.set_fields(999, {"name": "x"}) == {"found": False}


def test_set_fields_applies_locks_and_clears_suggestion_when_triaged(temp_db):

    store, known, guest, phone = seeded(temp_db)

    assert store.set_fields(phone["id"], {"name": " Pixel 7 ", "kind": "phone", "tags": ["family"],
                                          "important": True, "state": "known"}) == {"found": True}
    phone = store.device(phone["id"])
    assert (phone["name"], phone["kind"], phone["tags"], phone["important"], phone["state"]) == \
        ("Pixel 7", "phone", ["family"], True, "known")

    store.set_fields(guest["id"], {"state": "ignored"})
    assert store.device(guest["id"])["suggested_merge_id"] is None


def test_merge_moves_sightings_and_notifications_and_deletes_source(temp_db):

    store, known, guest, phone = seeded(temp_db)
    store.record_run("lan", [Sighting("lan", "aa:99", ip="192.168.10.99", mac="aa:99")], now=at(15))
    newcomer = next(d for d in store.devices() if d["ip"] == "192.168.10.99")

    assert store.merge(guest["id"], known["id"]) == {"found": True, "device_id": known["id"]}
    assert store.device(guest["id"]) is None
    assert {s["source"] for s in store.device(known["id"])["sightings"]} == {"manual", "lan", "proxmox"}

    # newcomer's queued "new" alert moves with it, so it now names the phone
    assert store.merge(newcomer["id"], phone["id"])["device_id"] == phone["id"]
    assert [item["device"] for item in store.due_notifications(now=at(15))["new"]] == ["pixel"]

    assert store.merge(known["id"], known["id"]) == {"found": True, "error": "can't merge a device into itself"}
    assert store.merge(12345, known["id"]) == {"found": False}


def test_split_makes_a_new_device_but_never_empties_one(temp_db):

    store, known, guest, phone = seeded(temp_db)
    lan = next(s for s in store.device(known["id"])["sightings"] if s["source"] == "lan")

    result = store.split(lan["id"])
    assert result["found"] is True and result["device_id"] != known["id"]
    assert store.device(result["device_id"])["state"] == "new"
    assert [s["source"] for s in store.device(known["id"])["sightings"]] == ["manual"]

    only = store.device(phone["id"])["sightings"][0]
    assert store.split(only["id"]) == {"found": True, "error": "that's the device's only sighting"}
    assert store.split(99999) == {"found": False}


def test_triage_lists_new_with_suggestion_names_and_quiet_known(temp_db):

    store, known, guest, phone = seeded(temp_db)
    store.set_fields(phone["id"], {"state": "known"})
    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")], now=at(15))
    store.record_run("lan", [Sighting("lan", "aa:57", ip="192.168.10.57", mac="aa:57")], now=at(30))

    triage = store.triage()

    assert [(d["name"], d["suggested_merge_name"]) for d in triage["new"]] == [("mediabox", "mediabox")]
    assert [d["name"] for d in triage["quiet"]] == ["pixel"]


def test_coverage_reports_each_source_and_quiet_invisible(temp_db):

    store, known, guest, phone = seeded(temp_db)
    store.import_manual_hosts([MapHost(name="garage-tv", address="192.168.10.224")], now=at(1))
    store.record_run("proxmox", [], ok=False, error="could not connect to Proxmox", now=at(15))

    coverage = store.coverage()
    sources = {s["source"]: s for s in coverage["sources"]}

    assert sources["proxmox"]["ok"] is False
    assert sources["proxmox"]["error"] == "could not connect to Proxmox"
    assert sources["proxmox"]["last_ok"] == at(0).isoformat()
    assert sources["lan"]["ok"] is True and sources["lan"]["seen_count"] == 2
    assert [d["name"] for d in coverage["invisible"]] == ["garage-tv"]
    assert coverage["quiet"] == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_devices_store_edits.py -q`
Expected: FAIL (ImportError: `KINDS`).

- [ ] **Step 3: Implement.** In `atlas/devices/store.py`:

Change the sqlalchemy import to `from sqlalchemy import func, select`, then add these constants next to `EDITABLE`:

```python
KINDS = ("server", "vm", "lxc", "container-host", "workstation", "phone", "tv", "iot", "network", "other")

STATES = ("new", "known", "ignored")


def _validate(fields):
    """First problem with an edit, or None. Checked before anything is applied."""

    for key, value in fields.items():

        if key not in EDITABLE:
            return f"{key} can't be edited"

        if key == "name" and not (isinstance(value, str) and value.strip() and len(value.strip()) <= 64):
            return "name must be 1-64 characters"

        if key == "kind" and value not in KINDS:
            return f"kind must be one of: {', '.join(KINDS)}"

        if key == "state" and value not in STATES:
            return f"state must be one of: {', '.join(STATES)}"

        if key == "important" and not isinstance(value, bool):
            return "important must be true or false"

        if key == "notes" and not (isinstance(value, str) and len(value) <= 2000):
            return "notes must be text, at most 2000 characters"

        if key == "tags" and not (isinstance(value, list) and len(value) <= 20
                                  and all(isinstance(tag, str) and 0 < len(tag) <= 32 for tag in value)):
            return "tags must be a list of up to 20 tags, each 1-32 characters"

    return None
```

Replace `set_fields` with:

```python
    def set_fields(self, device_id, fields, now=None):
        """Operator edit: all-or-nothing validation, then applies and locks each field it sets."""

        error = _validate(fields)

        with Session(self.engine) as session:

            device = session.get(DeviceRecord, device_id)

            if device is None:
                return {"found": False}

            if error:
                return {"found": True, "error": error}

            locked = set(json.loads(device.locked_fields))

            for key, value in fields.items():

                if key == "tags":
                    value = json.dumps(value)
                elif key == "name":
                    value = value.strip()

                setattr(device, key, value)
                locked.add(key)

            # Triaging a device (keep or ignore) answers its merge suggestion.
            if fields.get("state") in ("known", "ignored"):
                device.suggested_merge_id = None

            device.locked_fields = json.dumps(sorted(locked))
            device.updated_at = now or datetime.utcnow()
            session.commit()

        return {"found": True}
```

Replace `_ok_runs` (status only ever needs each source's last two successful runs):

```python
    def _ok_runs(self, session):

        runs = {}

        for source in session.scalars(select(SourceRunRecord.source).distinct()):
            runs[source] = list(session.scalars(
                select(SourceRunRecord.started_at)
                .where(SourceRunRecord.source == source, SourceRunRecord.ok.is_(True))
                .order_by(SourceRunRecord.started_at.desc()).limit(2)))

        return runs
```

Add these methods after `set_fields`:

```python
    def device(self, device_id):

        return next((device for device in self.devices() if device["id"] == device_id), None)

    def merge(self, device_id, into_id, now=None):
        """Operator merge: every sighting and queued alert moves to into_id, the empty device goes."""

        if device_id == into_id:
            return {"found": True, "error": "can't merge a device into itself"}

        with Session(self.engine) as session:

            source, target = session.get(DeviceRecord, device_id), session.get(DeviceRecord, into_id)

            if source is None or target is None:
                return {"found": False}

            for row in session.scalars(select(SightingRecord).where(SightingRecord.device_id == device_id)).all():
                row.device_id = into_id

            for note in session.scalars(select(NotificationRecord)
                                        .where(NotificationRecord.device_id == device_id)).all():
                note.device_id = into_id

            for other in session.scalars(select(DeviceRecord)
                                         .where(DeviceRecord.suggested_merge_id == device_id)).all():
                other.suggested_merge_id = None if other.id == into_id else into_id

            target.updated_at = now or datetime.utcnow()
            session.delete(source)
            session.commit()

        return {"found": True, "device_id": into_id}

    def split(self, sighting_id, now=None):
        """Operator split: one sighting becomes its own new device (lands in Triage)."""

        now = now or datetime.utcnow()

        with Session(self.engine) as session:

            row = session.get(SightingRecord, sighting_id)

            if row is None:
                return {"found": False}

            siblings = session.scalar(select(func.count()).select_from(SightingRecord)
                                      .where(SightingRecord.device_id == row.device_id))

            if siblings < 2:
                return {"found": True, "error": "that's the device's only sighting"}

            device = DeviceRecord(name=(row.hostname or "").split(".")[0] or row.ip or row.external_id,
                                  created_at=now, updated_at=now)
            session.add(device)
            session.flush()
            row.device_id = device.id
            session.commit()

            return {"found": True, "device_id": device.id}

    def triage(self):

        devices = self.devices()
        names = {device["id"]: device["name"] for device in devices}

        return {
            "new": [{**device, "suggested_merge_name": names.get(device["suggested_merge_id"])}
                    for device in devices if device["state"] == "new"],
            "quiet": [device for device in devices if device["state"] == "known" and device["status"] == "quiet"],
        }

    def coverage(self):

        with Session(self.engine) as session:

            sources = []

            for source in sorted(session.scalars(select(SourceRunRecord.source).distinct())):

                latest = session.scalar(select(SourceRunRecord).where(SourceRunRecord.source == source)
                                        .order_by(SourceRunRecord.started_at.desc()).limit(1))
                last_ok = session.scalar(select(SourceRunRecord.started_at)
                                         .where(SourceRunRecord.source == source, SourceRunRecord.ok.is_(True))
                                         .order_by(SourceRunRecord.started_at.desc()).limit(1))

                sources.append({"source": source, "last_run": _iso(latest.started_at), "ok": latest.ok,
                                "error": latest.error, "seen_count": latest.seen_count, "last_ok": _iso(last_ok)})

        devices = [device for device in self.devices() if device["state"] != "ignored"]

        return {
            "sources": sources,
            "quiet": [device for device in devices if device["status"] == "quiet"],
            "invisible": [device for device in devices if device["status"] == "invisible"],
        }
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_devices_store_edits.py tests/ -q`
Expected: all pass. PR 1's store tests still pass: they only pass editable keys with valid values.

- [ ] **Step 5: Commit**

```bash
git add atlas/devices/store.py tests/test_devices_store_edits.py
git commit -m "feat(devices): validated edits, merge, split, triage and coverage views"
```

---

### Task 2: JSON API (`atlas/web/api.py`)

**Files:**
- Create: `atlas/web/api.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: the `InventoryStore` methods from Task 1.
- Produces: `handle(method: str, path: str, body=None) -> tuple[int, object] | None`. It returns `None` when the path isn't a device API route. The routes are:
  - `GET /api/devices`
  - `GET /api/devices/<id>`
  - `GET /api/triage`
  - `GET /api/coverage`
  - `POST /api/devices/<id>` (edit)
  - `POST /api/devices/<id>/merge` with `{"into": int}`
  - `POST /api/sightings/<id>/split`

  On success a POST returns `(200, {"ok": True, ...result minus "found"})`, publishes its event, and never raises.

- [ ] **Step 1: Write the failing test** in `tests/test_web_api.py`

```python
from atlas.devices import Sighting
from atlas.devices.store import InventoryStore
from atlas.knowledge.queries import KnowledgeQueries
from atlas.web import api


def two_devices():

    store = InventoryStore()
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01", hostname="router"),
                             Sighting("lan", "aa:02", ip="192.168.10.2", mac="aa:02")])

    return {d["name"]: d["id"] for d in store.devices()}


def test_get_routes(temp_db):

    ids = two_devices()

    status, devices = api.handle("GET", "/api/devices")
    assert status == 200 and {d["name"] for d in devices} == {"router", "192.168.10.2"}
    assert api.handle("GET", f"/api/devices/{ids['router']}")[1]["name"] == "router"
    assert api.handle("GET", "/api/devices/999") == (404, {"error": "not found"})
    assert set(api.handle("GET", "/api/triage")[1]) == {"new", "quiet"}
    assert set(api.handle("GET", "/api/coverage")[1]) == {"sources", "quiet", "invisible"}
    assert api.handle("GET", "/api/summary") is None
    assert api.handle("GET", "/nope") is None


def test_edit_publishes_event_and_maps_errors(temp_db):

    ids = two_devices()

    assert api.handle("POST", f"/api/devices/{ids['router']}", {"name": "UniFi", "kind": "network"}) == (200, {"ok": True})
    assert InventoryStore().device(ids["router"])["name"] == "UniFi"
    assert KnowledgeQueries().recent_events(5)[0]["event_type"] == "atlas.devices.updated"

    status, payload = api.handle("POST", f"/api/devices/{ids['router']}", {"kind": "toaster"})
    assert status == 400 and "kind must be one of" in payload["error"]
    assert api.handle("POST", "/api/devices/999", {"name": "x"}) == (404, {"error": "not found"})
    assert api.handle("POST", f"/api/devices/{ids['router']}", ["not", "an", "object"]) == \
        (400, {"error": "expected a JSON object"})


def test_merge_and_split(temp_db):

    ids = two_devices()
    router, other = ids["router"], ids["192.168.10.2"]

    assert api.handle("POST", f"/api/devices/{other}/merge", {"into": True}) == (400, {"error": "into must be a device id"})
    assert api.handle("POST", f"/api/devices/{other}/merge", {"into": router}) == (200, {"ok": True, "device_id": router})
    assert KnowledgeQueries().recent_events(5)[0]["event_type"] == "atlas.devices.merged"

    sighting = InventoryStore().device(router)["sightings"][-1]["id"]
    status, payload = api.handle("POST", f"/api/sightings/{sighting}/split", {})
    assert status == 200 and payload["ok"] is True and payload["device_id"] != router
    assert KnowledgeQueries().recent_events(5)[0]["event_type"] == "atlas.devices.split"
    assert api.handle("POST", "/api/other", {}) is None
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_web_api.py -q`
Expected: FAIL (ImportError `atlas.web.api`).

Before implementing, check `KnowledgeQueries.recent_events` returns dicts with an `event_type` key, newest first. If it returns objects instead, adapt the three assertions to that shape and note it in your report.

- [ ] **Step 3: Implement** `atlas/web/api.py`

```python
"""
The inventory's JSON API for atlas web: plain (status, payload) results,
so the HTTP layer (server.py) owns sockets and headers and this module
owns only routing, validation mapping and events. Writes go through
InventoryStore, and every successful one is published as an event, the
same persistence path as every other atlas state change.
"""

import re

from atlas.core.application import application
from atlas.devices.store import InventoryStore
from atlas.events import AtlasEvent


DEVICE = re.compile(r"^/api/devices/(\d+)$")

MERGE = re.compile(r"^/api/devices/(\d+)/merge$")

SPLIT = re.compile(r"^/api/sightings/(\d+)/split$")

NOT_FOUND = (404, {"error": "not found"})


def _result(result, event_type, payload):

    if not result.get("found"):
        return NOT_FOUND

    if result.get("error"):
        return 400, {"error": result["error"]}

    application.runtime.events.publish(AtlasEvent(event_type=event_type, source="AtlasWeb", payload=payload))

    return 200, {"ok": True, **{key: value for key, value in result.items() if key != "found"}}


def _get(path):

    store = InventoryStore()

    if path == "/api/devices":
        return 200, store.devices()

    if path == "/api/triage":
        return 200, store.triage()

    if path == "/api/coverage":
        return 200, store.coverage()

    match = DEVICE.match(path)

    if match:
        device = store.device(int(match.group(1)))
        return (200, device) if device else NOT_FOUND

    return None


def _post(path, body):

    if not any(pattern.match(path) for pattern in (DEVICE, MERGE, SPLIT)):
        return None

    if not isinstance(body, dict):
        return 400, {"error": "expected a JSON object"}

    store = InventoryStore()
    match = DEVICE.match(path)

    if match:
        device_id = int(match.group(1))
        return _result(store.set_fields(device_id, body), "atlas.devices.updated",
                       {"device_id": device_id, "fields": body})

    match = MERGE.match(path)

    if match:

        into = body.get("into")

        if isinstance(into, bool) or not isinstance(into, int):
            return 400, {"error": "into must be a device id"}

        device_id = int(match.group(1))
        return _result(store.merge(device_id, into), "atlas.devices.merged", {"device_id": device_id, "into": into})

    sighting_id = int(SPLIT.match(path).group(1))

    return _result(store.split(sighting_id), "atlas.devices.split", {"sighting_id": sighting_id})


def handle(method, path, body=None):

    if method == "GET":
        return _get(path)

    if method == "POST":
        return _post(path, body)

    return None
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/test_web_api.py tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/api.py tests/test_web_api.py
git commit -m "feat(web): JSON API for the device inventory - list, edit, merge, split, triage, coverage"
```

---

### Task 3: Server write path, routes and summary counts

**Files:**
- Modify: `atlas/web/server.py`, `atlas/web/render.py` (only `build_summary`)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `api.handle` (Task 2), `InventoryStore().devices()`.
- Produces:
  - `AtlasWebHandler.do_POST`.
  - GET `/api/*` delegated to `api.handle`.
  - GET page routes `/triage`, `/devices`, `/devices/<id>` and `/coverage`. These call the Task 4 renderers. Until Task 4 lands, have them return a 501 plain-text placeholder: Task 4 replaces those four lines.
  - `build_summary(topology, devices=())` adds `to_triage` and `devices_quiet`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_web_server.py`:
  - Delete `test_only_get_routes_exist_no_write_path`. The write path now exists deliberately.
  - Add these tests. They reuse the file's `running_server` fixture and `_get` helper.

```python
import json


def _post(url, body, origin=None, raw=None):

    headers = {"Content-Type": "application/json"}

    if origin:
        headers["Origin"] = origin

    data = raw if raw is not None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def _seed_device():

    from atlas.devices import Sighting
    from atlas.devices.store import InventoryStore

    store = InventoryStore()
    store.record_run("lan", [Sighting("lan", "aa:01", ip="192.168.10.1", mac="aa:01", hostname="router")])

    return store, store.devices()[0]["id"]


def test_post_requires_same_origin(running_server):

    store, device_id = _seed_device()
    url = f"{running_server}/api/devices/{device_id}"

    assert _post(url, {"name": "x"})[0] == 403
    assert _post(url, {"name": "x"}, origin="https://evil.example")[0] == 403
    assert store.device(device_id)["name"] == "router"

    assert _post(url, {"name": "UniFi"}, origin=running_server) == (200, {"ok": True})
    assert store.device(device_id)["name"] == "UniFi"


def test_post_rejects_bad_json_big_bodies_and_unknown_paths(running_server):

    store, device_id = _seed_device()
    url = f"{running_server}/api/devices/{device_id}"

    assert _post(url, None, origin=running_server, raw=b"{nope")[0] == 400
    assert _post(f"{running_server}/api/whatever", {}, origin=running_server)[0] == 404

    # Oversized: send only the headers - the server must refuse on Content-Length alone,
    # without reading (a real body would race the early 413 and reset the connection).
    import http.client
    from urllib.parse import urlsplit
    connection = http.client.HTTPConnection(urlsplit(running_server).netloc, timeout=5)
    connection.putrequest("POST", f"/api/devices/{device_id}")
    connection.putheader("Origin", running_server)
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "70000")
    connection.endheaders()
    assert connection.getresponse().status == 413
    connection.close()


def test_api_get_and_summary_counts(running_server):

    _seed_device()

    status, body = _get(running_server + "/api/devices")
    assert status == 200 and json.loads(body)[0]["name"] == "router"

    summary = json.loads(_get(running_server + "/api/summary")[1])
    assert summary["to_triage"] == 1 and summary["devices_quiet"] == 0
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -q`
Expected: FAIL (501 or 405 on POST; KeyError `to_triage`).

- [ ] **Step 3: Implement.**

In `atlas/web/render.py`, replace `build_summary`'s signature and returns. Every return gets the two counts:

```python
def build_summary(topology, devices=()):
    """
    One small JSON object for a dashboard tile (e.g. Homepage's customapi
    widget): counts from the latest saved network map and the device
    inventory, plus a single status word. Nothing is queried live.
    """

    counts = {
        "to_triage": sum(device["state"] == "new" or (device["state"] == "known" and device["status"] == "quiet")
                         for device in devices),
        "devices_quiet": sum(device["status"] == "quiet" and device["state"] != "ignored" for device in devices),
    }

    if not topology:
        return {"status": "no map yet - run atlas map", **counts}
```

Then add `**counts` as the last entry of the existing final returned dict.

In `atlas/web/server.py`:
- Update the module docstring. Replace "read-only ... no POST route ... no write path" with this: the server is read-only except for the inventory's `/api/*` POST routes. Those are gated by a same-origin check, capped at 64 KB of JSON, and write only through `InventoryStore`. The Authelia admin rule in front of the host is the auth boundary.
- Add the imports `import re`, `from urllib.parse import urlsplit`, `from atlas.devices.store import InventoryStore` and `from atlas.web import api`.
- Add these module-level items:

```python
MAX_BODY = 65536

DEVICE_PAGE = re.compile(r"^/devices/(\d+)$")


def same_origin(headers):
    """
    Cross-site request forgery guard for the write routes: Authelia's cookie rides along
    on any request the browser makes, so a POST must provably come from atlas's own pages.
    """

    if headers.get("Sec-Fetch-Site") == "same-origin":
        return True

    origin = headers.get("Origin") or headers.get("Referer") or ""
    host = headers.get("Host") or ""

    return bool(origin and host) and urlsplit(origin).netloc == host
```

In `do_GET`, change the `/api/summary` branch to `build_summary(query.latest_topology(), InventoryStore().devices())`. Then insert these branches before the final `else` (404):

```python
        elif path in ("/triage", "/devices", "/coverage") or DEVICE_PAGE.match(path):
            self._send(501, "text/plain; charset=utf-8", "Not implemented yet")  # replaced in Task 4
            return
        elif path.startswith("/api/"):
            result = api.handle("GET", path)
            if result is None:
                self._send(404, "application/json", json.dumps({"error": "not found"}))
            else:
                self._send(result[0], "application/json", json.dumps(result[1]))
            return
```

Add `do_POST` to the class:

```python
    def do_POST(self):

        path = self.path.split("?", 1)[0]

        if not same_origin(self.headers):
            self._send(403, "application/json", json.dumps({"error": "cross-origin request refused"}))
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1

        if length < 0 or length > MAX_BODY:
            self.close_connection = True  # the unread body must not be parsed as a next request
            self._send(413 if length > MAX_BODY else 400, "application/json",
                       json.dumps({"error": "body must be JSON, at most 64 KB"}))
            return

        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            self._send(400, "application/json", json.dumps({"error": "body must be valid JSON"}))
            return

        result = api.handle("POST", path, body)

        if result is None:
            self._send(404, "application/json", json.dumps({"error": "not found"}))
        else:
            self._send(result[0], "application/json", json.dumps(result[1]))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, including the existing `build_summary` tests, because the `devices=()` default keeps them valid.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/server.py atlas/web/render.py tests/test_web_server.py
git commit -m "feat(web): same-origin-gated write path for the inventory API; triage counts in /api/summary"
```

---

### Task 4: Triage, Devices, device and Coverage pages

**Files:**
- Create: `atlas/web/devices_pages.py`
- Modify: `atlas/web/render.py` (nav plus CSS), `atlas/web/server.py` (replace the Task 3 placeholder)
- Test: `tests/test_web_devices_pages.py`

**Interfaces:**
- Consumes: `render_page`, `_esc` (render.py); `KINDS`, `STATES` (store); the store's triage, devices, device and coverage dict shapes (Task 1).
- Produces:
  - `render_triage_page(triage) -> str`
  - `render_devices_page(devices) -> str`
  - `render_device_page(device, devices) -> str`
  - `render_coverage_page(coverage) -> str`
  - `ACTIONS_SCRIPT`

  Every action is a `<button data-post="URL" data-body='JSON'>`. Optional attributes:
  - `data-name-from="<input id>"` copies an input's value into `body.name`.
  - `data-into-from="<select id>"` copies a select's value into `body.into` as an int.
  - `data-form="<form id>"` collects the edit form.
  - `data-after="goto"` navigates to `/devices/<device_id>` from the response instead of reloading.

- [ ] **Step 1: Write the failing test** in `tests/test_web_devices_pages.py`

```python
from atlas.web.devices_pages import (render_coverage_page, render_device_page, render_devices_page,
                                     render_triage_page)


def device(id, name, state="new", status="seen", sightings=None, **extra):

    return {"id": id, "name": name, "kind": "other", "tags": [], "notes": "", "important": False,
            "state": state, "suggested_merge_id": None, "status": status, "ip": f"192.168.10.{id}",
            "last_seen": "2026-09-30T12:00:00",
            "sightings": sightings or [{"id": id * 10, "source": "lan", "external_id": f"aa:{id}",
                                        "ip": f"192.168.10.{id}", "mac": f"aa:{id}", "hostname": None,
                                        "detail": {}, "first_seen": "2026-09-30T11:00:00",
                                        "last_seen": "2026-09-30T12:00:00"}], **extra}


def test_triage_page_has_keep_merge_ignore_and_escapes():

    html = render_triage_page({
        "new": [device(2, "<script>x</script>", suggested_merge_id=1, suggested_merge_name="mediabox")],
        "quiet": [device(3, "pixel", state="known", status="quiet")],
    })

    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert 'data-post="/api/devices/2"' in html and 'data-name-from="name-2"' in html
    assert 'data-post="/api/devices/2/merge"' in html and "Merge into mediabox" in html
    assert "&quot;ignored&quot;" in html
    assert 'href="/devices/3"' in html


def test_empty_triage_says_so():

    assert "Nothing to triage" in render_triage_page({"new": [], "quiet": []})


def test_devices_page_lists_with_filter_box():

    html = render_devices_page([device(1, "mediabox", state="known"), device(2, "pixel")])

    assert 'id="filter"' in html and 'href="/devices/1"' in html and "pixel" in html


def test_device_page_split_only_with_several_sightings_and_merge_targets():

    single = render_device_page(device(1, "pixel"), [device(1, "pixel"), device(2, "router")])
    assert "/split" not in single
    assert '<option value="2">router</option>' in single
    assert '<option value="1">' not in single
    assert 'id="edit"' in single and 'data-form="edit"' in single

    two = device(1, "mediabox", sightings=[device(1, "a")["sightings"][0], device(9, "b")["sightings"][0]])
    assert 'data-post="/api/sightings/10/split"' in render_device_page(two, [two])


def test_coverage_page_shows_source_failures():

    html = render_coverage_page({
        "sources": [{"source": "proxmox", "last_run": "2026-09-30T12:00:00", "ok": False,
                     "error": "could not connect to Proxmox", "seen_count": 0, "last_ok": None}],
        "quiet": [], "invisible": [device(4, "garage-tv", state="known", status="invisible")],
    })

    assert "could not connect to Proxmox" in html and "garage-tv" in html
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_web_devices_pages.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement.**

In `atlas/web/render.py`, change the nav to `Overview | Triage | Devices | Map | Coverage | History | Trends`: add `<a href="/triage">Triage</a>`, `<a href="/devices">Devices</a>` and `<a href="/coverage">Coverage</a>`. Append this CSS to `PAGE_STYLE`:

```css
  button { background: #21262d; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px;
           padding: 0.25rem 0.7rem; margin: 0 0.25rem 0.25rem 0; cursor: pointer; font: inherit; }
  button:hover { border-color: #58a6ff; }
  button.primary { background: #1f6feb; border-color: #1f6feb; }
  input, select, textarea { background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
           border-radius: 6px; padding: 0.25rem 0.5rem; font: inherit; }
  textarea { width: 100%; min-height: 4rem; }
  label { display: block; margin: 0.5rem 0 0.2rem; color: #8b949e; font-size: 0.85rem; }
  .status-seen { color: #3fb950; } .status-quiet { color: #d29922; } .status-invisible { color: #8b949e; }
  #msg { color: #f85149; min-height: 1.2rem; }
```

Create `atlas/web/devices_pages.py`:

```python
"""
Server-rendered pages for the device inventory: Triage, Devices, one device, Coverage.
Pure functions (data in, HTML out) like render.py. Every action is a button whose
data-* attributes say what to POST; ACTIONS_SCRIPT does the fetch and never puts
data into innerHTML.
"""

import json

from atlas.devices.store import KINDS, STATES
from atlas.web.render import _esc, render_page


ACTIONS_SCRIPT = """
<script>
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-post]");
  if (!button) return;
  const body = JSON.parse(button.dataset.body || "{}");
  if (button.dataset.nameFrom) body.name = document.getElementById(button.dataset.nameFrom).value;
  if (button.dataset.intoFrom) body.into = parseInt(document.getElementById(button.dataset.intoFrom).value, 10);
  if (button.dataset.form) {
    const field = (name) => document.getElementById(button.dataset.form).elements.namedItem(name);
    Object.assign(body, {name: field("name").value, kind: field("kind").value, state: field("state").value,
      notes: field("notes").value, important: field("important").checked,
      tags: field("tags").value.split(",").map((tag) => tag.trim()).filter(Boolean)});
  }
  const message = document.getElementById("msg");
  try {
    const response = await fetch(button.dataset.post, {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) { message.textContent = data.error || ("Failed: " + response.status); return; }
    if (button.dataset.after === "goto" && data.device_id) { location.href = "/devices/" + data.device_id; return; }
    location.reload();
  } catch (error) { message.textContent = "Request failed: " + error; }
});
const filter = document.getElementById("filter");
if (filter) filter.addEventListener("input", () => {
  const needle = filter.value.toLowerCase();
  document.querySelectorAll("tr[data-row]").forEach((row) => {
    row.style.display = row.textContent.toLowerCase().includes(needle) ? "" : "none";
  });
});
</script>
"""


def _button(label, url, body=None, css="", **data):

    extra = "".join(f' data-{key.replace("_", "-")}="{_esc(value)}"' for key, value in data.items())

    return (f'<button class="{css}" data-post="{_esc(url)}" data-body="{_esc(json.dumps(body or {}))}"'
            f"{extra}>{_esc(label)}</button>")


def _sources(device):

    return ", ".join(sorted({sighting["source"] for sighting in device["sightings"]}))


def _status(device):

    return f'<span class="status-{_esc(device["status"])}">{_esc(device["status"])}</span>'


def _page(title, body):

    return render_page(title, f'<p id="msg"></p>{body}{ACTIONS_SCRIPT}')


def render_triage_page(triage):

    if not triage["new"] and not triage["quiet"]:
        return _page("Triage", '<p class="muted">Nothing to triage - every device is known or ignored.</p>')

    new_rows = "".join(
        f"<tr><td><input id=\"name-{device['id']}\" value=\"{_esc(device['name'])}\"></td>"
        f"<td>{_esc(device['ip'] or '-')}</td><td>{_esc(_sources(device))}</td>"
        f"<td>{_esc(device['last_seen'] or '-')}</td><td>"
        + _button("Keep", f"/api/devices/{device['id']}", {"state": "known"}, "primary", name_from=f"name-{device['id']}")
        + (_button(f"Merge into {device['suggested_merge_name']}", f"/api/devices/{device['id']}/merge",
                   {"into": device["suggested_merge_id"]}) if device.get("suggested_merge_name") else "")
        + _button("Ignore", f"/api/devices/{device['id']}", {"state": "ignored"})
        + f" <a href=\"/devices/{device['id']}\">details</a></td></tr>"
        for device in triage["new"]
    )

    quiet_rows = "".join(
        f"<tr><td><a href=\"/devices/{device['id']}\">{_esc(device['name'])}</a></td>"
        f"<td>{_esc(device['ip'] or '-')}</td><td>{_esc(device['last_seen'] or '-')}</td><td>"
        + _button("Ignore", f"/api/devices/{device['id']}", {"state": "ignored"}) + "</td></tr>"
        for device in triage["quiet"]
    )

    body = ""

    if new_rows:
        body += ("<div class=\"card\"><h2>New devices</h2><p class=\"muted\">Name it and Keep, merge it into "
                 "the device it duplicates, or Ignore it.</p><table><thead><tr><th>name</th><th>ip</th>"
                 f"<th>seen by</th><th>last seen</th><th></th></tr></thead><tbody>{new_rows}</tbody></table></div>")

    if quiet_rows:
        body += ("<div class=\"card\"><h2>Gone quiet</h2><p class=\"muted\">Known devices no source has seen in "
                 "its last two runs.</p><table><thead><tr><th>name</th><th>ip</th><th>last seen</th><th></th>"
                 f"</tr></thead><tbody>{quiet_rows}</tbody></table></div>")

    return _page("Triage", body)


def render_devices_page(devices):

    rows = "".join(
        f"<tr data-row><td><a href=\"/devices/{device['id']}\">{_esc(device['name'])}</a></td>"
        f"<td>{_status(device)}</td><td>{_esc(device['state'])}</td><td>{_esc(device['kind'])}</td>"
        f"<td>{_esc(device['ip'] or '-')}</td><td>{_esc(', '.join(device['tags']))}</td>"
        f"<td>{_esc(_sources(device))}</td><td>{_esc(device['last_seen'] or '-')}</td></tr>"
        for device in devices
    )

    body = ("<p><input id=\"filter\" placeholder=\"Filter by name, ip, tag, state...\" size=\"40\"></p>"
            "<div class=\"card\"><table><thead><tr><th>name</th><th>status</th><th>state</th><th>kind</th>"
            "<th>ip</th><th>tags</th><th>seen by</th><th>last seen</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")

    return _page(f"Devices ({len(devices)})", body)


def _options(values, selected):

    return "".join(f"<option{' selected' if value == selected else ''}>{_esc(value)}</option>" for value in values)


def render_device_page(device, devices):

    form = (
        f"<form id=\"edit\" onsubmit=\"return false\">"
        f"<label>Name</label><input name=\"name\" value=\"{_esc(device['name'])}\" size=\"40\">"
        f"<label>Kind</label><select name=\"kind\">{_options(KINDS, device['kind'])}</select>"
        f"<label>State</label><select name=\"state\">{_options(STATES, device['state'])}</select>"
        f"<label>Tags (comma separated)</label><input name=\"tags\" value=\"{_esc(', '.join(device['tags']))}\" size=\"40\">"
        f"<label>Notes</label><textarea name=\"notes\">{_esc(device['notes'])}</textarea>"
        f"<label><input type=\"checkbox\" name=\"important\"{' checked' if device['important'] else ''}> "
        "Important - alert me on Signal when it goes quiet</label><p>"
        + _button("Save", f"/api/devices/{device['id']}", {}, "primary", form="edit")
        + "</p></form>"
    )

    several = len(device["sightings"]) > 1
    sighting_rows = "".join(
        f"<tr><td>{_esc(sighting['source'])}</td><td>{_esc(sighting['external_id'])}</td>"
        f"<td>{_esc(sighting['ip'] or '-')}</td><td>{_esc(sighting['mac'] or '-')}</td>"
        f"<td>{_esc(sighting['hostname'] or '-')}</td><td>{_esc(sighting['last_seen'] or '-')}</td><td>"
        + (_button("Split out", f"/api/sightings/{sighting['id']}/split", {}, after="goto") if several else "")
        + "</td></tr>"
        for sighting in device["sightings"]
    )

    others = "".join(f"<option value=\"{other['id']}\">{_esc(other['name'])}</option>"
                     for other in devices if other["id"] != device["id"])
    merge = (f"<p>Merge this device into <select id=\"merge-into\">{others}</select> "
             + _button("Merge", f"/api/devices/{device['id']}/merge", {}, into_from="merge-into", after="goto")
             + "</p>") if others else ""

    body = (
        f"<p>{_status(device)} <span class=\"muted\">- {_esc(device['ip'] or 'no ip')} - last seen "
        f"{_esc(device['last_seen'] or 'never')}</span></p>"
        f"<div class=\"card\"><h2>Details</h2>{form}</div>"
        "<div class=\"card\"><h2>Where atlas saw it</h2><table><thead><tr><th>source</th><th>id</th><th>ip</th>"
        f"<th>mac</th><th>hostname</th><th>last seen</th><th></th></tr></thead><tbody>{sighting_rows}</tbody></table>"
        f"{merge}</div>"
    )

    return _page(device["name"], body)


def render_coverage_page(coverage):

    source_rows = "".join(
        f"<tr><td>{_esc(source['source'])}</td><td>{'ok' if source['ok'] else 'FAILED'}</td>"
        f"<td>{_esc(source['last_run'] or '-')}</td><td>{_esc(source['seen_count'])}</td>"
        f"<td>{_esc(source['last_ok'] or 'never')}</td><td>{_esc(source['error'] or '')}</td></tr>"
        for source in coverage["sources"]
    )

    def listing(devices, empty):
        if not devices:
            return f"<p class=\"muted\">{empty}</p>"
        return "<ul>" + "".join(f"<li><a href=\"/devices/{device['id']}\">{_esc(device['name'])}</a> "
                                f"<span class=\"muted\">{_esc(device['ip'] or '')}</span></li>"
                                for device in devices) + "</ul>"

    body = (
        "<div class=\"card\"><h2>Sources</h2><table><thead><tr><th>source</th><th>last run</th><th>at</th>"
        f"<th>devices seen</th><th>last success</th><th>error</th></tr></thead><tbody>{source_rows}</tbody></table>"
        "<p class=\"muted\">A failed run never makes devices look quiet - they keep their last status.</p></div>"
        f"<div class=\"card\"><h2>Gone quiet</h2>{listing(coverage['quiet'], 'None - everything is being seen.')}</div>"
        "<div class=\"card\"><h2>Known but invisible</h2><p class=\"muted\">In your config, never seen by a scan.</p>"
        f"{listing(coverage['invisible'], 'None.')}</div>"
    )

    return _page("Coverage", body)
```

In `atlas/web/server.py`, add `from atlas.web.devices_pages import render_coverage_page, render_device_page, render_devices_page, render_triage_page`. Replace the Task 3 placeholder branch with:

```python
        elif path == "/triage":
            body = render_triage_page(InventoryStore().triage())
        elif path == "/devices":
            body = render_devices_page(InventoryStore().devices())
        elif path == "/coverage":
            body = render_coverage_page(InventoryStore().coverage())
        elif DEVICE_PAGE.match(path):
            store = InventoryStore()
            device = store.device(int(DEVICE_PAGE.match(path).group(1)))
            if device is None:
                self._send(404, "text/plain; charset=utf-8", "Not found")
                return
            body = render_device_page(device, store.devices())
```

Add one server test to `tests/test_web_server.py`:

```python
def test_device_pages_render(running_server):

    _, device_id = _seed_device()

    for path in ("/triage", "/devices", "/coverage", f"/devices/{device_id}"):
        status, body = _get(running_server + path)
        assert status == 200 and "router" in body, path
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add atlas/web tests/test_web_devices_pages.py tests/test_web_server.py
git commit -m "feat(web): Triage, Devices, device and Coverage pages"
```

---

### Task 5: Docs

**Files:** `docs/cli-reference.md`, `README.md`, `atlas/web/render.py` (module docstring)

- [ ] **Step 1:** Update the `atlas web` row in `docs/cli-reference.md`:
  - It now serves Overview/Triage/Devices/Map/Coverage/History/Trends.
  - It is read-only except for the device inventory's edit/merge/split actions, which are same-origin-gated JSON POSTs.
  - Run it behind an auth proxy (Authelia) whenever it's reachable beyond localhost.
- [ ] **Step 2:** In `README.md`, extend the device-inventory feature line: "... triage new devices, rename/tag/merge them and check coverage in the web UI".
- [ ] **Step 3:** In `atlas/web/render.py`'s module docstring, drop "No form, no POST route, no write path" and say the pages are pure renderers; the write path lives in `api.py` and `server.py`.
- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/ -q`. Expected: all pass. Then commit: `git commit -am "docs: web triage/devices/coverage and the inventory write path"`.

---

### Task 6: Real-infrastructure verification on cyberpac (controller)

- [ ] Build a test image from the branch on cyberpac. Copy the live db to `/tmp/atlas-web-test/`, then run `atlas scan` and `atlas map` into the copy, as in PR 1.
- [ ] Run `atlas web` from the test image on `127.0.0.1:18420` against the copy:
  `docker run -d --name atlas-web-test --network host -u 1000:1000 -v ~/atlas/atlas.yaml:/data/atlas.yaml:ro -v /tmp/atlas-web-test:/data/inventory atlas:triage-test atlas web --host 127.0.0.1 --port 18420`
- [ ] Use curl to check that `/triage`, `/devices`, `/coverage` and one `/devices/<id>` return 200 with real device names, and that `/api/summary` has `to_triage` above 0.
- [ ] Writes:
  - A POST without `Origin` gets 403.
  - A POST with `Origin: http://127.0.0.1:18420` that sets a name returns 200, and the name persists.
  - Merge the mediabox Proxmox guest into mediabox through `/api/devices/<guest>/merge`. mediabox should then show manual, lan and proxmox sightings.
  - Split one back out, then check that `atlas history` in the copy shows the three `atlas.devices.*` events.
- [ ] Clean up: `docker rm -f atlas-web-test`, remove the image and `/tmp/atlas-web-test`, and check out main in `~/atlas`. The live db stays untouched.
