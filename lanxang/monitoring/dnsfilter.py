"""
Pi-hole (v6) or AdGuard Home: is ad blocking on, how many DNS questions were asked and blocked, and which
devices ask the most. Read-only, checked with every `atlas scan` (and `atlas dns check`).

  Pi-hole v6   POST /api/auth with the password or an app password -> a session id, sent as X-FTL-SID;
               the session is ended (DELETE /api/auth) after each read, so atlas never uses up Pi-hole's
               16 session slots. No password set = no login.
  AdGuard Home basic auth on /control/status (protection on or off), /control/stats and
               /control/filtering/status (blocklist size).

Ad blocking off at two checks in a row (so not a 5-minute pause) is one alert, and one more when it's back on.
"""

import os

from lanxang.alerts import Text

PASSWORD_ENV = "ATLAS_DNS_PASSWORD"


class DnsFilterError(Exception):
    pass


def _json(response, what):

    if response.status_code in (401, 403):
        raise DnsFilterError(f"{what}: wrong password (HTTP {response.status_code})")
    if response.status_code >= 400:
        raise DnsFilterError(f"{what}: HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError:
        raise DnsFilterError(f"{what}: not a JSON answer - is this the right address?")


def _pihole(http, base, password, timeout, verify):

    headers, sid = {}, None
    try:
        if password:
            reply = _json(http.post(f"{base}/api/auth", json={"password": password}, timeout=timeout, verify=verify),
                          "Pi-hole sign-in")
            session = reply.get("session") or {}
            if not session.get("valid"):
                raise DnsFilterError("Pi-hole sign-in: password not accepted"
                                     + (" (two-factor is on - use an app password)" if session.get("totp") else ""))
            sid = session.get("sid")
            headers = {"X-FTL-SID": sid} if sid else {}
        get = lambda path, what: _json(http.get(f"{base}{path}", headers=headers, timeout=timeout, verify=verify), what)
        summary = get("/api/stats/summary", "Pi-hole stats")
        blocking = get("/api/dns/blocking", "Pi-hole blocking")
        top = get("/api/stats/top_clients?count=10", "Pi-hole clients")
    finally:
        if sid:
            try:
                http.delete(f"{base}/api/auth", headers={"X-FTL-SID": sid}, timeout=timeout, verify=verify)
            except Exception:
                pass                         # an expired session frees itself; never fail the read over it

    queries = summary.get("queries") or {}
    return {"kind": "Pi-hole", "blocking": blocking.get("blocking") == "enabled",
            "queries": queries.get("total"), "blocked": queries.get("blocked"),
            "percent": queries.get("percent_blocked"),
            "blocklist": (summary.get("gravity") or {}).get("domains_being_blocked"),
            "clients": [{"ip": c.get("ip"), "name": c.get("name") or "", "count": c.get("count")}
                        for c in top.get("clients") or []]}


def _adguard(http, base, user, password, timeout, verify):

    auth = (user, password) if user or password else None
    get = lambda path, what: _json(http.get(f"{base}{path}", auth=auth, timeout=timeout, verify=verify), what)
    status = get("/control/status", "AdGuard Home status")
    stats = get("/control/stats", "AdGuard Home stats")
    try:                                             # the blocklist size is extra: never fail the read over it
        lists = get("/control/filtering/status", "AdGuard Home lists").get("filters") or []
        blocklist = sum(f.get("rules_count") or 0 for f in lists if f.get("enabled")) or None
    except DnsFilterError:
        blocklist = None
    total, blocked = stats.get("num_dns_queries"), stats.get("num_blocked_filtering")
    clients = [{"ip": ip, "name": "", "count": count} for item in stats.get("top_clients") or []
               for ip, count in item.items()][:10]
    return {"kind": "AdGuard Home", "blocking": bool(status.get("protection_enabled")), "queries": total,
            "blocked": blocked, "percent": round(100 * blocked / total, 1) if total and blocked is not None else None,
            "blocklist": blocklist, "clients": clients}


def fetch(config, environ=None, http=None):
    """{"kind", "blocking", "queries", "blocked", "percent", "blocklist", "clients": [{ip, name, count}]}.
    Raises DnsFilterError in words a person can act on."""

    import requests

    http = http or requests
    environ = os.environ if environ is None else environ
    base = (config.url or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise DnsFilterError("Enter the web address, like http://192.168.1.53 or https://pi.hole")
    password = environ.get(PASSWORD_ENV, "")
    try:
        if config.kind == "adguard":
            return _adguard(http, base, config.user, password, config.timeout, config.verify_ssl)
        return _pihole(http, base, password, config.timeout, config.verify_ssl)
    except DnsFilterError:
        raise
    except Exception as error:                                   # connection refused, timeout, TLS...
        raise DnsFilterError(f"No answer from {base}: {type(error).__name__}") from error


def run(settings, store, now, *, get=fetch, send=None):
    """One read: status "dns" on the posture store, alerts when blocking stays off. Returns the saved detail."""

    from lanxang import notify
    from lanxang.alerts import allowed, issue, report

    config = settings.dns_filter
    if not config.enabled:
        report("dns", [], now, store)
        return None
    previous = ((store.statuses().get("dns") or {}).get("detail")) or {}
    try:
        info, error = get(config), ""
    except DnsFilterError as failure:
        info, error = dict(previous.get("info") or {}), str(failure)

    found, texts = [], []
    kind = info.get("kind") or ("AdGuard Home" if config.kind == "adguard" else "Pi-hole")
    if error:                                         # can't tell: keep what we knew, say nothing new
        off_since, alerted = previous.get("off_since"), previous.get("alerted", False)
        found.append(issue("read", kind, f"Can't read {kind}", error, "watch", "/settings#dnsfilter"))
    else:
        off = info.get("blocking") is False
        off_since = (previous.get("off_since") or now.isoformat(timespec="seconds")) if off else None
        alerted = off and previous.get("off_since") is not None          # off at two checks in a row
        if alerted:
            found.append(issue("blocking", kind, f"Ad blocking is off on {kind}", f"since {off_since[11:16]} UTC",
                               href="/settings#dnsfilter"))
        if alerted and not previous.get("alerted"):
            texts.append(Text(f"**🛑 Ad blocking is off on {kind}**\n• it has been off since {off_since[11:16]} UTC"
                              "\n• every device on your network is seeing ads and trackers again", "dns:blocking"))
        elif not off and previous.get("alerted"):
            texts.append(Text(f"**✅ Ad blocking is back on ({kind})**", "dns:blocking"))
    report("dns", found, now, store)

    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                notify.send(settings.notify, text)

    detail = {"checked_at": now.isoformat(timespec="seconds"), "error": error, "info": info, "off_since": off_since,
              "alerted": alerted}
    store.set_status("dns", not found, detail, now)
    return detail
