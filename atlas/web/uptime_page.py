"""
/uptime (Servers > Uptime): one row per uptime check - up/down, response time, uptime over 24 h / 7 days /
30 days, a 24 h graph - plus a form to add a check and one-click suggestions from the public hostnames atlas
already knows. Checks added here are saved to the web settings; a list in atlas.yaml wins and locks the form.
"""

import re

from atlas.config import local
from atlas.web.cabling_page import _ago
from atlas.web.render import _esc, render_page

STYLE = """<style>
.up-intro { color:var(--muted); max-width:70ch; }
.uptime { width:100%; border-collapse:collapse; font-size:14px; margin:12px 0 24px; }
.uptime th, .uptime td { text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:middle; }
.uptime th { color:var(--muted); font-weight:600; font-size:13px; }
.uptime td.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
.uptime .target { display:block; color:var(--muted); font-size:12px; word-break:break-all; }
.state { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }
.state.up { background:color-mix(in srgb, var(--green) 20%, transparent); color:var(--green); }
.state.down { background:color-mix(in srgb, var(--red) 22%, transparent); color:var(--red); }
.state.failing { background:color-mix(in srgb, var(--orange) 22%, transparent); color:var(--orange); }
.state.waiting { background:var(--line); color:var(--muted); }
.ms polyline { fill:none; stroke:var(--blue); stroke-width:1.5; } .ms rect { fill:var(--red); }
.up-add { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; max-width:760px; }
.up-add form { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.up-add input { background:var(--bg); color:inherit; border:1px solid var(--line); border-radius:6px; padding:7px 9px; font:inherit; }
.up-add input[name=name] { width:180px; } .up-add input[name=target] { flex:1; min-width:240px; }
.up-btn { background:var(--accent); color:#fff; border:0; border-radius:6px; padding:7px 14px; cursor:pointer; font:inherit; }
.up-btn.ghost { background:transparent; color:inherit; border:1px solid var(--line); padding:4px 10px; font-size:13px; }
.up-sugg { margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; color:var(--muted); font-size:13px; }
.up-power { margin:.4rem 0; } .up-power .state { margin-right:.4rem; }
#up-msg { color:var(--red); min-height:1.2em; }
</style>"""

SCRIPT = """<script>
const upMsg = document.getElementById("up-msg");
async function upPost(path, body) {
  const response = await fetch(path, {method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  if (response.ok) { location.reload(); return; }
  const data = await response.json().catch(() => ({}));
  upMsg.textContent = data.error || ("Failed: " + response.status);
}
document.getElementById("up-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  upPost("/api/uptime/add", {name: form.name.value, target: form.target.value});
});
document.addEventListener("click", (event) => {
  const remove = event.target.closest("[data-remove]");
  if (remove) { remove.disabled = true; upPost("/api/uptime/remove", {name: remove.dataset.remove}); return; }
  const fill = event.target.closest("[data-fill]");
  if (fill) { const form = document.getElementById("up-form");
              form.name.value = fill.dataset.name; form.target.value = fill.dataset.fill; form.target.focus(); }
});
</script>"""

BUCKETS = 96     # the 24 h graph: one point per 15 minutes


def _graph(points):
    """24 h of response times; a red mark under any 15 minutes that had a failure."""

    if len(points) < 2:
        return ""
    size = max(1, -(-len(points) // BUCKETS))
    buckets = [points[i:i + size] for i in range(0, len(points), size)]
    times = [[ms for ok, ms in bucket if ok and ms is not None] for bucket in buckets]
    top = max([max(t) for t in times if t] or [1.0])
    step = 160 / max(1, len(buckets) - 1)
    line = " ".join(f"{i * step:.1f},{22 - sum(t) / len(t) / top * 18:.1f}" for i, t in enumerate(times) if t)
    marks = "".join(f'<rect x="{max(0, i * step - 1.5):.1f}" y="24" width="3" height="4"/>'
                    for i, bucket in enumerate(buckets) if any(not ok for ok, _ in bucket))
    tip = f"slowest {top:.0f} ms in the last 24 h" + (" · red = failed checks" if marks else "")

    return (f'<svg class="ms" width="160" height="28" viewBox="0 0 160 28" role="img" aria-label="{_esc(tip)}">'
            f'<title>{_esc(tip)}</title><polyline points="{line}"/>{marks}</svg>')


def _state(info, fail_after):

    points = info["points"]
    if not points:
        return "waiting", "Waiting"
    recent = points[-fail_after:]
    if len(recent) == fail_after and not any(ok for ok, _ in recent):
        return "down", "Down"

    return ("up", "Up") if points[-1][0] else ("failing", "Failed once")


def _pct(value):

    return "–" if value is None else f"{value:g}%"


def _power(power):
    """The UPS line(s) when the UPS watch is on: state, charge, time left, load."""

    if not power:
        return ""
    if power.get("error") and not power.get("upses"):
        return (f'<p class="up-power"><span class="state failing">UPS</span> Can\'t read the UPS server: '
                f'{_esc(power["error"])} - <a href="/settings#ups">check Setup</a></p>')
    rows = []
    for name, info in (power.get("upses") or {}).items():
        state, label = {"online": ("up", "On mains"), "battery": ("down", "On battery"),
                        "low": ("down", "Battery low")}.get(info["state"], ("waiting", info["state"]))
        facts = [f"{info['charge']:.0f}% charged" if info.get("charge") is not None else "",
                 f"about {info['runtime_min']} min on battery" if info.get("runtime_min") is not None else "",
                 f"{info['load']:.0f}% load" if info.get("load") is not None else "",
                 "asks for a new battery" if info.get("replace") else ""]
        rows.append(f'<p class="up-power"><span class="state {state}">{label}</span> <b>{_esc(name)}</b>'
                    f'{" (" + _esc(info["model"]) + ")" if info.get("model") else ""} · '
                    f'{_esc(" · ".join(filter(None, facts)))}</p>')

    return "<h2>Power</h2>" + "".join(rows)


def render_uptime_page(checks, summary, now, fail_after=2, suggestions=(), locked=False, power=None):

    rows = []
    for check in checks:
        info = summary.get(check.name) or {"points": [], "uptime": {}, "last": None, "last_failure": None}
        state, label = _state(info, fail_after)
        last = info["last"]
        response = f"{last[2]:.0f} ms" if last and last[2] is not None else (last[3] if last else "")
        failure = info["last_failure"]
        problem = f"{_ago(failure[0], now)}: {failure[1]}" if failure else "none in 30 days"
        remove = ("" if locked else
                  f'<button class="up-btn ghost" type="button" data-remove="{_esc(check.name)}">Remove</button>')
        rows.append(
            f'<tr><td><span class="state {state}">{label}</span></td>'
            f'<td><strong>{_esc(check.name)}</strong><span class="target">{_esc(check.target)}</span></td>'
            f'<td class="num">{_esc(response)}</td><td>{_graph(info["points"])}</td>'
            + "".join(f'<td class="num">{_pct(info["uptime"].get(w))}</td>' for w in ("24 h", "7 days", "30 days"))
            + f'<td>{_esc(problem)}</td><td>{remove}</td></tr>')

    table = ('<table class="uptime"><thead><tr><th>Status</th><th>Check</th><th>Response</th><th>Last 24 h</th>'
             '<th>24 h</th><th>7 days</th><th>30 days</th><th>Last problem</th><th></th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table>' if rows else
             '<p class="up-intro"><strong>No checks yet.</strong> Add the services you care about below - '
             'atlas tries each one every minute.</p>')

    if locked:
        add = ('<section class="up-add"><p class="up-intro">These checks are set in atlas.yaml '
               '(<code>uptime.checks</code>) - edit them there.</p></section>')
    else:
        chips = "".join(f'<button class="up-btn ghost" type="button" data-name="{_esc(name)}" data-fill="{_esc(target)}">'
                        f'{_esc(name)}</button>' for name, target in suggestions)
        add = ('<section class="up-add"><h2>Add a check</h2>'
               '<form id="up-form"><input name="name" placeholder="Name, e.g. Media server" aria-label="Name" required>'
               '<input name="target" placeholder="https://media.example.org or 192.0.2.10:22" aria-label="Address" required>'
               '<button class="up-btn" type="submit">Add</button></form>'
               + (f'<div class="up-sugg">Your public sites: {chips}</div>' if chips else "")
               + '<p id="up-msg"></p></section>')

    body = (STYLE
            + '<p class="up-intro">Is each service answering? Atlas tries every check once a minute. A web address '
              'is up when it answers at all (a login page counts); <code>host:port</code> is up when the port accepts '
              f'a connection. After {fail_after} failures in a row it is <strong>down</strong>: you get one alert, and '
              'another when it is back.</p>'
            + _power(power) + ("<h2>Services</h2>" if power else "") + table + add + SCRIPT)

    return render_page("Uptime", body, active="uptime")


def suggestions(checks):
    """(name, https://host) for public hostnames atlas knows (Traefik routes, cert_hosts) not checked yet."""

    try:
        from atlas.config.loader import load_config
        from atlas.posture.certs import hosts
        from atlas.posture.store import PostureStore
        known = hosts(PostureStore().latest_routes(), load_config().security.cert_hosts)
    except Exception:
        return []
    taken = " ".join(check.target for check in checks)

    return [(host.split(".")[0].capitalize(), f"https://{host}") for host in known if host not in taken][:10]


def handle_post(path, body):
    """(status, payload) for /api/uptime/add and /api/uptime/remove, or None when the path isn't ours."""

    from atlas.monitoring.uptime import valid_target

    if path not in ("/api/uptime/add", "/api/uptime/remove"):
        return None
    if local.locked(("uptime", "checks")):
        return 400, {"error": "The checks are set in atlas.yaml - edit them there."}
    body = body if isinstance(body, dict) else {}
    name = re.sub(r"\s+", " ", str(body.get("name") or "")).strip()[:60]
    saved = ((local.read_settings().get("uptime") or {}).get("checks")) or []
    others = [check for check in saved if check.get("name") != name]

    if path.endswith("/remove"):
        if len(others) == len(saved):
            return 404, {"error": "No such check."}
        local.save_settings({"uptime": {"checks": others or None}})
        return 200, {"ok": True}

    if not name:
        return 400, {"error": "Give the check a name."}
    if len(others) != len(saved):
        return 400, {"error": f"There is already a check called {name}."}
    try:
        target = valid_target(str(body.get("target") or ""))
    except ValueError as error:
        return 400, {"error": str(error)}
    local.save_settings({"uptime": {"checks": others + [{"name": name, "target": target}]}})

    return 200, {"ok": True}
