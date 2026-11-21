"""
Per-port traffic: each wiring scan's byte counters against the scan before give an average in bits per second
over that gap (15 minutes by default). Switches report 64-bit counters over SNMP and UniFi reports them in its
port table, so nothing extra is polled. Rates are kept a week in their own table for the Port map's graphs, and
each cable on the map carries its current load.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from lanxang.database.models import PortTrafficRecord
from lanxang.wiring.build import INFRA
from lanxang.wiring.health import _delta, _ports
from lanxang.clock import utcnow

KEEP = timedelta(days=7)
BUSY, HOT = 0.5, 0.8        # share of link speed: drawn thicker / red on the map


def rates(raw, old_raw, seconds, stale=()):
    """{(device, port): (in_bps, out_bps)}; ports with a missing counter, a reset or a stale source left out."""

    if not seconds or seconds <= 0:
        return {}
    before = _ports(old_raw or {})
    found = {}
    for key, port in _ports(raw).items():
        if key[0] in stale or key not in before:
            continue
        now, then = port.get("counters"), before[key].get("counters")
        grew = _delta(now, then, "in_bytes"), _delta(now, then, "out_bytes")
        if None not in grew:
            found[key] = (grew[0] * 8 / seconds, grew[1] * 8 / seconds)

    return found


def annotate(snapshot, found):
    """Give every cable whose port has a rate "bps" (busier direction) and "load" (share of its speed)."""

    names = {node["id"]: node["name"] for node in snapshot.get("nodes", [])}
    for link in snapshot.get("links", []):
        rate = found.get((names.get(link["a"]), link["a_port"])) or found.get((names.get(link["b"]), link["b_port"]))
        if rate:
            link["bps"] = max(rate)
            link["load"] = round(max(rate) / (link["speed"] * 1e6), 4) if link.get("speed") else None


def save(engine, found, taken_at):

    with Session(engine) as session, session.begin():
        session.add_all(PortTrafficRecord(taken_at=taken_at, device=device, port=port, in_bps=a, out_bps=b)
                        for (device, port), (a, b) in found.items())
        session.execute(delete(PortTrafficRecord).where(PortTrafficRecord.taken_at < taken_at - KEEP))


def history(engine, since=None):
    """{(device, port): [(taken_at, in_bps, out_bps), ...]} oldest first (default: the last 24 h); {} when there's
    no table yet."""

    since = since or utcnow() - timedelta(hours=24)
    try:
        with Session(engine) as session:
            rows = session.scalars(select(PortTrafficRecord).where(PortTrafficRecord.taken_at >= since)
                                   .order_by(PortTrafficRecord.taken_at)).all()
    except Exception:
        return {}
    found = {}
    for row in rows:
        found.setdefault((row.device, row.port), []).append((row.taken_at, row.in_bps, row.out_bps))

    return found


def top_users(history, snapshot, n=5):
    """[(name, bytes)] for what is plugged into each port, summed over history(), busiest first. Switches, the gateway
    and access points are left out (their ports carry everyone's traffic); Wi-Fi clients sit behind their access point,
    so this is wired devices only."""

    nodes = {node["id"]: node for node in (snapshot or {}).get("nodes") or []}
    ids = {node.get("name") or node_id: node_id for node_id, node in nodes.items()}
    ends = {}
    for link in (snapshot or {}).get("links") or []:
        ends.setdefault((link.get("a"), link.get("a_port")), link.get("b"))
        ends.setdefault((link.get("b"), link.get("b_port")), link.get("a"))
    totals = {}
    for (device, port), points in history.items():
        node = nodes.get(ends.get((ids.get(device), port)))
        if not node or node.get("kind") in INFRA:
            continue
        # each rate is the average since the scan before, so it covers the gap back to the previous point (capped
        # at 2 h so a stretch with the scanner off isn't filled in with a guess)
        done = sum((a + b) / 8 * min((at - before[0]).total_seconds(), 7200)
                   for before, (at, a, b) in zip(points, points[1:]))
        name = node.get("name") or node["id"]
        totals[name] = totals.get(name, 0) + done

    return sorted(((name, done) for name, done in totals.items() if done > 0), key=lambda pair: -pair[1])[:n]


def text(bps):

    for unit, size in (("Gb/s", 1e9), ("Mb/s", 1e6), ("kb/s", 1e3)):
        if bps >= size:
            return f"{bps / size:.1f} {unit}".replace(".0 ", " ")

    return f"{bps:.0f} b/s"
