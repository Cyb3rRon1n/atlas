"""
One wired-map pass: collect every source on its own, fall back to a failed
source's last good raw input (marked stale), build, save. Shared by
`atlas wiring scan` and the web Refresh button; a module lock keeps two
clicks (or a click during a CLI run in the same process) from overlapping.
"""

import os
import threading
from datetime import datetime

from atlas.wiring import WiringError
from atlas.wiring.build import build_wiring
from atlas.wiring.cabling import load_cabling
from atlas.wiring.snmp import collect_switch
from atlas.wiring.unifi import fetch_unifi


_LOCK = threading.Lock()


class WiringBusy(Exception):
    """A scan is already running."""


def run_scan(settings, store, devices, env=None, now=None, collect=collect_switch, fetch=fetch_unifi):

    if not _LOCK.acquire(blocking=False):
        raise WiringBusy()

    try:
        env = os.environ if env is None else env
        config = settings.wiring
        previous = store.latest(1)
        old_raw = previous[0]["raw"] if previous else {"switches": {}, "unifi": None}
        raw = {"switches": {}, "unifi": None}
        sources = {}

        for switch in config.switches:
            try:
                raw["switches"][switch.name] = collect(switch, env, config.timeout)
                sources[switch.name] = {"ok": True, "error": "", "stale": False,
                                        "note": "weak privacy (DES)" if switch.priv == "des" else ""}
            except WiringError as error:
                old = (old_raw.get("switches") or {}).get(switch.name)
                if old:
                    raw["switches"][switch.name] = old
                sources[switch.name] = {"ok": False, "error": str(error), "stale": bool(old), "note": ""}

        if config.unifi.enabled:
            try:
                raw["unifi"] = fetch(config.unifi, env, config.timeout)
                sources["unifi"] = {"ok": True, "error": "", "stale": False, "note": ""}
            except WiringError as error:
                raw["unifi"] = old_raw.get("unifi")
                sources["unifi"] = {"ok": False, "error": str(error), "stale": raw["unifi"] is not None, "note": ""}

        snapshot = build_wiring(list(raw["switches"].values()), raw["unifi"], devices,
                                load_cabling(config.cabling_file))
        taken_at = now or datetime.utcnow()
        store.save(snapshot, raw, sources, taken_at, keep=config.keep_snapshots)

        return {"taken_at": taken_at, "snapshot": snapshot, "sources": sources}

    finally:
        _LOCK.release()
