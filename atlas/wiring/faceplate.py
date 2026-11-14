"""
Physical port layout, so the screen matches the box in the rack: small devices
(gateways, APs, desktop switches - up to 8 ports) are one row in device order;
rack switches are two rows, odd numbers on top and even below, in blocks of 6
columns, with the extra uplink/SFP ports past 24 (or 48) as their own group on
the right - the front-panel convention almost every managed switch follows.
Logical ports (port-channels, VLAN interfaces) have no socket and are listed
apart. Pure; shared by the faceplate grid and the diagram boxes.

ponytail: a convention, not per-model data - a switch with an unusual panel
(ports numbered top row first, SFP cages left) needs a per-model override.
"""

import re


LOGICAL = re.compile(r"^(po|port-channel|ch|lag|bond|vlan|tunnel|loopback|lo|br)[\s\d/]*$", re.IGNORECASE)

NUMBER = re.compile(r"(\d+)$")

SINGLE_ROW_MAX = 8

BLOCK = 6        # columns per block before a gap

GAP = 0.5        # gap width, in port columns


def _label(name, rank):

    number = NUMBER.search(name)
    digits = number.group(1) if number else str(rank)

    return f"S{digits}" if name.upper().startswith("SFP") else digits


def physical_layout(ports):
    """{port: {"index", "up", "speed"}} -> {"rows", "width", "ports": [{name, label, row, x, up, speed}], "logical": [names]}"""

    physical, logical = [], []

    for name, info in ports.items():
        (logical if LOGICAL.match(name) else physical).append((name, info))

    def order(item):
        name, info = item
        number = NUMBER.search(name)
        return (info.get("index") or 0, int(number.group(1)) if number else 0, name)

    physical.sort(key=order)
    count = len(physical)
    placed = []

    if count <= SINGLE_ROW_MAX:
        for rank, (name, info) in enumerate(physical, 1):
            placed.append((name, info, rank, 0, float(rank - 1)))
        rows = 1
    else:
        main = 24 if 24 < count <= 28 else 48 if 48 < count <= 52 else count
        for rank, (name, info) in enumerate(physical, 1):
            in_main = rank <= main
            position = rank if in_main else rank - main
            column = (position - 1) // 2
            x = column + (column // BLOCK) * GAP
            if not in_main:
                last_main = (main - 1) // 2
                x += last_main + 1 + (last_main // BLOCK) * GAP + 2 * GAP
            placed.append((name, info, rank, 0 if position % 2 else 1, x))
        rows = 2

    return {
        "rows": rows,
        "width": (max(x for *_, x in placed) + 1) if placed else 0,
        "ports": [{"name": name, "label": _label(name, rank), "row": row, "x": x,
                   "up": bool(info.get("up")), "speed": int(info.get("speed") or 0)}
                  for name, info, rank, row, x in placed],
        "logical": sorted(name for name, _ in logical),
    }
