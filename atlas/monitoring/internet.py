"""
Internet health (part of `atlas uptime check`, once a minute in atlas-scan): is the connection up, how fast does
it answer, and when it drops, is it the router or the internet provider?

  internet   a TCP connect to a few public DNS servers (Cloudflare, Google, Quad9 by default, port 443). Up when
             any answers; the time is the fastest answer. No ping, so no extra container privileges.
  router     the default gateway: a TCP connect to 53, 80 or 443. "Connection refused" also counts - only a
             router that's up can refuse.

Both are saved as uptime results ("Internet", "Router"), so they get the same graphs, uptime % and 30-day
keep as the checks you add. Down after uptime.fail_after failed minutes in a row: one alert then (it only
arrives if your alert service is reachable without the internet, like ntfy on your own network), and one when
it's back with how long it lasted.
"""

import errno
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from atlas.alerts import Text

INTERNET, ROUTER = "Internet", "Router"
NAMES = (INTERNET, ROUTER)


def _connect(host, port, timeout):
    """Milliseconds to connect, or None. A refused connection still proves the host is up: (ms, refused)."""

    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.monotonic() - start) * 1000, False
    except ConnectionRefusedError:
        return (time.monotonic() - start) * 1000, True
    except OSError as error:
        if error.errno == errno.ECONNREFUSED:
            return (time.monotonic() - start) * 1000, True
        return None, False


def check_internet(targets, timeout=3.0, connect=None):
    """(ok, fastest ms, detail) over targets like "1.1.1.1:443"."""

    def one(target):
        host, _, port = target.rpartition(":")
        return target, (connect or _connect)(host, int(port), timeout)

    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
        answers = list(pool.map(one, targets))
    times = [ms for _, (ms, refused) in answers if ms is not None and not refused]
    if times:
        return True, min(times), f"{len(times)} of {len(targets)} answered"
    return False, None, "no answer from " + ", ".join(target for target, _ in answers)


def check_router(gateway, timeout=2.0, connect=None):
    """(ok, ms, detail) for the default gateway: up when any of 53/80/443 answers or refuses."""

    if not gateway:
        return None
    for port in (53, 80, 443):
        ms, refused = (connect or _connect)(gateway, port, timeout)
        if ms is not None:
            return True, ms, f"{gateway} answered" + (" (port closed)" if refused else f" on {port}")
    return False, None, f"{gateway} did not answer"


def _gateway():

    from atlas.devices.lan import _read, default_gateway
    try:
        return default_gateway(_read("/proc/net/route"))
    except Exception:
        return None


def _minutes(span):

    minutes = max(1, round(span.total_seconds() / 60))
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60} min"


def outages(rows, fail_after=2):
    """[(start, end or None, router_ok)] from (checked_at, ok, router_ok) rows oldest first: runs of at least
    fail_after failures. router_ok: the router answered through the whole outage (so: the provider's side)."""

    found, run = [], []
    for at, ok, router_ok in list(rows) + [(None, True, True)]:
        if not ok and at is not None:
            run.append((at, router_ok))
            continue
        if len(run) >= fail_after:
            found.append((run[0][0], at, all(r is not False for _, r in run)))
        run = []
    return found


def run(settings, store, now, *, internet=None, router=None, gateway=None, send=None):
    """One check: saves "Internet" and "Router" results, alerts on a drop and on the way back."""

    from atlas import notify
    from atlas.alerts import allowed, issue, report

    config = settings.internet
    if not config.enabled:
        report("internet", [], now, store)
        return {}
    fail_after = max(1, settings.uptime.fail_after)
    was_down = _down(store, fail_after)

    results = {INTERNET: (internet or check_internet)(config.targets, config.timeout)}
    router_result = (router or check_router)((gateway or _gateway)())
    if router_result:
        results[ROUTER] = router_result
    store.save(results, now)

    down = _down(store, fail_after)
    found, texts = [], []
    router_ok = results.get(ROUTER, (None,))[0]
    side = ("your router answered, so it's the internet provider's side" if router_ok
            else "your router isn't answering either - check it and its power" if router_ok is False else "")
    if down:
        found.append(issue("down", INTERNET, "The internet connection is down", side or results[INTERNET][2],
                           href="/uptime"))
    if down and not was_down:
        texts.append(Text(f"**🌐 Internet is down**\n• {side or results[INTERNET][2]}\n• atlas keeps checking every"
                          " minute and tells you when it's back", "internet:down"))
    elif was_down and not down:
        since = store.outage_start(INTERNET, now)
        lasted = f"\n• it was down for about {_minutes(now - since)}" if since else ""
        texts.append(Text(f"**✅ Internet is back**{lasted}\n• see Atlas → Servers → Uptime for the outage list",
                          "internet:down"))
    report("internet", found, now, store)

    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                try:
                    notify.send(settings.notify, text)
                except Exception:
                    pass                       # no line, no message: the "back" one still goes out later

    return results


def _down(store, fail_after):

    rows = store.recent(INTERNET, fail_after)
    return len(rows) == fail_after and not any(ok for _, ok, _ in rows)
