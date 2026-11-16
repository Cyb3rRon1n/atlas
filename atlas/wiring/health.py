"""
Cable health: compares each wired-map scan's per-port counters with the scan
before it (counters only ever grow, so what matters is the change) plus the
port's own speed history. Pure functions over the raw switch / UniFi data the
wiring scan already saves.

  bad    CRC / alignment errors growing (a damaged cable, jack or patch lead),
         or a duplex mismatch (half duplex, late collisions). These alert.
  watch  link speed below what the port ran at before (often a damaged pair -
         or a desktop asleep), a link that went down and up, output errors.
         Shown on /cabling only: they have innocent causes too often to page anyone.
"""

from atlas.alerts import Text


CRC_MIN = 10            # errors per scan before a port is worth a look ...
RATE_WATCH = 1e-4       # ... and only above 0.01% of packets
RATE_BAD = 1e-3         # 0.1% of packets = a real problem
OUT_MIN = 10

REASONS = {
    "crc": "Likely bad cable or jack",
    "duplex": "Duplex mismatch",
    "speed": "Speed dropped",
    "flap": "Link went down and up",
    "out_errors": "Output errors",
    "poe_fault": "PoE fault",
    "poe_budget": "PoE budget nearly used",
}

POE_BUDGET_WATCH = 0.9


def _speed(mbit):

    return f"{mbit // 1000} Gbit/s" if mbit >= 1000 and mbit % 1000 == 0 else f"{mbit} Mbit/s"


def _devices(raw):
    """Every switch and UniFi device in one scan's raw data (name, ports, poe_budget_w, poe_used_w)."""

    return list((raw.get("switches") or {}).values()) + list((raw.get("unifi") or {}).get("devices") or [])


def poe_ports(raw):
    """[{device, port, delivering, watts}] for every PoE-capable port - saved on the snapshot for change detection."""

    return [{"device": device.get("name"), "port": name, "delivering": port["poe"]["delivering"],
             "watts": port["poe"].get("watts")}
            for device in _devices(raw) for name, port in sorted((device.get("ports") or {}).items()) if port.get("poe")]


def _ports(raw):
    """{(device, port): port dict} for every switch and UniFi device in one scan's raw data."""

    found = {}
    for switch in (raw.get("switches") or {}).values():
        for name, port in (switch.get("ports") or {}).items():
            found[(switch.get("name"), name)] = port
    for device in ((raw.get("unifi") or {}).get("devices") or []):
        for name, port in (device.get("ports") or {}).items():
            found[(device.get("name"), name)] = port

    return found


def _delta(now, before, key):
    """How much a counter grew; None when either side is missing or it went backwards (a reset)."""

    a, b = (now or {}).get(key), (before or {}).get(key)
    if a is None or b is None or a < b:
        return None

    return a - b


def _reset(now, before):

    return any((now or {}).get(k) is not None and (before or {}).get(k) is not None and now[k] < before[k]
               for k in ("in_errors", "out_errors", "fcs", "align", "packets"))


def assess(current, history, stale=()):
    """
    Issues for one scan. current: this scan's raw data; history: earlier raw
    data, newest first; stale: device names whose data was reused from an old
    scan (nothing new to judge). Returns [{device, port, kind, level, reason, detail}].
    """

    previous = _ports(history[0]) if history else {}
    best_speed = {}
    for raw in history:
        for key, port in _ports(raw).items():
            if port.get("up"):
                best_speed[key] = max(best_speed.get(key, 0), port.get("speed") or 0)

    issues = []

    def add(key, kind, level, detail):
        issues.append({"device": key[0], "port": key[1], "kind": kind, "level": level,
                       "reason": REASONS[kind], "detail": detail})

    for key, port in sorted(_ports(current).items()):
        if key[0] in stale or not port.get("up"):
            continue
        now, before = port.get("counters") or {}, (previous.get(key) or {}).get("counters")

        if now.get("duplex") == "half":
            add(key, "duplex", "bad", "running half duplex - usually one end is set to a fixed speed")

        speed, best = port.get("speed") or 0, best_speed.get(key, 0)
        if 0 < speed < best:
            add(key, "speed", "watch", f"links at {_speed(speed)}, ran at {_speed(best)} before - "
                                       "often a damaged wire pair or a bad jack (or a computer asleep)")

        if not before or _reset(now, before):
            continue

        late = _delta(now, before, "late")
        if late and now.get("duplex") != "half":          # half duplex is already reported above
            add(key, "duplex", "bad", f"{late} late collisions since the last scan - one end is half duplex")

        crc = (_delta(now, before, "fcs") or 0) + (_delta(now, before, "align") or 0)
        if now.get("fcs") is None and now.get("align") is None:
            crc = _delta(now, before, "in_errors") or 0         # no EtherLike-MIB: input errors stand in
        packets = _delta(now, before, "packets") or 0
        rate = crc / packets if packets else 1.0
        if crc >= CRC_MIN and rate >= RATE_WATCH:
            add(key, "crc", "bad" if rate >= RATE_BAD else "watch",
                f"{crc} CRC errors since the last scan ({rate:.2%} of packets)" if packets
                else f"{crc} CRC errors since the last scan")

        out = _delta(now, before, "out_errors")
        if out and out >= OUT_MIN:
            add(key, "out_errors", "watch", f"{out} output errors since the last scan")

        if now.get("last_change") is not None and before.get("last_change") is not None \
                and now["last_change"] != before["last_change"] and (previous.get(key) or {}).get("up"):
            add(key, "flap", "watch", "the link dropped and came back since the last scan")

    # PoE: a port that detected a device but can't power it, and devices close to their power budget.
    # Checked on down ports too - a powered device that never comes up is exactly what a fault looks like.
    for device in _devices(current):
        name = device.get("name")
        if name in stale:
            continue
        for port, info in sorted((device.get("ports") or {}).items()):
            if (info.get("poe") or {}).get("fault"):
                add((name, port), "poe_fault", "bad", "the switch detected a powered device but can't power it - "
                                                     "check the cable, or whether it needs more power than the port gives")
        budget, used = device.get("poe_budget_w"), device.get("poe_used_w")
        if budget and used is not None and used >= budget * POE_BUDGET_WATCH:
            add((name, ""), "poe_budget", "watch", f"using {used:g} W of {budget:g} W - another powered device may not start")

    return issues


def _key(issue):

    return (issue["device"], issue["port"], issue["kind"])


def alerts(previous_issues, issues):
    """Alert texts for bad issues that are new since the last scan, and for bad ones that cleared."""

    old = {_key(i): i for i in previous_issues or [] if i["level"] == "bad"}
    new = {_key(i): i for i in issues if i["level"] == "bad"}
    texts = []

    for key, issue in new.items():
        if key not in old:
            texts.append(Text(f"**🔌 {issue['reason']}: {issue['device']} {issue['port']}**\n"
                              f"• {issue['detail']}\n\nSee Atlas → Network → Cabling.",
                              f"wiring:cable:{issue['kind']}:{issue['device']}:{issue['port']}"))
    for key, issue in old.items():
        if key not in new:
            texts.append(Text(f"**✅ {issue['device']} {issue['port']} is healthy again**\n"
                              f"• no more {issue['reason'].lower()}",
                              f"wiring:cable:{issue['kind']}:{issue['device']}:{issue['port']}"))

    return texts
