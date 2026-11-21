"""
One wired-map pass: collect every source on its own, fall back to a failed
source's last good raw input (marked stale), build, save. Shared by
`lanxang wiring scan` and the web Refresh button; a module lock keeps two
clicks (or a click during a CLI run in the same process) from overlapping.
"""

import os
import threading
from datetime import datetime

from lanxang.alerts import Text
from lanxang.wiring import WiringError, traffic
from lanxang.wiring.build import build_wiring
from lanxang.wiring.cabling import load_cabling
from lanxang.wiring.health import alerts, assess, name_attached, poe_ports, where
from lanxang.wiring.snmp import collect_switch
from lanxang.wiring.unifi import fetch_unifi
from lanxang.clock import utcnow


_LOCK = threading.Lock()


class WiringBusy(Exception):
    """A scan is already running."""


def _send(settings, text, send, store=None):

    from lanxang.alerts import allowed
    if not allowed(store, text):
        return

    from lanxang import notify

    if send:
        send(text)
    elif notify.configured(settings.notify):
        notify.send(settings.notify, text)


def run_scan(settings, store, devices, env=None, now=None, collect=collect_switch, fetch=fetch_unifi, send=None):

    if not _LOCK.acquire(blocking=False):
        raise WiringBusy()

    try:
        env = os.environ if env is None else env
        config = settings.wiring
        history = store.latest(config.keep_snapshots)
        previous = history[:1]
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
            if sources["unifi"]["ok"]:
                try:                               # UniFi's names and Wi-Fi details help identify devices
                    from lanxang.devices.store import InventoryStore
                    from lanxang.wiring.unifi import sightings
                    InventoryStore(getattr(store, "engine", None)).record_run("unifi", sightings(raw["unifi"]))
                except Exception:
                    pass                           # the map never fails over the device list

        snapshot = build_wiring(list(raw["switches"].values()), raw["unifi"], devices,
                                load_cabling(config.cabling_file))

        # cable health: this scan's counters against the earlier scans (stale sources have nothing new)
        stale = {name for name, source in sources.items() if not source["ok"]}
        if "unifi" in stale:
            stale |= {d.get("name") for d in ((raw["unifi"] or {}).get("devices") or [])}
        snapshot["health"] = name_attached(assess(raw, [h["raw"] for h in history], stale), snapshot)
        snapshot["poe"] = poe_ports(raw)
        taken_at = now or utcnow()
        if previous:                                # per-port traffic since the last scan, for the map and graphs
            found = traffic.rates(raw, old_raw, (taken_at - previous[0]["taken_at"]).total_seconds(), stale)
            traffic.annotate(snapshot, found)
            if getattr(store, "engine", None) is not None:
                traffic.save(store.engine, found, taken_at)
        if previous:
            for text in alerts(previous[0]["snapshot"].get("health"), snapshot["health"]):
                _send(settings, text, send, store)
            before = set(previous[0]["snapshot"].get("loops") or [])
            for pair in sorted(set(snapshot["loops"]) - before):
                _send(settings, Text(f"**🔁 Possible network loop: {pair}**\n• more than one cable between them "
                                     "carries traffic\n\nSee Lanxang → Network → Cabling.", f"wiring:loop:{pair}"), send, store)
            for pair in sorted(before - set(snapshot["loops"])):
                _send(settings, Text(f"**✅ Resolved: loop between {pair}**\n• only one cable carries traffic now",
                                     f"wiring:loop:{pair}"), send, store)
        from lanxang.alerts import issue, report
        found = [issue(f"cable:{i['kind']}", f"{i['device']}:{i['port']}", f"{i['reason']}: {where(i)}",
                       i["detail"], "problem" if i["level"] == "bad" else "watch", "/cabling")
                 for i in snapshot["health"]]
        found += [issue("loop", pair, f"Possible network loop: {pair}",
                        "more than one cable between them carries traffic", href="/cabling")
                  for pair in snapshot["loops"]]
        found += [issue("source", name, f"Can't read {name}", source["error"], "watch", "/cabling")
                  for name, source in sources.items() if not source["ok"]]
        report("wiring", found, taken_at, store)
        store.save(snapshot, raw, sources, taken_at, keep=config.keep_snapshots)

        return {"taken_at": taken_at, "snapshot": snapshot, "sources": sources}

    finally:
        _LOCK.release()
