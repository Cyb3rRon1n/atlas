"""
Certificate watch (atlas certs check -> Posture page, Public exposure tab): once a day, opens a
TLS connection to every public hostname - the Traefik routes atlas already reads plus
security.cert_hosts - the way a browser would, and reads the certificate's expiry date.

Levels per host: ok, soon (cert_warn_days or fewer left), urgent (cert_urgent_days or fewer, or
expired), invalid (the browser would refuse it: wrong name, untrusted issuer), unreachable (no
alert - outages are the health checks' job). One alert per host each time its level gets worse,
and a "Resolved" once it is back to ok.
"""

import socket
import ssl
from datetime import datetime, timedelta, timezone

ALERTING = ("soon", "urgent", "invalid")
RANK = {"ok": 0, "unreachable": 0, "soon": 1, "invalid": 2, "urgent": 3}
CHECK_EVERY = timedelta(hours=24)


def _expiry(der):

    from cryptography import x509

    cert = x509.load_der_x509_certificate(der)
    issuer = cert.issuer.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME) or \
        cert.issuer.get_attributes_for_oid(x509.NameOID.COMMON_NAME)

    return cert.not_valid_after_utc, (issuer[0].value if issuer else "")


def fetch(host, port=443, timeout=5.0):
    """{"expires": datetime (UTC), "issuer": str, "error": "" | "invalid: ..." | "unreachable: ..."}"""

    def handshake(context):
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                return tls.getpeercert(binary_form=True)

    try:
        expires, issuer = _expiry(handshake(ssl.create_default_context()))
        return {"expires": expires, "issuer": issuer, "error": ""}
    except ssl.SSLCertVerificationError as error:
        reason = f"invalid: {error.verify_message or error.reason}"
    except (OSError, ssl.SSLError) as error:
        return {"expires": None, "issuer": "", "error": f"unreachable: {error}"}

    loose = ssl.create_default_context()      # still read the date of a cert a browser would refuse
    loose.check_hostname, loose.verify_mode = False, ssl.CERT_NONE
    try:
        expires, issuer = _expiry(handshake(loose))
    except (OSError, ssl.SSLError, ValueError):
        expires, issuer = None, ""

    return {"expires": expires, "issuer": issuer, "error": reason}


def hosts(routes, extra):
    """Plain hostnames from the Traefik routes (wildcards and regex rules skipped) plus security.cert_hosts."""

    names = {h.strip().lower() for r in routes for h in r.get("hosts", []) if h and not set(h) & set("*{}")}

    return sorted(names | {h.strip().lower() for h in extra if h.strip()})


def level(result, now, warn_days, urgent_days):

    if result["error"].startswith("unreachable"):
        return "unreachable", None
    days = (result["expires"] - now).days if result["expires"] else None
    if days is not None and days <= urgent_days:
        return "urgent", days
    if result["error"]:
        return "invalid", days
    if days is not None and days <= warn_days:
        return "soon", days

    return "ok", days


def _text(host, entry):

    days = entry["days"]
    if entry["level"] == "invalid":
        return f"**🔒 Certificate not trusted: {host}**\n• {entry['error'][len('invalid: '):]}\n\nSee Atlas → Posture."
    when = "expired" if days < 0 else "expires today" if days == 0 else f"expires in {days} day{'s' * (days != 1)}"
    icon = "🔴" if entry["level"] == "urgent" else "🟡"
    return (f"**{icon} Certificate {when}: {host}**\n• {entry['expires'][:10]}"
            + (f", issued by {entry['issuer']}" if entry["issuer"] else "") + "\n\nSee Atlas → Posture.")


def assess(previous, results, now, warn_days, urgent_days):
    """(alert texts, {host: entry}) - alerts when a host's level gets worse, resolves when back to ok."""

    old, entries, texts = previous or {}, {}, []
    for host, result in results.items():
        name, days = level(result, now, warn_days, urgent_days)
        entries[host] = {"level": name, "days": days, "issuer": result["issuer"], "error": result["error"],
                         "expires": result["expires"].isoformat() if result["expires"] else ""}
        before = (old.get(host) or {}).get("alerted")         # last level alerted about, kept while unreachable
        entries[host]["alerted"] = name if name in ALERTING else before if name == "unreachable" else None
        if name in ALERTING and RANK[name] > RANK.get(before or "ok", 0):
            texts.append(_text(host, entries[host]))
        elif name == "ok" and before:
            texts.append(f"**✅ Resolved: certificate for {host}**\n• valid for {days} more days")

    return texts, entries


def due(detail, now):

    checked = (detail or {}).get("checked_at")
    return not checked or now - datetime.fromisoformat(checked) >= CHECK_EVERY


def run(settings, store, now, *, get=fetch, send=None, force=False):
    """One daily check (skipped inside 24 h unless force). Status source 'certs'. Returns (texts, detail)."""

    from atlas import notify

    config = settings.security
    previous = ((store.statuses().get("certs") or {}).get("detail")) or {}
    if not force and not due(previous, now):
        return [], previous

    utc = now.replace(tzinfo=timezone.utc)
    results = {host: get(host, timeout=config.cert_timeout)
               for host in hosts(store.latest_routes(), config.cert_hosts)}
    texts, entries = assess(previous.get("hosts"), results, utc, config.cert_warn_days, config.cert_urgent_days)
    for text in texts:
        if send:
            send(text)
        elif notify.configured(settings.notify):
            notify.send(settings.notify, text)
    detail = {"checked_at": now.isoformat(timespec="minutes"), "hosts": entries}
    store.set_status("certs", not any(e["level"] in ALERTING for e in entries.values()), detail, now)

    return texts, detail
