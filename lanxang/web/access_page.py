"""
/access - where the public services are reached from: a world map of visitor
locations, signed-in people (app sign-ins with user + IP) and anonymous visitors
grouped by place. Pure renderer over AccessStore.summary().
"""

import math

from lanxang.config.local import config_name
from lanxang.access.parse import is_private
from lanxang.web.icons import icon
from lanxang.web.render import _esc, ask_chips, empty_state, segmented, plural, render_page
from lanxang.web.world_land import LAND_PATH

WINDOWS = {"24h": 1, "7d": 7, "30d": 30}

ACCESS_CHIPS = ("Who signed in from somewhere unusual this week?", "Which anonymous visitors look like attackers or scanners?",
                "Were there failed sign-in attempts I should worry about?", "Which countries reach my services the most?")

ACCESS_STYLE = """
<style>
.windows { margin:0 0 14px; }
.astrip { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px; }
.astrip > div { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:10px 14px; }
.astrip .k { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
.astrip .v { font-size:20px; font-weight:600; } .astrip .warn .v { color:var(--bad-text); }
.mapbox { background:var(--deep); border:1px solid var(--line); border-radius:14px; padding:8px; margin-bottom:16px; }
.mapbox svg { width:100%; height:auto; display:block; }
.mapbox .land { fill:var(--surface2); stroke:var(--line2); stroke-width:.15; }
.mapbox .vis { fill:var(--blue); fill-opacity:.55; stroke:var(--blue); stroke-width:.2; }
.mapbox .vis.denied { fill:var(--red); stroke:var(--red); } .mapbox .user { fill:var(--green); fill-opacity:.8; stroke:var(--deep); stroke-width:.3; }
.legend { display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); padding:4px 6px 0; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:-1px; }
.acard { background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin-bottom:16px; }
.acard h2 { margin:0 0 4px; font-size:15px; border:0; padding:0; } .acard .why { margin:0 0 10px; font-size:13px; color:var(--muted); }
.acard table { margin:0; font-size:14px; } .acard td, .acard th { padding:6px 8px; }
.tag { font-size:11px; padding:1px 7px; border-radius:999px; border:1px solid var(--line); color:var(--muted); white-space:nowrap; }
.tag.new { color:var(--warn-text); border-color:var(--warn-line); } .tag.bad { color:var(--bad-text); border-color:var(--bad-line); } .tag.home { color:var(--ok-text); border-color:var(--ok-line); }
.credit { font-size:12px; color:var(--muted); }
.acard.attn { border-color:var(--orange); background:var(--warn-bg); }
.rv { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:8px 0; border-top:1px solid var(--warn-line); font-size:14px; }
.rv:first-of-type { border-top:0; } .rv > div { flex:1 1 320px; } .rv button { margin:0; }
details.acard > summary { cursor:pointer; font-weight:600; }
</style>
"""


def _place(v):

    if v.get("country") == "Home network":
        return "Home network"
    parts = [v.get("city"), v.get("region"), v.get("cc") or v.get("country")]
    return ", ".join(p for p in parts if p) or "Unknown"


def _xy(v):

    return (v["lon"] + 180, 90 - v["lat"]) if v.get("lat") is not None and v.get("lon") is not None else None


def render_access_page(summary, window, home_ips=(), enabled=True, user_places=()):

    if not enabled:
        how = (f'<details><summary>How to turn it on</summary><p class="muted">Set <code>access.enabled: true</code> '
               f'in {_esc(config_name())}. The scan service then reads the Traefik access log on every cycle.</p></details>')
        return render_page("Visitors", empty_state(
            "shield", "Visitor tracking is off", "When it is on, this page shows who reached your public services "
            "and from where: sign-ins, anonymous visitors and failed attempts on a world map.", extra=how),
            active="access")

    home = set(home_ips)
    is_home = lambda v: v["ip"] in home or is_private(v["ip"]) or v.get("country") == "Home network"
    logins = summary["logins"]
    login_ips = {l["ip"] for l in logins if l["ok"]}
    visitors = summary["visitors"]
    outside = [v for v in visitors if not is_home(v)]
    anonymous = [v for v in outside if v["ip"] not in login_ips]
    failed = [l for l in logins if not l["ok"]]

    # map: one dot per place (rounded lat/lon), area ~ requests; signed-in places on top in green
    places = {}
    for v in outside:
        xy = _xy(v)
        if not xy:
            continue
        p = places.setdefault((round(xy[0], 1), round(xy[1], 1)), {"requests": 0, "denied": 0, "label": _place(v), "user": False})
        p["requests"] += v["requests"]
        p["denied"] += v["denied"]
        p["user"] = p["user"] or v["ip"] in login_ips
    dots = "".join(
        f'<circle class="{"user" if p["user"] else "vis denied" if p["denied"] * 2 > p["requests"] else "vis"}" cx="{x}" cy="{y}" '
        f'r="{min(4.5, 0.6 + 0.5 * math.log10(1 + p["requests"])):.2f}"><title>{_esc(p["label"])}: {plural(p["requests"], "request")}'
        + (f', {p["denied"]} denied' if p["denied"] else "") + (", signed-in user" if p["user"] else "") + "</title></circle>"
        for (x, y), p in sorted(places.items(), key=lambda kv: kv[1]["user"]))

    win = segmented(WINDOWS, window, "/access?window={key}")
    countries = {v.get("cc") or v.get("country") for v in outside if v.get("cc") or v.get("country")}
    stats = (("Visitor IPs", len(outside), ""), ("Countries", len(countries), ""),
             ("Requests", sum(v["requests"] for v in outside), ""), ("Denied", sum(v["denied"] for v in outside), ""),
             ("Sign-ins", sum(l["ok"] for l in logins), ""), ("Failed sign-ins", len(failed), "warn" if failed else ""))

    people = {}
    for l in logins:
        key = (l["user"], l["app"], l["ip"])
        p = people.setdefault(key, {**l, "count": 0, "failed": 0})
        p["count" if l["ok"] else "failed"] += 1
    people_rows = "".join(
        f'<tr><td>{_esc(p["user"])}</td><td>{_esc(p["app"])}</td><td>{_esc(_place(p))}'
        + (' <span class="tag home">home</span>' if is_home(p) else "") + f'</td><td>{_esc(p.get("org") or "-")}</td>'
        f'<td>{p["count"]}' + (f' <span class="tag bad">{p["failed"]} failed</span>' if p["failed"] else "")
        + f'</td><td>{_esc(str(p["time"])[:16])}</td></tr>' for p in people.values())

    groups = {}
    for v in anonymous:
        g = groups.setdefault((_place(v), v.get("org") or "-"), {"ips": 0, "requests": 0, "denied": 0, "services": {}, "last": v["last"],
                                                                 "new": False})
        g["ips"] += 1
        g["requests"] += v["requests"]
        g["denied"] += v["denied"]
        g["last"] = max(g["last"], v["last"])
        for s, n in v["services"].items():
            g["services"][s] = g["services"].get(s, 0) + n
    anon_rows = "".join(
        f'<tr><td>{_esc(place)}</td><td>{_esc(org)}</td><td>{g["ips"]}</td><td>{g["requests"]}'
        + (f' <span class="tag bad">{g["denied"]} denied</span>' if g["denied"] else "") + "</td><td>"
        + _esc(", ".join(s for s, _ in sorted(g["services"].items(), key=lambda kv: -kv[1])[:3])) + "</td></tr>"
        for (place, org), g in sorted(groups.items(), key=lambda kv: -kv[1]["requests"])[:60])

    reviews = [p for p in user_places if p["status"] == "review"]
    review_rows = "".join(
        f'<div class="rv"><div><b>{_esc(p["user"])}</b> signed in to {_esc(p["app"])} from <b>{_esc(p["label"])}</b>'
        f'<div class="muted">first {_esc(str(p["first_seen"])[:16])} \u00b7 latest {_esc(str(p["last_seen"])[:16])} \u00b7 {_esc(p["ip"])}</div></div>'
        f'<button class="primary" data-confirm-user="{_esc(p["user"])}" data-confirm-key="{_esc(p["place_key"])}">That\'s them</button>'
        f'<button data-ask="Is this sign-in suspicious? {_esc(p["user"])} signed in to {_esc(p["app"])} from {_esc(p["label"])} '
        f'(IP {_esc(p["ip"])}) — a place and provider they have not used before. Their usual places: '
        + _esc("; ".join(q["label"] for q in user_places if q["user"] == p["user"] and q["status"] != "review") or "none yet")
        + '. Verdict: expected / ask them / lock the account, and why.">Investigate</button></div>' for p in reviews)
    review_card = (
        f'<section class="acard attn"><h2>{icon("globe")}New sign-in places ({len(reviews)})</h2><p class="why">Someone signed in '
        'from a country + provider not seen for them before (each person\'s first 14 days are learned automatically). '
        'Confirm it was them, or investigate.</p>' + review_rows + "</section>") if reviews else ""
    normal = [p for p in user_places if p["status"] != "review"]
    normal_card = (
        f'<details class="acard"><summary>Normal places ({len(normal)})</summary><table><thead><tr><th>User</th><th>Place'
        '</th><th>How</th><th>Last seen</th></tr></thead><tbody>' + "".join(
            f'<tr><td>{_esc(p["user"])}</td><td>{_esc(p["label"])}</td><td>{"you confirmed" if p["status"] == "confirmed" else "learned"}'
            f'</td><td>{_esc(str(p["last_seen"])[:16])}</td></tr>' for p in normal) + "</tbody></table></details>") if normal else ""
    confirm_js = ("<script>document.querySelectorAll('[data-confirm-user]').forEach((b) => b.addEventListener('click', async () => {"
                  " b.disabled = true; try { const r = await fetch('/api/access/known', {method: 'POST', credentials: 'same-origin',"
                  " headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user: b.dataset.confirmUser,"
                  " place_key: b.dataset.confirmKey})}); if (r.ok) { b.closest('.rv').remove(); return; }"
                  " b.textContent = 'Failed (' + r.status + ')'; } catch (e) { b.textContent = 'Network error'; } b.disabled = false; }));</script>")

    body = (
        ACCESS_STYLE + ask_chips(ACCESS_CHIPS) + review_card + f'<div class="windows">{win}</div>'
        + '<div class="astrip">' + "".join(f'<div class="{c}"><div class="k">{k}</div><div class="v">{v}</div></div>'
                                           for k, v, c in stats) + "</div>"
        + f'<div class="mapbox"><svg viewBox="0 0 360 180" role="img" aria-label="Where visitors came from">'
          f'<path class="land" d="{LAND_PATH}"/>{dots}</svg><div class="legend"><span><i style="background:var(--green)"></i>'
          'signed-in user</span><span><i style="background:var(--blue)"></i>anonymous visitor (dot size = requests)</span>'
          '<span><i style="background:var(--red)"></i>mostly denied (login wall, CrowdSec, rate limit)</span>'
          f'<span>{len(visitors) - len(outside)} home/LAN IPs not drawn</span></div></div>'
        + '<section class="acard"><h2>Signed-in people</h2><p class="why">Sign-ins and failed attempts from the apps\' own '
          'logs (Authelia, Jellyfin, Audiobookshelf, Kavita), with where they came from.</p>'
        + (f'<table><thead><tr><th>User</th><th>App</th><th>From</th><th>Provider</th><th>Sign-ins</th><th>Latest</th></tr>'
           f'</thead><tbody>{people_rows}</tbody></table>' if people_rows else '<p class="muted">No sign-ins in this window.</p>')
        + "</section>"
        + f'<section class="acard"><h2>Anonymous visitors ({plural(len(anonymous), "IP")})</h2><p class="why">Requests from IPs that '
          'never signed in — link previews, bots and scanners, or people who only reached a login page. Grouped by place '
          'and provider.</p>'
        + (f'<table><thead><tr><th>From</th><th>Provider</th><th>IPs</th><th>Requests</th><th>Services hit</th></tr></thead>'
           f'<tbody>{anon_rows}</tbody></table>' if anon_rows else '<p class="muted">No anonymous visitors in this window.</p>')
        + "</section>"
        + normal_card + confirm_js
        + '<p class="credit">IP geolocation by <a href="https://db-ip.com">DB-IP</a> (CC BY 4.0), looked up on this server. '
          'City-level, approximate.</p>'
    )

    return render_page("Visitors", body, active="access")
