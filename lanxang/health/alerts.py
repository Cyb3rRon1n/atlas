"""
Host health alerts: one pure assess() over what `lanxang sample` already reads
(temperatures with each sensor's own limit, memory, disks, containers, JSON
status feeds) and alerts() that fire once per new problem and once on recovery.

Containers that stopped cleanly (exit code 0, e.g. a game room an idle timer
put to sleep) or carry the label lanxang.on-demand=true (or the older atlas.on-demand) are "asleep", not a
problem: only crashes, restart loops and failing health checks count.
"""

TEMP_RUNS = 2         # scans in a row near the limit before it alerts (one busy minute is not a problem)

REASONS = {
    "temperature": "Running hot",
    "memory": "Memory almost full",
    "disk": "Disk almost full",
    "container": "Container down",
    "feed": "Status feed reports a problem",
}


def container_state(container):
    """'ok', 'asleep' or 'problem' for one container dict (status, health, exit_code, on_demand)."""

    status = container.get("status")
    if container.get("health") == "unhealthy" or status in ("restarting", "dead"):
        return "problem"
    if status == "running":
        return "ok"
    if status in ("created", "paused") or container.get("exit_code") == 0 or container.get("on_demand"):
        return "asleep"

    return "problem"


def container_problem(container):
    """Short text for a container that needs attention, else None."""

    if container_state(container) != "problem":
        return None
    if container.get("health") == "unhealthy":
        return f"{container['name']} unhealthy"
    if container.get("status") == "restarting":
        return f"{container['name']} keeps restarting"
    code = container.get("exit_code")

    return f"{container['name']} stopped" + (f" (exit code {code})" if code not in (None, 0) else "")


def assess(health, containers, config, state):
    """
    Issues for one sample plus the state to keep. health: get_host_health();
    containers: [{name, status, health, exit_code, on_demand}]; config: HealthConfig;
    state: {"hot": {sensor: runs}}. Returns (issues, state).
    """

    issues, hot = [], {}

    def add(kind, subject, detail):
        issues.append({"kind": kind, "level": "bad", "subject": subject, "reason": REASONS[kind], "detail": detail})

    limits = health.get("temperature_high_c_by_sensor") or {}
    for sensor, current in sorted((health.get("max_temperature_c_by_sensor") or {}).items()):
        high = limits.get(sensor)
        if high and current >= high - config.temp_margin_c:
            hot[sensor] = (state.get("hot") or {}).get(sensor, 0) + 1
            if hot[sensor] >= TEMP_RUNS:
                add("temperature", sensor, f"{sensor} at {current:.0f}°C, its limit is {high:.0f}°C - "
                                           "check fans and airflow, or what is keeping it busy")

    if (health.get("memory_percent") or 0) >= config.memory_percent:
        add("memory", "memory", f"{health['memory_percent']:.0f}% of memory in use")

    for label, percent in sorted((health.get("disks") or {}).items()):
        if percent >= config.disk_percent:
            add("disk", label, f"{label} is {percent:.0f}% full")

    for container in containers:
        problem = container_problem(container)
        if problem:
            add("container", container["name"], problem)

    for name, feed in sorted((health.get("status_feeds") or {}).items()):
        if "error" in feed:
            continue                          # unreachable feed: shown on the home page, not worth a page
        if str(feed.get("state", "ok")).lower() not in ("ok", "normal", "healthy"):
            temp = f", {feed['temp']}°C" if "temp" in feed else ""
            add("feed", name, f"{name} says {feed['state']}{temp}")

    return issues, {"hot": hot}


def alerts(previous_issues, issues):
    """Alert texts for problems new since the last sample, and for ones that cleared."""

    key = lambda i: (i["kind"], i["subject"])
    old = {key(i): i for i in previous_issues or []}
    new = {key(i): i for i in issues}
    from lanxang.alerts import Text
    tag = lambda k: f"host:{k[0]}:{k[1]}"
    texts = [Text(f"**🖥️ {i['reason']}**\n• {i['detail']}\n\nSee Lanxang → Home.", tag(k))
             for k, i in new.items() if k not in old]
    texts += [Text(f"**✅ Resolved: {i['reason'].lower()}**\n• {i['subject']}", tag(k)) for k, i in old.items() if k not in new]

    return texts


def run(settings, store, health, containers, now, send=None):
    """Assess one sample, alert on changes, keep the result (posture status table, source 'host')."""

    from lanxang import notify

    previous = ((store.statuses().get("host") or {}).get("detail")) or {}
    issues, state = assess(health, containers, settings.health, previous)
    from lanxang.alerts import issue, report
    report("host", [issue(i["kind"], i["subject"], i["reason"], i["detail"], href="/")
                    for i in issues] if settings.health.alerts else [], now, store)
    if settings.health.alerts:
        from lanxang.alerts import allowed
        for text in alerts(previous.get("issues"), issues):
            if not allowed(store, text, now):
                continue
            if send:
                send(text)
            elif notify.configured(settings.notify):
                notify.send(settings.notify, text)
    store.set_status("host", not issues, {**state, "issues": issues}, now)

    return issues
