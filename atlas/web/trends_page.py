"""
/trends (Hosts > Trends): line charts over 24h / 7d / 30d from Atlas's own
history - atlas.host.sample events (this host, every scan) and
atlas.proxmox.scan.completed events (the Proxmox node, its ZFS pools and
guests). Plain inline SVG, no dependencies. Pure renderer.
"""

from datetime import timedelta

from atlas.web.render import _esc, ask_chips, render_page

WINDOWS = {"24h": 1, "7d": 7, "30d": 30}
MAX_POINTS = 240

TRENDS_CHIPS = ("When was the server busiest this week?", "Will any disk or pool fill up soon?",
                "Did anything crash or go unhealthy recently?", "Which VM uses the most memory over time?")

TRENDS_STYLE = """
<style>
.windows { display:flex; gap:4px; margin:0 0 14px; } .windows a { padding:6px 12px; border-radius:8px; color:var(--muted); }
.windows a[aria-current="page"] { background:var(--surface2); color:var(--text); }
.tcard { background:#111821; border:1px solid #222c38; border-radius:14px; padding:14px 16px; margin-bottom:16px; }
.tcard > h2 { margin:0 0 10px; font-size:16px; border:0; padding:0; }
.tgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }
.tgrid.small { grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); }
.chart h3 { margin:0; font-size:13px; font-weight:600; display:flex; justify-content:space-between; gap:8px; }
.chart h3 .now { font-variant-numeric:tabular-nums; } .chart svg { width:100%; height:70px; display:block; margin:4px 0 2px; }
.chart .stats { font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums; }
.chart .grow { font-size:12px; margin-top:2px; } .chart .grow.soon { color:#ffb4a2; }
.chart .ln { fill:none; stroke-width:1.6; vector-effect:non-scaling-stroke; }
.chart .area { opacity:.12; } .chart .th { stroke-width:1; stroke-dasharray:3 3; vector-effect:non-scaling-stroke; }
.legend { font-size:12px; color:var(--muted); } .legend i { display:inline-block; width:10px; height:3px; margin:0 4px 2px 8px; }
</style>
"""

COLORS = ("#5aa7f0", "#43c08f", "#f0a23a", "#c58af9")


def _downsample(points):

    if len(points) <= MAX_POINTS:
        return points
    step = len(points) / MAX_POINTS
    return [points[int(i * step)] for i in range(MAX_POINTS)]


def _chart(title, series, since, now, unit="%", ymax=100.0, thresholds=(75, 90), growth=False):
    """series: [(label, [(time, value)])] - first series drives the numbers shown."""

    series = [(label, [(t, v) for t, v in pts if v is not None]) for label, pts in series]
    main = series[0][1] if series else []
    if not main:
        return f'<div class="chart"><h3>{_esc(title)}<span class="now muted">no data yet</span></h3></div>'

    top = max(ymax, max(v for _, pts in series for _, v in pts) * 1.1)
    span = max(1.0, (now - since).total_seconds())
    xy = lambda t, v: (round((t - since).total_seconds() / span * 300, 1), round(70 - v / top * 66, 1))
    lines = ""
    for i, (label, pts) in enumerate(series):
        coords = " ".join("%s,%s" % xy(t, v) for t, v in _downsample(pts))
        color = COLORS[i % len(COLORS)]
        if i == 0:
            first, last = xy(*pts[0]), xy(*pts[-1])
            lines += f'<polygon class="area" fill="{color}" points="{first[0]},70 {coords} {last[0]},70"/>'
        lines += f'<polyline class="ln" stroke="{color}" points="{coords}"><title>{_esc(label)}</title></polyline>'
        lx, ly = xy(*pts[-1])   # latest value always visible, even with a single sample
        lines += f'<ellipse cx="{lx}" cy="{ly}" rx="2.2" ry="3" fill="{color}"/>'
    guides = "".join(f'<line class="th" x1="0" x2="300" y1="{xy(now, th)[1]}" y2="{xy(now, th)[1]}" '
                     f'stroke="{"#f47a5c" if th >= 90 else "#f0a23a"}"/>' for th in thresholds if th < top)

    values = [v for _, v in main]
    fmt = (lambda v: f"{v:.0f}{unit}") if unit else (lambda v: f"{v:.0f}")
    legend = ("<div class=\"legend\">" + "".join(f'<i style="background:{COLORS[i % len(COLORS)]}"></i>{_esc(l)}'
                                                  for i, (l, _) in enumerate(series)) + "</div>") if len(series) > 1 else ""
    grow = _growth(main) if growth else ""

    return (f'<div class="chart"><h3>{_esc(title)}<span class="now">{fmt(values[-1])}</span></h3>'
            f'<svg viewBox="0 0 300 70" preserveAspectRatio="none" role="img" aria-label="{_esc(title)}">{guides}{lines}</svg>'
            f'<div class="stats">min {fmt(min(values))} · avg {fmt(sum(values) / len(values))} · max {fmt(max(values))}</div>'
            f"{grow}{legend}</div>")


def _growth(points):
    """Least-squares slope (%/day) -> 'full in ~N days' when there is enough history and it is rising."""

    if len(points) < 6 or (points[-1][0] - points[0][0]) < timedelta(hours=6):
        return '<div class="grow muted">growth: needs a few more hours of history</div>'
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in points]
    ys = [v for _, v in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0
    if slope <= 0.01:
        return '<div class="grow muted">not growing</div>'
    days = (100 - ys[-1]) / slope
    soon = days < 60
    when = f"~{days:.0f} days" if days < 365 else "over a year"
    return f'<div class="grow{" soon" if soon else ""}">+{slope:.2f}%/day → full in {when}</div>'


def _pct(used, total):

    return used / total * 100 if used is not None and total else None


def render_trends_page(samples, scans, window, now, host_name="this host", node_names=None):
    """
    samples: [(time, atlas.host.sample payload)]; scans: [(time, atlas.proxmox.scan.completed payload)],
    both oldest first and already limited to the window.
    """

    since = now - timedelta(days=WINDOWS[window])
    win = "".join(f'<a href="/trends?window={w}"{" aria-current=page" if w == window else ""}>{w}</a>' for w in WINDOWS)
    tabs = [("/overview", "Overview", False), ("/trends", "Trends", True)]
    s = lambda key: [(t, p.get(key)) for t, p in samples]

    host = (f'<section class="tcard"><h2>{_esc(host_name)}</h2><div class="tgrid">'
            + _chart("CPU", [("CPU", s("cpu"))], since, now) + _chart("RAM", [("RAM", s("mem"))], since, now)
            + _chart("System disk", [("disk", s("disk"))], since, now)
            + _chart("Hottest sensor", [("temp", s("temp"))], since, now, unit="°C", thresholds=(80, 90))
            + "</div></section>") if samples else ""

    node_points = {}
    pools, guests = {}, {}
    for t, p in scans:
        for n in p.get("nodes", []):
            if "maxmem" not in n:
                continue
            d = node_points.setdefault(n["name"], {"cpu": [], "mem": [], "disk": []})
            d["cpu"].append((t, (n.get("cpu") or 0) * 100))
            d["mem"].append((t, _pct(n.get("mem"), n.get("maxmem"))))
            d["disk"].append((t, _pct(n.get("disk"), n.get("maxdisk"))))
            for z in n.get("zfs", []):
                pools.setdefault(f"{(node_names or {}).get(n['name'], n['name'])} {z['name']}", []).append((t, _pct(z.get("alloc"), z.get("size"))))
        for g in p.get("guests", []):
            if g.get("template") or g.get("status") != "running":
                continue
            d = guests.setdefault(g["name"], {"cpu": [], "mem": []})
            d["cpu"].append((t, (g.get("cpu") or 0) * 100))
            d["mem"].append((t, _pct(g.get("mem"), g.get("maxmem"))))

    node_names = node_names or {}
    nodes = "".join(f'<section class="tcard"><h2>{_esc(node_names.get(name, name))} (Proxmox)</h2><div class="tgrid">'
                    + _chart("CPU", [("CPU", d["cpu"])], since, now) + _chart("RAM", [("RAM", d["mem"])], since, now)
                    + _chart("Root disk", [("disk", d["disk"])], since, now) + "</div></section>"
                    for name, d in node_points.items())

    storage_series = {label: [(t, p.get("storage", {}).get(label)) for t, p in samples]
                      for label in sorted({k for _, p in samples for k in p.get("storage", {})})}
    storage_series.update(pools)
    storage = ('<section class="tcard"><h2>Storage growth</h2><div class="tgrid">' + "".join(
        _chart(label, [(label, pts)], since, now, growth=True) for label, pts in storage_series.items())
        + "</div></section>") if storage_series else ""

    cont = [(t, p["containers"]) for t, p in samples if p.get("containers")]
    containers = ('<section class="tcard"><h2>Containers</h2><div class="tgrid">'
                  + _chart("Running", [("running", [(t, c["running"]) for t, c in cont]), ("total", [(t, c["total"]) for t, c in cont])],
                           since, now, unit="", ymax=max((c["total"] for _, c in cont), default=1), thresholds=())
                  + _chart("Unhealthy", [("unhealthy", [(t, c["unhealthy"]) for t, c in cont])], since, now, unit="",
                           ymax=3, thresholds=())
                  + "</div></section>") if cont else ""

    vms = ('<section class="tcard"><h2>VMs and containers on Proxmox</h2><div class="tgrid small">' + "".join(
        _chart(name, [("CPU", d["cpu"]), ("RAM", d["mem"])], since, now) for name, d in sorted(guests.items()))
        + "</div></section>") if guests else ""

    empty = ("" if samples or scans else
             '<p class="muted">No history yet - atlas-scan records a sample every 15 minutes; charts fill in as it runs.</p>')
    note = ('<p class="muted">Atlas keeps its own history (every 15 min). The 24h view fills after a day, 7d after a week.</p>')

    body = (TRENDS_STYLE + ask_chips(TRENDS_CHIPS) + f'<nav class="windows" aria-label="Time window">{win}</nav>'
            + note + empty + host + nodes + storage + containers + vms)

    return render_page("Trends", body, active="hosts", tabs=tabs)
