"""
One wired-map pass: collect every source on its own, fall back to a failed
source's last good raw input (marked stale), build, save. Shared by
`atlas wiring scan` and the web Refresh button; a module lock keeps two
clicks (or a click during a CLI run in the same process) from overlapping.
"""

import os
import threading
from datetime import datetime

from atlas.alerts import Text
from atlas.wiring import WiringError
from atlas.wiring.build import build_wiring
from atlas.wiring.cabling import load_cabling
from atlas.wiring.health import alerts, assess, poe_ports
from atlas.wiring.snmp import collect_switch
from atlas.wiring.unifi import fetch_unifi


_LOCK = threading.Lock()


class WiringBusy(Exception):
    """A scan is already running."""


def _send(settings, text, send, store=None):

    from atlas.alerts import allowed
    if not allowed(store, text):
        return

    from atlas import notify

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

        snapshot = build_wiring(list(raw["switches"].values()), raw["unifi"], devices,
                                load_cabling(config.cabling_file))

        # cable health: this scan's counters against the earlier scans (stale sources have nothing new)
        stale = {name for name, source in sources.items() if not source["ok"]}
        if "unifi" in stale:
            stale |= {d.get("name") for d in ((raw["unifi"] or {}).get("devices") or [])}
        snapshot["health"] = assess(raw, [h["raw"] for h in history], stale)
        snapshot["poe"] = poe_ports(raw)
        if previous:
            for text in alerts(previous[0]["snapshot"].get("health"), snapshot["health"]):
                _send(settings, text, send, store)
            before = set(previous[0]["snapshot"].get("loops") or [])
            for pair in sorted(set(snapshot["loops"]) - before):
                _send(settings, Text(f"**🔁 Possible network loop: {pair}**\n• more than one cable between them "
                                     "carries traffic\n\nSee Atlas → Cabling.", f"wiring:loop:{pair}"), send, store)
            for pair in sorted(before - set(snapshot["loops"])):
                _send(settings, Text(f"**✅ Resolved: loop between {pair}**\n• only one cable carries traffic now",
                                     f"wiring:loop:{pair}"), send, store)
        taken_at = now or datetime.utcnow()
        from atlas.alerts import issue, report
        found = [issue(f"cable:{i['kind']}", f"{i['device']}:{i['port']}", f"{i['reason']}: {i['device']} {i['port']}",
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
