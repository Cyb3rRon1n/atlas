"""
/uptime (Servers > Uptime): one row per uptime check - up/down, response time, uptime over 24 h / 7 days /
30 days, a 24 h graph - plus a form to add a check and one-click suggestions from the public hostnames atlas
already knows. Checks added here are saved to the web settings; a list in the config file wins and locks the form.
"""

import re
from datetime import timedelta

from lanxang.config.local import config_name
from lanxang.config import local
from lanxang.web.blocks import status_hero
from lanxang.web.render import _esc, plural, render_page, when

STYLE = """<style>
.up-intro { color:var(--muted); max-width:70ch; }
.up-how > summary { cursor:pointer; color:var(--muted); margin:8px 0 12px; }
.uptime { width:100%; border-collapse:collapse; font-size:.875rem; margin:12px 0 24px; }
.uptime th, .uptime td { text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:middle; }
.uptime th { color:var(--muted); font-weight:600; font-size:.8125rem; }
.uptime td.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
.uptime .target { display:block; color:var(--muted); font-size:.75rem; overflow-wrap:anywhere; }
@media (max-width: 600px) { .uptime .target { white-space:nowrap; } }   /* the table scrolls sideways instead */
.state { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:600; }
.state.up { background:color-mix(in srgb, var(--green) 20%, transparent); color:var(--green); }
.state.down { background:color-mix(in srgb, var(--red) 22%, transparent); color:var(--red); }
.state.failing { background:color-mix(in srgb, var(--orange) 22%, transparent); color:var(--orange); }
.state.waiting { background:var(--line); color:var(--muted); }
.ms polyline { fill:none; stroke:var(--blue); stroke-width:1.5; } .ms rect { fill:var(--red); }
.up-add { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; max-width:760px; }
.up-add form, form.up-add { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.up-add input[name=name] { width:230px; max-width:100%; box-sizing:border-box; } .up-add input[name=target] { flex:1; min-width:min(240px, 100%); box-sizing:border-box; }
.up-sugg { margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; color:var(--muted); font-size:.8125rem; }
.up-sugg button { border-radius:999px; }   /* suggestion chips stay pills */
.up-power { margin:.4rem 0; } .up-power .state { margin-right:.4rem; }
#up-msg { color:var(--red); min-height:1.2em; }
.outages { margin:4px 0 24px; padding-left:18px; font-size:.875rem; } .outages li { padding:2px 0; }
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
document.querySelectorAll("code.ping").forEach((el) => {
  el.textContent = "curl -fsS -m 10 " + location.origin + el.dataset.ping;
});
document.getElementById("beat-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  upPost("/api/uptime/heartbeat/add", {name: form.name.value, every: Number(form.every.value)});
});
document.addEventListener("click", (event) => {
  const beat = event.target.closest("[data-beat-remove]");
  if (beat) { beat.disabled = true; upPost("/api/uptime/heartbeat/remove", {name: beat.dataset.beatRemove}); return; }
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


def _hero(checks, summary, now, fail_after, internet=None):
    """The top line over the Services table, counting the built-in Internet check when it is on. A check with no
    result in the last few minutes (or never) is unknown: the hero only says "up" when every check answered recently
    and none failed."""

    entries = [(check.name, summary.get(check.name)) for check in checks]
    if internet:
        entries.append(("Internet", internet["summary"].get("Internet")))
    if not entries:
        return ""
    fresh = timedelta(minutes=fail_after + 3)               # checks run once a minute
    down, failing, unknown = [], [], []
    for name, info in entries:
        info = info or {"points": [], "last": None}
        last = info["last"]
        if not last or now - last[0] > fresh:
            unknown.append(name)
            continue
        state = _state(info, fail_after)[0]
        if state == "down":
            down.append(name)
        elif state == "failing":
            failing.append(name)
    total = len(entries)
    gaps = f"{plural(len(unknown), 'check')} with no recent result" if unknown else ""

    def named(names, verb):                                 # the Internet by name: it isn't in the table below
        rest = len(names) - ("Internet" in names)
        if "Internet" not in names:
            return f"{plural(rest, 'check')} {verb}"
        return f"Internet and {plural(rest, 'check')} {verb}" if rest else f"Internet {verb}"

    if down or failing:
        bad = down or failing
        return status_hero(len(bad), named(bad, "down" if down else "failing"), gaps, "attention")
    if unknown:
        title = ("The Internet check has no recent result" if unknown == ["Internet"]
                 else f"{len(unknown)} of {total} checks have no recent result")
        return status_hero("?", title, "Lanxang may not be running the checks right now.", "unknown")

    rest = total - bool(internet)
    if internet:
        return status_hero("", f"Internet and {'all ' if rest > 1 else ''}{plural(rest, 'check')} up" if rest
                           else "Internet up", "", "ok")
    return status_hero("", f"All {total} checks up" if total > 1 else "1 check up", "", "ok")


def _pct(value):

    return "–" if value is None else f"{value:g}%"


def _power(power):
    """The UPS line(s) when the UPS watch is on: state, charge, time left, load."""

    if not power:
        return ""
    if power.get("error") and not power.get("upses"):
        return (f'<p class="up-power"><span class="state failing">UPS</span> Can\'t read the UPS server: '
                f'{_esc(power["error"])} — <a href="/settings#ups">check Setup</a></p>')
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


def internet_data(store, now, fail_after=2, config=None):
    """{"summary": UptimeStore.summary() for Internet and Router, "outages": [(start, end, router_ok)] 30 days}."""

    from datetime import timedelta

    from lanxang.monitoring import internet

    since = now - timedelta(days=30)
    router = dict(store.history(internet.ROUTER, since))
    rows = [(at, ok, router.get(at)) for at, ok in store.history(internet.INTERNET, since)]
    return {"summary": store.summary(internet.all_names(config) if config else internet.NAMES, now),
            "outages": list(reversed(internet.outages(rows, fail_after)))}


def _what(name):
    if name == "Internet":
        return "public DNS servers"
    if name == "Router":
        return "your router"
    return "this machine's name lookups" if name == "DNS" else "name lookups at " + name[4:]


def _internet(data, now, fail_after):
    """The Internet section: the two built-in checks as rows, then the outage list."""

    if not data or not any(info["points"] for info in data["summary"].values()):
        return ""
    rows = []
    for name, info in data["summary"].items():
        if not info["points"]:
            continue
        state, label = _state(info, fail_after)
        last = info["last"]
        rows.append(f'<tr><td><span class="state {state}">{label}</span></td><td><strong>{_esc(name)}</strong>'
                    f'<span class="target">{_what(name)}</span></td>'
                    f'<td class="num">{f"{last[2]:.0f} ms" if last and last[2] is not None else ""}</td>'
                    f'<td>{_graph(info["points"])}</td>'
                    + "".join(f'<td class="num">{_pct(info["uptime"].get(w))}</td>' for w in ("24 h", "7 days", "30 days"))
                    + "</tr>")
    outages = "".join(
        f'<li><b>{when(start)}</b> — '
        + (f'{_minutes(end - start)}' if end else "still down")
        + f' · {"internet provider (your router answered)" if router_ok else "router or local network"}</li>'
        for start, end, router_ok in data["outages"][:20])

    return ('<h2>Internet</h2><div class="table-wrap"><table class="uptime"><thead><tr><th>Status</th><th>Check</th><th>Response</th>'
            '<th>Last 24 h</th><th>24 h</th><th>7 days</th><th>30 days</th></tr></thead><tbody>' + "".join(rows)
            + '</tbody></table></div>' + (f'<h3>Outages, last 30 days</h3><ul class="outages">{outages}</ul>' if outages else
                                   '<p class="up-intro">No outages in the last 30 days.</p>'))


def _minutes(span):

    minutes = max(1, round(span.total_seconds() / 60))
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60} min"


EVERY = (("every hour", 60), ("every day", 1440), ("every week", 10080))
BEAT_LABELS = {"ok": ("up", "On time"), "late": ("down", "Late"), "failed": ("down", "Failed"),
               "waiting": ("waiting", "Waiting for first ping")}


def _every(minutes):
    return next((label for label, value in EVERY if value == minutes), f"every {minutes} min")


def _heartbeats(beats, now, locked):
    """beats: [(heartbeat, {"state", "at"}, token)]."""

    rows = "".join(
        f'<tr><td><span class="state {BEAT_LABELS[st["state"]][0]}">{BEAT_LABELS[st["state"]][1]}</span></td>'
        f'<td><strong>{_esc(hb.name)}</strong><span class="target">{_every(hb.every_minutes)}, '
        f'{hb.grace_minutes} min grace</span></td>'
        f'<td>{when(st.get("at"), now, never="never")}</td>'
        f'<td><code class="ping" data-ping="/ping/{_esc(token)}">curl -fsS -m 10 /ping/{_esc(token)}</code></td>'
        f'<td>{"" if locked else f"""<button class="danger sm" type="button" data-beat-remove="{_esc(hb.name)}">Remove</button>"""}</td></tr>'
        for hb, st, token in beats)
    table = ('<div class="table-wrap"><table class="uptime"><thead><tr><th>Status</th><th>Job</th><th>Last ping</th><th>Ping it with</th>'
             f'<th></th></tr></thead><tbody>{rows}</tbody></table></div>' if rows else "")
    options = "".join(f'<option value="{value}"{" selected" if value == 1440 else ""}>{label}</option>'
                      for label, value in EVERY)
    add = ("" if locked else
           '<form id="beat-form" class="up-add"><input name="name" placeholder="Name, e.g. Nightly backup" '
           f'aria-label="Name" required><select name="every" aria-label="How often">{options}</select>'
           '<button class="primary" type="submit">Add heartbeat</button></form>')
    return ('<h2>Heartbeats</h2><p class="up-intro">For jobs Lanxang can\'t check from outside — a nightly backup, a '
            'cron job. Add one, then have the job run the line shown when it finishes (add <code>/fail</code> to '
            'the address when it fails). If it doesn\'t check in on time you get one alert, and another when it '
            'does. If Lanxang sits behind a sign-in page, use its address on your network instead.</p>'
            + table + add)


def render_uptime_page(checks, summary, now, fail_after=2, suggestions=(), locked=False, power=None, internet=None,
                       beats=(), beats_locked=False):

    rows = []
    for check in checks:
        info = summary.get(check.name) or {"points": [], "uptime": {}, "last": None, "last_failure": None}
        state, label = _state(info, fail_after)
        last = info["last"]
        response = f"{last[2]:.0f} ms" if last and last[2] is not None else (last[3] if last else "")
        failure = info["last_failure"]
        problem = f"{when(failure[0], now)}: {_esc(failure[1])}" if failure else "none in 30 days"
        remove = ("" if locked else
                  f'<button class="danger sm" type="button" data-remove="{_esc(check.name)}">Remove</button>')
        rows.append(
            f'<tr><td><span class="state {state}">{label}</span></td>'
            f'<td><strong>{_esc(check.name)}</strong><span class="target">{_esc(check.target)}</span></td>'
            f'<td class="num">{_esc(response)}</td><td>{_graph(info["points"])}</td>'
            + "".join(f'<td class="num">{_pct(info["uptime"].get(w))}</td>' for w in ("24 h", "7 days", "30 days"))
            + f'<td>{problem}</td><td>{remove}</td></tr>')

    table = ('<div class="table-wrap"><table class="uptime"><thead><tr><th>Status</th><th>Check</th><th>Response</th><th>Last 24 h</th>'
             '<th>24 h</th><th>7 days</th><th>30 days</th><th>Last problem</th><th></th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>' if rows else
             '<p class="up-intro"><strong>No checks yet.</strong> Add the services you care about below — '
             'Lanxang tries each one every minute.</p>')

    if locked:
        add = (f'<section class="up-add"><p class="up-intro">These checks are set in {config_name()} '
               '(<code>uptime.checks</code>) — edit them there.</p></section>')
    else:
        chips = "".join(f'<button class="secondary sm" type="button" data-name="{_esc(name)}" data-fill="{_esc(target)}">'
                        f'{_esc(name)}</button>' for name, target in suggestions)
        add = ('<section class="up-add"><h2>Add a check</h2>'
               '<form id="up-form"><input name="name" placeholder="Name, e.g. Media server" aria-label="Name" required>'
               '<input name="target" placeholder="https://media.example.org or 192.0.2.10:22" aria-label="Address" required>'
               '<button class="primary" type="submit">Add</button></form>'
               + (f'<div class="up-sugg">Your public sites: {chips}</div>' if chips else "")
               + '<p id="up-msg"></p></section>')

    body = (STYLE + _hero(checks, summary, now, fail_after, internet)
            + '<details class="up-how"><summary>How checks work</summary>'
              '<p class="up-intro">Is each service answering? Lanxang tries every check once a minute. A web address '
              'is up when it answers at all (a login page counts); <code>host:port</code> is up when the port accepts '
              f'a connection. After {plural(fail_after, "failure")} in a row it is <strong>down</strong>: you get one alert, and '
              'another when it is back.</p></details>'
            + _internet(internet, now, fail_after) + _power(power)
            + ("<h2>Services</h2>" if power or internet else "") + table + add
            + _heartbeats(beats, now, beats_locked) + SCRIPT)

    return render_page("Uptime", body, active="uptime")


def suggestions(checks):
    """(name, https://host) for public hostnames atlas knows (Traefik routes, cert_hosts) not checked yet."""

    try:
        from lanxang.config.loader import load_config
        from lanxang.posture.certs import hosts
        from lanxang.posture.store import PostureStore
        known = hosts(PostureStore().latest_routes(), load_config().security.cert_hosts)
    except Exception:
        return []
    taken = " ".join(check.target for check in checks)

    return [(host.split(".")[0].capitalize(), f"https://{host}") for host in known if host not in taken][:10]


def handle_post(path, body):
    """(status, payload) for /api/uptime/add and /api/uptime/remove, or None when the path isn't ours."""

    from lanxang.monitoring.uptime import valid_target

    if path in ("/api/uptime/heartbeat/add", "/api/uptime/heartbeat/remove"):
        return _beat_post(path, body)
    if path not in ("/api/uptime/add", "/api/uptime/remove"):
        return None
    if local.locked(("uptime", "checks")):
        return 400, {"error": f"The checks are set in {config_name()} — edit them there."}
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
    if name.lower() in ("internet", "router", "dns") or name.lower().startswith("dns "):
        return 400, {"error": f"{name} is the built-in internet check — pick another name."}
    if len(others) != len(saved):
        return 400, {"error": f"There is already a check called {name}."}
    try:
        target = valid_target(str(body.get("target") or ""))
    except ValueError as error:
        return 400, {"error": str(error)}
    local.save_settings({"uptime": {"checks": others + [{"name": name, "target": target}]}})

    return 200, {"ok": True}


def _beat_post(path, body):

    if local.locked(("uptime", "heartbeats")):
        return 400, {"error": f"The heartbeats are set in {config_name()} — edit them there."}
    body = body if isinstance(body, dict) else {}
    name = re.sub(r"\s+", " ", str(body.get("name") or "")).strip()[:60]
    saved = ((local.read_settings().get("uptime") or {}).get("heartbeats")) or []
    others = [beat for beat in saved if beat.get("name") != name]
    if path.endswith("/remove"):
        if len(others) == len(saved):
            return 404, {"error": "No such heartbeat."}
        local.save_settings({"uptime": {"heartbeats": others or None}})
        return 200, {"ok": True}
    if not name or "/" in name:
        return 400, {"error": "Give the heartbeat a name (no slashes)."}
    if len(others) != len(saved):
        return 400, {"error": f"There is already a heartbeat called {name}."}
    every = body.get("every")
    if every not in [value for _, value in EVERY]:
        return 400, {"error": "Pick how often the job runs."}
    local.save_settings({"uptime": {"heartbeats": others + [
        {"name": name, "every_minutes": every, "grace_minutes": 15 if every <= 60 else 60}]}})
    return 200, {"ok": True}
