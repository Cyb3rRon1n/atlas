"""
Daily internet speed test (internet.speed_test, off by default): download, upload and ping against Cloudflare's
public speed test (speed.cloudflare.com), the first `lanxang internet speed` run after 04:00 local (notify.timezone),
so it doesn't land on someone's evening film. Four parallel streams, about 200 MB down and 60 MB up - one TCP
stream alone can't fill a multi-gigabit line. The result is posture status 'speedtest' with the last 30 days; there
is no alert, since a single slow result is usually the line being busy, not a fault. Nothing about you is sent.
"""

import http.client
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

BASE = "https://speed.cloudflare.com"
STREAMS, DOWN_BYTES, UP_BYTES = 4, 50_000_000, 15_000_000      # per stream
RUN_AT_HOUR = 4
KEEP = 30


def _request(url, data=None, timeout=60):

    request = urllib.request.Request(url, data=data, headers={"User-Agent": "lanxang-speedtest"})
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        while reply.read(1 << 20):
            pass


def _ping(samples=5):
    """Fastest round trip in ms over one open connection, so the TLS handshake isn't counted."""

    connection = http.client.HTTPSConnection("speed.cloudflare.com", timeout=10)
    try:
        connection.connect()
        best = None
        for _ in range(samples):
            start = time.monotonic()
            connection.request("GET", "/__down?bytes=0", headers={"User-Agent": "lanxang-speedtest"})
            connection.getresponse().read()
            took = (time.monotonic() - start) * 1000
            best = took if best is None else min(best, took)
        return round(best)
    finally:
        connection.close()


def _mbps(job, size):

    start = time.monotonic()
    with ThreadPoolExecutor(STREAMS) as pool:
        list(pool.map(lambda _: job(), range(STREAMS)))
    return round(STREAMS * size * 8 / (time.monotonic() - start) / 1e6, 1)


def measure(request=_request, ping=_ping):
    """{"down": Mb/s, "up": Mb/s, "ping": ms}; raises OSError when Cloudflare can't be reached."""

    latency = ping()
    down = _mbps(lambda: request(f"{BASE}/__down?bytes={DOWN_BYTES}"), DOWN_BYTES)
    up = _mbps(lambda: request(f"{BASE}/__up", data=b"0" * UP_BYTES), UP_BYTES)

    return {"down": down, "up": up, "ping": latency}


def due(previous, now, tz):
    """True from 04:00 local until today's test has run."""

    from datetime import datetime

    from lanxang.alerts.quiet import local

    here = local(now, tz)
    if here.hour < RUN_AT_HOUR:
        return False
    last = (previous or {}).get("at")
    return not last or local(datetime.fromisoformat(last), tz).date() != here.date()


def run(settings, store, now, *, test=measure, force=False):
    """One daily test. Returns the saved detail ({"at", "down", "up", "ping", "error", "history"}), or the previous one
    when it isn't due."""

    previous = (store.statuses().get("speedtest") or {}).get("detail") or {}
    if not force and not due(previous, now, settings.notify.timezone):
        return previous
    try:
        result, error = test(), None
    except (OSError, ValueError) as failure:
        result, error = {}, str(getattr(failure, "reason", None) or failure)[:200]
    history = [h for h in previous.get("history") or [] if h["at"] >= (now - timedelta(days=KEEP)).isoformat()]
    if result:
        history.append({"at": now.isoformat(), **result})
    detail = {"at": now.isoformat(), "down": result.get("down"), "up": result.get("up"), "ping": result.get("ping"),
              "error": error, "history": history}
    store.set_status("speedtest", error is None, detail, now)

    return detail

