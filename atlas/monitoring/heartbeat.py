"""
Heartbeats: for the jobs atlas can't check from outside - a nightly backup, a cron job, a script on another box.
The job calls its secret ping address when it finishes:

    curl -fsS -m 10 http://atlas.example:8420/ping/<token>          # it worked
    curl -fsS -m 10 http://atlas.example:8420/ping/<token>/fail     # it ran and failed

Checked once a minute with the uptime checks: a heartbeat that hasn't pinged within every_minutes + grace_minutes
is late - one alert then, one when it pings again. A /fail ping alerts right away. Nothing is said before the first
ping, so a new heartbeat doesn't alert while you're still wiring up the job.

The token is an HMAC of the heartbeat's name with a random key kept in inventory/ (so renaming a heartbeat changes
its address). The ping address needs no sign-in - the token is the password.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from atlas.alerts import Text

KEY_FILE = Path("inventory/heartbeat.key")


def _key():

    from atlas.config.local import _write

    try:
        return bytes.fromhex(KEY_FILE.read_text().strip())
    except (OSError, ValueError):
        key = secrets.token_bytes(32)
        _write(KEY_FILE, key.hex(), 0o600)
        return key


def token(name, key=None):
    return hmac.new(key or _key(), name.encode(), hashlib.sha256).hexdigest()[:32]


def find(supplied, heartbeats, key=None):
    """The heartbeat whose token this is, or None. Constant-time compares."""

    key = key or _key()
    return next((hb for hb in heartbeats if hmac.compare_digest(token(hb.name, key), supplied)), None)


def ping(store, name, now, failed=False):
    store.set_status(f"ping:{name}", not failed, {"at": now.isoformat(timespec="seconds"), "failed": failed}, now)


def state(heartbeat, last, now):
    """"waiting" (never pinged), "failed", "late" or "ok"."""

    if not last:
        return "waiting"
    if last.get("failed"):
        return "failed"
    due = timedelta(minutes=heartbeat.every_minutes + heartbeat.grace_minutes)
    return "late" if now - datetime.fromisoformat(last["at"]) > due else "ok"


def _ago(at, now):

    minutes = int((now - datetime.fromisoformat(at)).total_seconds() // 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h" if minutes < 2880 else f"{minutes // 1440} days"


def run(settings, store, now, send=None):
    """One look at every heartbeat: status "heartbeats" on the posture store, alerts on late, failed and back."""

    from atlas import notify
    from atlas.alerts import allowed, issue, report

    statuses = store.statuses()
    before = ((statuses.get("heartbeats") or {}).get("detail")) or {}
    found, texts, now_states = [], [], {}
    for hb in settings.uptime.heartbeats:
        last = (statuses.get(f"ping:{hb.name}") or {}).get("detail")
        current = state(hb, last, now)
        was = (before.get(hb.name) or {}).get("state", "waiting")
        now_states[hb.name] = {"state": current, "at": (last or {}).get("at")}
        if current == "late":
            detail = f"last ping {_ago(last['at'], now)} ago; expected every {hb.every_minutes} min"
            found.append(issue("late", hb.name, f"{hb.name} hasn't checked in", detail, href="/uptime"))
            if was != "late":
                texts.append(Text(f"**⏰ {hb.name} hasn't checked in**\n• {detail}\n• the job may not have run, "
                                  "or failed before it could ping", f"heartbeat:{hb.name}"))
        elif current == "failed":
            found.append(issue("failed", hb.name, f"{hb.name} reported a failure", f"at {last['at'][11:16]} UTC",
                               href="/uptime"))
            if was != "failed":
                texts.append(Text(f"**❌ {hb.name} reported a failure**\n• at {last['at'][11:16]} UTC - check its "
                                  "log", f"heartbeat:{hb.name}"))
        elif current == "ok" and was in ("late", "failed"):
            texts.append(Text(f"**✅ {hb.name} checked in again**", f"heartbeat:{hb.name}"))
    report("heartbeats", found, now, store)

    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                try:
                    notify.send(settings.notify, text)
                except Exception:
                    pass
    store.set_status("heartbeats", not found, now_states, now)
    return now_states
