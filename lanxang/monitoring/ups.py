"""
UPS watch (atlas ups check, once a minute in atlas-scan): reads a NUT server (Network UPS Tools, TCP 3493) - the
standard most UPSes are monitored through. A Linux box running nut-server, or a Synology / QNAP / Unraid / TrueNAS
with "network UPS server" switched on, all speak it. Only LIST and GET are sent: read-only, no login needed.

  power cut      ups.status has OB (on battery): one alert with charge and time left
  battery low    LB: one more alert - the UPS is about to run out
  back           OL again: "Power is back" with how long it lasted
  replace        RB: the UPS asks for a new battery (watch, page only)
"""

import socket
from datetime import datetime

from lanxang.alerts import Text

STATES = {"battery": "on battery", "low": "battery low", "online": "on mains power", "unreachable": "unreachable"}


def _lines(sock):

    buffer = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buffer += chunk
        if buffer.endswith(b"\n") and (b"END LIST" in buffer or buffer.startswith(b"ERR")):
            break

    return buffer.decode("utf-8", "replace").splitlines()


def _ask(sock, command):

    sock.sendall(command.encode() + b"\n")
    lines = _lines(sock)
    if lines and lines[0].startswith("ERR"):
        raise OSError(f"the UPS server said {lines[0][4:].strip() or 'no'}")

    return lines


def _quoted(line, skip):
    """'VAR ups battery.charge "87"' -> ("battery.charge", "87") with skip=2 words before the name."""

    words = line.split(" ", skip)
    name, _, value = words[-1].partition(" ")

    return name, value.strip().strip('"')


def fetch(host, port=3493, timeout=5.0, name=""):
    """{ups name: {variable: value}} for the named UPS, or every UPS the server has. Raises OSError."""

    with socket.create_connection((host, port), timeout=timeout) as sock:
        names = [name] if name else [_quoted(line, 1)[0] for line in _ask(sock, "LIST UPS") if line.startswith("UPS ")]
        if not names:
            raise OSError("the UPS server lists no UPS")
        found = {}
        for ups in names:
            found[ups] = dict(_quoted(line, 2) for line in _ask(sock, f"LIST VAR {ups}") if line.startswith("VAR "))
        sock.sendall(b"LOGOUT\n")

    return found


def _number(value):

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize(variables):
    """{"state", "charge", "runtime_min", "load", "model", "replace"} from one UPS's NUT variables."""

    flags = set((variables.get("ups.status") or "").split())
    runtime = _number(variables.get("battery.runtime"))

    return {"state": "low" if "LB" in flags else "battery" if "OB" in flags else "online",
            "charge": _number(variables.get("battery.charge")), "load": _number(variables.get("ups.load")),
            "runtime_min": round(runtime / 60) if runtime is not None else None, "replace": "RB" in flags,
            "model": " ".join(filter(None, (variables.get("device.mfr") or variables.get("ups.mfr"),
                                            variables.get("device.model") or variables.get("ups.model")))).strip()}


def _left(info):

    parts = [f"{info['charge']:.0f}% charged" if info["charge"] is not None else "",
             f"about {info['runtime_min']} min left" if info["runtime_min"] is not None else ""]

    return ", ".join(filter(None, parts))


def _minutes(since, now):

    minutes = max(1, round((now - since).total_seconds() / 60))
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60} min"


def run(settings, store, now, *, get=fetch, send=None):
    """One look at the UPS server. Status source 'ups' in the posture store. Returns the saved detail."""

    from lanxang import notify
    from lanxang.alerts import allowed, issue, report

    config = settings.ups
    previous = ((store.statuses().get("ups") or {}).get("detail")) or {}
    old = previous.get("upses") or {}
    try:
        upses = {name: summarize(variables) for name, variables in
                 get(config.host, config.port, config.timeout, config.name).items()}
        error = ""
    except OSError as failure:
        upses, error = {}, str(failure) or "no answer"

    texts, found = [], []
    for name, info in upses.items():
        before = (old.get(name) or {}).get("state", "online")
        outage = info["state"] in ("battery", "low")
        info["since"] = ((old.get(name) or {}).get("since") if outage and before in ("battery", "low") else
                         now.isoformat() if outage else None)        # when this power cut began
        label = f"UPS {name}" + (f" ({info['model']})" if info["model"] else "")
        if info["state"] in ("battery", "low"):
            title = "Power cut - running on battery" if info["state"] == "battery" else "UPS battery low"
            found.append(issue("power", name, f"{label}: {title.lower()}", _left(info), href="/uptime"))
        if info["replace"]:
            found.append(issue("battery", name, f"{label} asks for a new battery", "the UPS failed its battery test",
                               "watch", "/uptime"))
        if info["state"] == "battery" and before == "online":
            texts.append(Text(f"**⚡ Power cut: {label} is on battery**\n• {_left(info)}", f"ups:power:{name}"))
        elif info["state"] == "low" and before != "low":
            texts.append(Text(f"**🔋 {label}: battery low**\n• {_left(info)}\n• it will run out soon - save your work",
                              f"ups:power:{name}"))
        elif info["state"] == "online" and before != "online":
            since = (old.get(name) or {}).get("since")
            lasted = f"\n• the outage lasted about {_minutes(datetime.fromisoformat(since), now)}" if since else ""
            texts.append(Text(f"**✅ Power is back: {label}**{lasted}\n• battery {_left(info) or 'charging'}",
                              f"ups:power:{name}"))
    if error:
        found.append(issue("server", config.host, f"Can't read the UPS server at {config.host}", error, "watch",
                           "/settings#ups"))
        upses = old          # keep the last known state: a blip in reading it is not a power change

    report("ups", found, now, store)
    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                notify.send(settings.notify, text)

    detail = {"checked_at": now.isoformat(timespec="seconds"), "error": error, "upses": upses}
    store.set_status("ups", not found, detail, now)

    return detail
