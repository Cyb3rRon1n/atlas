"""
The Setup page (/settings): connect alerts, an AI model, switches, UniFi and Proxmox from the browser instead of
editing the config file.

Each card is one integration: Test checks the values as typed without saving them (alerts send a real test
message; the AI card only lists models, which costs nothing; switches, UniFi and Proxmox get one read-only request), Save stores them through lanxang.config.local,
Turn off removes them. A field the config file sets is shown read-only ("set in lanxang.yaml") and never written; a
secret the real environment (.env) sets is shown as "set in .env". Secret values are never put in the page.
"""

import json
import os
import re
import urllib.request
from collections import namedtuple

from pydantic import ValidationError

from lanxang.config.local import config_name
from lanxang.config import local
from lanxang.config.loader import build_config, load_config
from lanxang.web.render import _esc, plural, render_page

Field = namedtuple("Field", "key label kind path secret hint options", defaults=(None, None, "", ()))

CARDS = {
    "ntfy": ("ntfy — phone push", "The quickest way to get alerts on your phone: install the ntfy app, pick a "
             "hard-to-guess topic name and subscribe to it.", [
                 Field("url", "Server", "text", ("notify", "ntfy", "url"), hint="https://ntfy.sh, or your own"),
                 Field("topic", "Topic", "text", ("notify", "ntfy", "topic")),
                 Field("token", "Access token (only for a protected topic)", "secret", ("notify", "ntfy", "token"),
                       "LANXANG_NTFY_TOKEN")]),
    "webhooks": ("Discord, Slack or a webhook", "Paste a Discord or Slack webhook URL, or any URL that accepts "
                 "JSON. One per line.", [
                     Field("urls", "Webhook URLs", "lines", ("notify", "webhooks"), "LANXANG_WEBHOOK_")]),
    "email": ("Email", "Alerts by email through any SMTP server (your mail provider's, with an app password).", [
        Field("host", "SMTP server", "text", ("notify", "email", "host"), hint="smtp.example.org"),
        Field("port", "Port", "number", ("notify", "email", "port"), hint="587, or 465 for TLS"),
        Field("starttls", "Use STARTTLS (port 587)", "bool", ("notify", "email", "starttls")),
        Field("user", "Username", "text", ("notify", "email", "user")),
        Field("password", "Password", "secret", ("notify", "email", "password"), "LANXANG_SMTP_PASSWORD"),
        Field("sender", "From address (blank = username)", "text", ("notify", "email", "sender")),
        Field("to", "Send to (comma separated)", "list", ("notify", "email", "to"))]),
    "summary": ("Daily summary", "One message a day with what changed in the last 24 hours: new devices, alerts "
                "that started or cleared, public routes added or removed, devices gone quiet. Nothing changed, "
                "nothing sent. The time uses the alert time zone (set with quiet hours on the Alerts page; UTC "
                "until then).", [
                    Field("daily_summary", "Daily summary at (HH:MM, empty = off)", "text", ("notify", "daily_summary"),
                          hint="08:00 - uses the alert time zone")]),
    "ai": ("AI assistant", "Optional: powers Chat and the daily check-up. Ollama runs on your own hardware; "
           "Claude needs an Anthropic API key.", [
               Field("provider", "Provider", "select", ("intelligence", "provider"),
                     options=("none", "ollama", "anthropic")),
               Field("ollama_host", "Ollama address", "text", ("intelligence", "ollama_host"),
                     hint="http://192.168.1.10:11434"),
               Field("model", "Model", "text", ("intelligence", "model"), hint="qwen3:8b or claude-opus-5"),
               Field("api_key", "Anthropic API key", "secret", None, "ANTHROPIC_API_KEY")]),
    "switches": ("Switches and routers (SNMP)", "Draws every port on the Cabling page. Works with managed switches "
                 "and with routers, firewalls and NAS boxes that speak SNMP (OPNsense, pfSense, OpenWrt, MikroTik, "
                 "Synology, QNAP...). Prefer SNMPv3 (a read-only user, SHA + AES); use v2c with a read-only "
                 "community only when the device offers nothing else — it travels unencrypted. Saving a name that "
                 "exists updates it.", [
                     Field("name", "Name", "text", hint="core-switch"),
                     Field("host", "Address", "text", hint="192.168.1.2"),
                     Field("version", "SNMP version", "select", options=("3", "2c")),
                     Field("community", "v2c read-only community", "secret", None, "LANXANG_SNMP_{}_COMMUNITY"),
                     Field("snmp_user", "SNMPv3 user", "text", hint="lanxang"),
                     Field("priv", "Privacy", "select", options=("aes", "des")),
                     Field("auth", "Auth passphrase (SHA)", "secret", None, "LANXANG_SNMP_{}_AUTH"),
                     Field("priv_pass", "Privacy passphrase", "secret", None, "LANXANG_SNMP_{}_PRIV")]),
    "unifi": ("UniFi console", "Optional: adds UniFi gateway, AP and switch ports, port forwards and wired "
              "clients. Use a local account with the View Only role.", [
                  Field("url", "Console address", "text", ("wiring", "unifi", "url"), hint="https://192.168.1.1"),
                  Field("site", "Site", "text", ("wiring", "unifi", "site"), hint="default"),
                  Field("verify_ssl", "Check the console's certificate (off for the self-signed one)", "bool",
                        ("wiring", "unifi", "verify_ssl")),
                  Field("user", "Username", "secret", None, "LANXANG_UNIFI_USER"),
                  Field("password", "Password", "secret", None, "LANXANG_UNIFI_PASS")]),
    "proxmox": ("Proxmox VE", "Lists your VMs and containers and draws them under their host. An API token "
                "with the PVEAuditor role is enough.", [
                    Field("host", "Host", "text", ("proxmox", "host"), hint="192.168.1.10"),
                    Field("user", "User", "text", ("proxmox", "user"), hint="lanxang@pve"),
                    Field("token_name", "Token ID", "text", ("proxmox", "token_name"), hint="lanxang"),
                    Field("token_value", "Token secret", "secret", ("proxmox", "token_value"), "LANXANG_PROXMOX_TOKEN"),
                    Field("verify_ssl", "Check the host's certificate", "bool", ("proxmox", "verify_ssl"))]),
    "ups": ("UPS (NUT)", "Alerts on a power cut, a low battery, and when power is back. Lanxang reads a NUT server "
            "(Network UPS Tools): nut-server on the computer the UPS is plugged into, or a Synology, QNAP, Unraid or "
            "TrueNAS with its network UPS server switched on (allow this machine's address). Read-only, no login.", [
                Field("host", "UPS server address", "text", ("ups", "host"), hint="192.168.1.20"),
                Field("port", "Port", "number", ("ups", "port"), hint="3493"),
                Field("name", "UPS name (blank = every UPS on that server)", "text", ("ups", "name"), hint="ups")]),
    "router": ("OpenWrt router", "Reads the names your router's DHCP server gave each device, and who is on which "
               "Wi-Fi, so Devices can tell you what an unknown address is. Uses the router's web interface (the one "
               "LuCI uses) with its login — a separate read-only user works too. Read-only.", [
                   Field("url", "Router address", "text", ("router", "url"), hint="http://192.168.1.1"),
                   Field("user", "User", "text", ("router", "user"), hint="root"),
                   Field("password", "Password", "secret", None, "LANXANG_ROUTER_PASSWORD"),
                   Field("verify_ssl", "Check its certificate (off for a self-signed one)", "bool",
                         ("router", "verify_ssl"))]),
    "homeassistant": ("Home Assistant", "Watches Home Assistant itself and the smart home it runs: devices that "
                      "dropped out (all their sensors, switches, locks... unavailable for hours — TVs and players "
                      "that are just off don't count), low batteries, and updates waiting. Make a long-lived access "
                      "token in Home Assistant (your profile > Security). Read-only.", [
                          Field("url", "Address", "text", ("homeassistant", "url"),
                                hint="http://homeassistant.local:8123"),
                          Field("token", "Long-lived access token", "secret", None, "LANXANG_HA_TOKEN"),
                          Field("verify_ssl", "Check its certificate (off for a self-signed one)", "bool",
                                ("homeassistant", "verify_ssl"))]),
    "nas": ("TrueNAS or Synology", "Shows each pool's health and how full it is, and each disk's health and "
            "temperature; alerts when a pool isn't healthy or a disk fails, runs hot or wears out. TrueNAS: an API "
            "key (top-right user menu > API Keys; give its user the read-only admin role) and the https address. "
            "Synology: DSM only lets administrators read storage — make an admin account for Lanxang, deny it every "
            "folder and app, and leave two-factor off for it. Read-only.", [
                Field("kind", "Which one", "select", ("nas", "kind"), options=("truenas", "synology")),
                Field("url", "Web address", "text", ("nas", "url"), hint="https://192.168.1.20 (Synology: ...:5001)"),
                Field("user", "Username (the API key's user, or the Synology account)", "text", ("nas", "user"),
                      hint="lanxang"),
                Field("password", "API key (TrueNAS) or password (Synology)", "secret", None, "LANXANG_NAS_PASSWORD"),
                Field("name", "Call it (optional)", "text", ("nas", "name"), hint="nas"),
                Field("verify_ssl", "Check its certificate (off for a self-signed one)", "bool", ("nas", "verify_ssl"))]),
    "dnsfilter": ("Pi-hole or AdGuard Home", "Shows whether ad blocking is on, how many DNS questions were asked "
                  "and blocked, and which devices ask the most; alerts when blocking stays off. Pi-hole 6: its "
                  "password, or an app password from Settings > Web interface / API. AdGuard Home: its username "
                  "and password. Read-only.", [
                      Field("kind", "Which one", "select", ("dns_filter", "kind"), options=("pihole", "adguard")),
                      Field("url", "Web address", "text", ("dns_filter", "url"), hint="http://192.168.1.53"),
                      Field("user", "Username (AdGuard Home only)", "text", ("dns_filter", "user"), hint="admin"),
                      Field("password", "Password or app password", "secret", None, "LANXANG_DNS_PASSWORD"),
                      Field("verify_ssl", "Check its certificate (off for a self-signed one)", "bool",
                            ("dns_filter", "verify_ssl"))]),
    "internet": ("Internet view (Shodan)", "Once a day, asks Shodan's free InternetDB what it last saw on your "
                 "home's public IP: open ports and reported vulnerabilities. Alerts on a port you don't expect to be "
                 "open. Sends your home IP to Shodan once a day. Needs posture collection on (posture.enabled), "
                 "which reads that IP.", [
                     Field("expected_ports", "Ports you expect to be open (comma separated)", "list",
                           ("posture", "expected_ports"), hint="80, 443")]),
}
# "What's on your network?" - each tick shows the Setup cards that gear uses. Alert and AI cards always show.
GEAR = [
    ("switch", "Managed switch", "Cisco, Netgear, TP-Link, Zyxel, MikroTik...", ("switches",)),
    ("router", "Router or firewall", "OPNsense, pfSense, OpenWrt, MikroTik — SNMP; OpenWrt also its DHCP names",
     ("switches", "router")),
    ("nas", "NAS", "Synology, QNAP, TrueNAS — ports over SNMP, disk health from TrueNAS or Synology",
     ("switches", "nas")),
    ("unifi", "UniFi", "gateway, switches or access points", ("unifi",)),
    ("proxmox", "Proxmox server", "VMs and containers", ("proxmox",)),
    ("ups", "UPS", "battery backup, read through NUT", ("ups",)),
    ("dns", "Pi-hole or AdGuard Home", "network-wide ad blocking", ("dnsfilter",)),
    ("homeassistant", "Home Assistant", "smart home: offline devices, batteries, updates", ("homeassistant",)),
    ("plain", "Only an internet-provider or store-bought router", "ASUS, Netgear, eero, Fritz!Box, Deco...", ()),
]
HARDWARE_CARDS = ("switches", "unifi", "proxmox", "ups", "dnsfilter", "nas", "homeassistant", "router")
SNMP_GEAR = {"Ubiquiti": "unifi", "Synology": "nas", "QNAP": "nas", "MikroTik": "router"}   # SNMPv3 discovery maker


def _detected(config):
    """Gear atlas has already seen or been given: configured cards, and makers answering SNMPv3 discovery."""

    found = {"switch"} if config.wiring.switches else set()
    found |= {"unifi"} if config.wiring.unifi.enabled else set()
    found |= {"proxmox"} if config.proxmox.enabled else set()
    found |= {"ups"} if config.ups.enabled else set()
    found |= {"dns"} if config.dns_filter.enabled else set()
    found |= {"nas"} if config.nas.enabled else set()
    found |= {"homeassistant"} if config.homeassistant.enabled else set()
    found |= {"router"} if config.router.enabled else set()
    try:
        from lanxang.posture.store import PostureStore
        snmp = ((PostureStore().statuses().get("ports") or {}).get("detail") or {}).get("snmp") or {}
    except Exception:
        snmp = {}
    for info in snmp.values():
        maker = info.get("vendor") or ""
        found.add(SNMP_GEAR.get(maker, "switch" if maker and maker not in ("net-snmp (Linux)", "VMware") else None))

    return found - {None}


def _gear_html(chosen, detected):

    boxes = "".join(
        f'<label class="gear-item"><input type="checkbox" value="{key}" data-cards="{" ".join(cards)}"'
        f'{" checked" if key in chosen else ""}><span><b>{_esc(label)}</b>'
        f'{"<em>found</em>" if key in detected else ""}<small>{_esc(hint)}</small></span></label>'
        for key, label, hint, cards in GEAR)

    return ('<section class="card gear" id="gear"><h2>What\'s on your network?</h2><p class="muted">Lanxang finds '
            'every device by itself. Tick what you have and Setup shows the matching cards — each one adds detail, '
            'like switch ports or your VMs. Nothing here is required.</p>'
            f'<div class="gear-list">{boxes}</div><p class="muted gear-plain" hidden>Nothing more to connect: '
            'Lanxang maps your network from its own scan. Turn on alerts below, and add the services you care about '
            'under <a href="/uptime">Servers → Uptime</a>.</p></section>')


ENABLES = {"unifi": [("wiring", "unifi", "enabled")], "proxmox": [("proxmox", "enabled")], "ups": [("ups", "enabled")],
           "dnsfilter": [("dns_filter", "enabled")], "nas": [("nas", "enabled")],
           "homeassistant": [("homeassistant", "enabled")], "router": [("router", "enabled")],
           "internet": [("posture", "internet_view")]}
WIRING_CARDS = ("switches", "unifi")

ACTIONS = re.compile(r"^/api/settings/([a-z]+)/(test|save|off|dismiss)$")


def _get(data, path):

    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]

    return data


def _put(settings, path, value):
    """Set settings[path] = value in place; None marks the setting for removal when saved."""

    node = settings
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _from_env(name):
    """A secret the real environment sets - .env wins over the Setup page, so the page can't change it."""

    applied = name in local._APPLIED

    return bool(name) and bool(os.environ.get(name)) and not applied


def _locked(field):

    return bool(field.path) and local.locked(field.path)


def _webhook_names():

    return sorted((n for n in local.secret_names() if n.startswith("LANXANG_WEBHOOK_")),
                  key=lambda n: int(n.rsplit("_", 1)[1]) if n.rsplit("_", 1)[1].isdigit() else 0)


def _saved(name):

    return name in local.secret_names() or _from_env(name)


def _switch_changes(body, off):
    """Add, update (same name) or remove one switch; the list is the Setup page's own, the config file's locks it."""

    from lanxang.wiring import env_key

    if local.locked(("wiring", "switches")):
        raise ValueError(f"The switches are set in {config_name()} — edit them there.")
    name = str(body.get("name") or "").strip()
    if not name:
        raise ValueError("Enter the switch name.")
    saved = _get(local.read_settings(), ("wiring", "switches")) or []
    others = [s for s in saved if s.get("name") != name]
    # A blank user keeps a saved switch's own; a new switch gets the name the hint suggests.
    user = next((s.get("snmp_user") for s in saved if s.get("name") == name and s.get("snmp_user")), "lanxang")
    every = {key: secret.format(env_key(name)) for key, secret in (("auth", "LANXANG_SNMP_{}_AUTH"),
                                                                    ("priv_pass", "LANXANG_SNMP_{}_PRIV"),
                                                                    ("community", "LANXANG_SNMP_{}_COMMUNITY"))}
    if off:
        return {"wiring": {"switches": others or None}}, {n: None for n in every.values() if not _from_env(n)}

    host = str(body.get("host") or "").strip()
    if not host:
        raise ValueError("Enter the switch address.")
    version = "2c" if str(body.get("version") or "3") == "2c" else "3"
    names = {key: n for key, n in every.items() if (key == "community") == (version == "2c")}
    secrets = {n: str(body[key]) for key, n in names.items() if body.get(key) and not _from_env(n)}
    if any(n not in secrets and not _saved(n) for n in names.values()):
        raise ValueError("Enter the read-only community." if version == "2c" else "Enter both passphrases.")
    secrets |= {n: None for key, n in every.items() if key not in names and _saved(n) and not _from_env(n)}
    switch = {"name": name, "host": host, "snmp_user": str(body.get("snmp_user") or "").strip() or user,
              "priv": body.get("priv") or "aes"} | ({"version": "2c"} if version == "2c" else {})

    return {"wiring": {"switches": others + [switch]}}, secrets


def _changes(card, body, off=False):
    """(settings patch, secrets) a Save (or Turn off) of this card would write; locked fields are left alone."""

    settings, secrets = _switch_changes(body, off) if card == "switches" else _field_changes(card, body, off)
    for path in ENABLES.get(card, ()):
        if not local.locked(path):
            _put(settings, path, None if off else True)
    if card in WIRING_CARDS and not local.locked(("wiring", "enabled")):
        merged = local._merge(local.read_settings(), settings)       # the cabling scan runs while either is set
        wanted = _get(merged, ("wiring", "switches")) or _get(merged, ("wiring", "unifi", "enabled"))
        _put(settings, ("wiring", "enabled"), True if wanted else None)

    return settings, secrets


def _field_changes(card, body, off):

    settings, secrets = {}, {}
    for field in CARDS[card][2]:
        if _locked(field) or (field.kind == "secret" and _from_env(field.secret)):
            continue
        value = None if off else body.get(field.key)
        if field.kind == "lines":
            old = _webhook_names()
            if off or (value is not None and str(value).strip()):
                urls = [] if off else [u.strip() for u in str(value).splitlines() if u.strip()]
                for url in urls:
                    if not re.match(r"^https?://", url):
                        raise ValueError(f"not a web address: {url[:40]}")
                names = [f"{field.secret}{i}" for i in range(1, len(urls) + 1)]
                secrets.update({name: None for name in old}, **dict(zip(names, urls)))
                _put(settings, field.path, ["${%s}" % n for n in names] or None)
            continue
        if field.kind == "secret":
            if off:
                secrets[field.secret] = None
                if field.path:
                    _put(settings, field.path, None)
            elif value:
                secrets[field.secret] = str(value)
                if field.path:
                    _put(settings, field.path, "${%s}" % field.secret)
            continue
        if value is None and not off:
            continue
        if off:
            value = None
        elif field.kind == "bool":
            value = bool(value)
        elif field.kind == "number":
            if str(value).strip() == "":
                value = None
            elif not str(value).strip().isdigit():
                raise ValueError(f"{field.label} must be a number")
            else:
                value = int(value)
        elif field.kind == "list":
            value = [part.strip() for part in str(value).split(",") if part.strip()] or None
        else:
            value = str(value).strip() or None
            if field.kind == "select" and value not in field.options:
                raise ValueError(f"{field.label} must be one of: {', '.join(field.options)}")
        _put(settings, field.path, value)      # None (an emptied field) removes it: the default applies

    return settings, secrets


def _candidate(card, body):
    """The config these unsaved values would give, with their secrets visible only to this check."""

    settings, secrets = _changes(card, body)
    environ = {**os.environ, **{name: value for name, value in secrets.items() if value}}
    for name, value in secrets.items():
        if value is None:
            environ.pop(name, None)

    return build_config(local._merge(local.read_settings(), settings), environ), environ


def _test_ai(config, environ):

    intelligence = config.intelligence
    if intelligence.provider == "none":
        return False, "No AI selected — choose ollama or anthropic first."
    if intelligence.provider == "ollama":
        url = intelligence.ollama_host.rstrip("/") + "/api/tags"
        with urllib.request.urlopen(url, timeout=8) as response:
            models = [m.get("name", "") for m in json.load(response).get("models", [])]
        if not models:
            return False, "Ollama answered but has no models — run: ollama pull qwen3:8b"
        if intelligence.model not in models and f"{intelligence.model}:latest" not in models:
            return False, f"Ollama is reachable, but {intelligence.model or 'no model'} isn't installed. " \
                          f"It has: {', '.join(models[:8])}"
        return True, f"Connected to Ollama: {intelligence.model} is installed ({plural(len(models), 'model')})."

    import anthropic

    key = environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return False, "Enter an Anthropic API key."
    try:
        ids = [model.id for model in anthropic.Anthropic(api_key=key).models.list(limit=100, timeout=10).data]
    except anthropic.AuthenticationError:
        return False, "Anthropic refused the key — check it, or create a new one in the Anthropic Console."
    if intelligence.model and intelligence.model not in ids:
        return False, f"The key works, but model {intelligence.model} isn't available to it. " \
                      f"Available: {', '.join(ids[:6])}"
    return True, "The key works" + (f" and {intelligence.model} is available." if intelligence.model else ".")


def _test_network(card, body, config, environ):

    from lanxang.wiring import WiringError

    try:
        if card == "switches":
            from lanxang.wiring.snmp import probe_switch
            name = str(body.get("name") or "").strip()
            switch = next((s for s in config.wiring.switches if s.name == name), None)
            if switch is None:
                return False, f"No switch named {name or '(blank)'} — names: " \
                              f"{', '.join(s.name for s in config.wiring.switches) or 'none yet'}"
            sys_name, description = probe_switch(switch, environ, config.wiring.timeout)
            return True, f"Connected to {sys_name or switch.host}" + (f": {description[:90]}" if description else ".")
        if card == "unifi":
            from lanxang.wiring.unifi import _session
            if not config.wiring.unifi.url:
                return False, "Enter the console address."
            devices = _session(config.wiring.unifi, environ, config.wiring.timeout, None,
                               lambda get: get("stat/device"))
            return True, f"Signed in: the console reports {len(devices)} UniFi device{'s' * (len(devices) != 1)}."
    except WiringError as error:
        return False, str(error)

    from lanxang.proxmox.client import connect

    proxmox = config.proxmox
    if not (proxmox.host and proxmox.user and proxmox.token_name and proxmox.token_value):
        return False, "Enter the host, user, token ID and token secret."
    from proxmoxer.core import AuthenticationError, ResourceException
    from requests.exceptions import RequestException

    api = connect(proxmox.host, proxmox.user, token_name=proxmox.token_name, token_value=proxmox.token_value,
                  verify_ssl=proxmox.verify_ssl)
    if api is None:
        return False, "Couldn't set up the Proxmox connection — check the host."
    try:
        version = api.version.get().get("version", "?")
        nodes = api.nodes.get()
    except (AuthenticationError, ResourceException) as error:
        if getattr(error, "status_code", 401) in (401, 403):
            return False, "Proxmox refused the token — check the user, token ID and secret, and that the token " \
                          "has the PVEAuditor role."
        return False, f"Proxmox answered with an error: {error}"
    except RequestException as error:
        if "SSL" in type(error).__name__ or "certificate" in str(error).lower():
            return False, f"Proxmox's certificate isn't trusted — untick the certificate check for its self-signed one."
        return False, f"No answer from Proxmox at {proxmox.host}:8006 — check the host and that it's on."
    return True, f"Connected: Proxmox VE {version}, {len(nodes)} node{'s' * (len(nodes) != 1)}."


def _test(card, body):

    from lanxang import notify

    if card == "switches" and local.locked(("wiring", "switches")):    # test the config file's switch by name
        config, environ = load_config(), dict(os.environ)
    else:
        config, environ = _candidate(card, body)
    if card in ("switches", "unifi", "proxmox"):
        return _test_network(card, body, config, environ)
    if card == "ups":
        from lanxang.monitoring.ups import STATES, fetch, summarize
        if not config.ups.host:
            return False, "Enter the UPS server address."
        try:
            upses = fetch(config.ups.host, config.ups.port, config.ups.timeout, config.ups.name)
        except OSError as error:
            return False, (f"No answer from {config.ups.host}:{config.ups.port} — check the address, that the "
                           f"network UPS server is on and allows this machine ({error}).")
        return True, "Connected: " + "; ".join(
            f"{name} {STATES[info['state']]}" + (f", {info['charge']:.0f}% charged" if info["charge"] is not None else "")
            for name, info in ((name, summarize(v)) for name, v in upses.items())) + "."
    if card == "dnsfilter":
        from lanxang.monitoring.dnsfilter import DnsFilterError, fetch
        try:
            info = fetch(config.dns_filter, environ)
        except DnsFilterError as error:
            return False, str(error)
        return True, (f"Connected: {info['kind']}, ad blocking {'on' if info['blocking'] else 'OFF'}, "
                      f"{info['queries'] or 0:,} DNS questions, {info['blocked'] or 0:,} blocked.")
    if card == "router":
        from lanxang.devices.router import RouterError, fetch
        try:
            clients = fetch(config.router, environ)
        except RouterError as error:
            return False, str(error)
        named = sum(bool(c["hostname"]) for c in clients)
        return True, (f"Connected: {len(clients)} DHCP lease(s), {named} with a name, "
                      f"{sum(bool(c['wifi']) for c in clients)} on Wi-Fi.")
    if card == "homeassistant":
        from lanxang.monitoring.homeassistant import HomeAssistantError, fetch
        try:
            info = fetch(config.homeassistant, environ)
        except HomeAssistantError as error:
            return False, str(error)
        return True, (f"Connected: Home Assistant {info['version']}, {plural(len(info['offline']), 'device')} offline, "
                      f"{plural(len(info['batteries']), 'low battery', 'low batteries')}, {plural(len(info['updates']), 'update')} waiting.")
    if card == "nas":
        from lanxang.monitoring.nas import NasError, fetch
        try:
            info = fetch(config.nas, environ)
        except NasError as error:
            return False, str(error)
        unhealthy = [p["name"] for p in info["pools"] if p["health"] not in ("ONLINE", "NORMAL")]
        return True, (f"Connected: {info['kind']}, {len(info['pools'])} pool(s), {len(info['disks'])} disk(s)"
                      + (f"; not healthy: {', '.join(unhealthy)}." if unhealthy else ", all pools healthy."))
    if card == "internet":
        from lanxang.posture.internet_view import lookup
        from lanxang.posture.store import PostureStore
        ip = ((PostureStore().statuses().get("public_ip") or {}).get("detail") or {}).get("ip")
        if not ip:
            return False, "Lanxang doesn't know your public IP yet — turn on posture collection (posture.enabled)."
        found = lookup(ip, config.posture.internet_view_url)
        if not found["ok"]:
            return False, f"Couldn't reach Shodan: {found['error']}"
        if not found["known"]:
            return True, f"Shodan knows nothing about {ip}."
        return True, f"Shodan sees {plural(len(found['ports']), 'open port')} on {ip}" + (
            f": {', '.join(map(str, found['ports']))}." if found["ports"] else ".")
    alerts = config.notify
    if card == "summary":
        if not alerts.daily_summary:
            return False, "Enter a time like 08:00."
        return True, (f"Looks right: sent daily from {alerts.daily_summary} {alerts.timezone or 'UTC'}, when something "
                      "changed.")
    if card == "ntfy":
        if not (alerts.ntfy.url and alerts.ntfy.topic):
            return False, "Enter the server and topic."
        notify.send_ntfy(alerts.ntfy, notify.test_text(config.display))
        return True, f"Sent — it should appear on every device subscribed to {alerts.ntfy.topic}."
    if card == "webhooks":
        if not alerts.webhooks:
            return False, "Enter at least one webhook URL."
        for url in alerts.webhooks:
            notify.send_webhook(url, notify.test_text(config.display))
        return True, f"Sent to {len(alerts.webhooks)} webhook{'s' * (len(alerts.webhooks) != 1)}."
    if card == "email":
        if not (alerts.email.host and alerts.email.to):
            return False, "Enter the SMTP server and at least one address to send to."
        notify.send_email(alerts.email, notify.test_text(config.display))
        return True, f"Sent to {', '.join(alerts.email.to)} — check the inbox (and spam)."

    return _test_ai(config, environ)


def handle_post(path, body):
    """(status, payload) for POST /api/settings/<card>/<test|save|off>, or None when the path isn't ours."""

    match = ACTIONS.match(path)
    if not match:
        return None
    card, action = match.groups()
    if card == "gear" and action == "save":
        gear = body.get("gear") if isinstance(body, dict) else None
        keys = {key for key, *_ in GEAR}
        if not isinstance(gear, list) or not set(gear) <= keys:
            return 400, {"error": "unknown gear"}
        local.save_settings({"setup": {"gear": sorted(set(gear))}})
        return 200, {"ok": True}
    if card == "display" and action == "save":
        return _save_display(body)
    if card not in CARDS:
        return 404, {"error": "no such setting"}
    body = body if isinstance(body, dict) else {}

    if action == "dismiss":
        return _dismiss(card, body)
    try:
        if action == "test":
            try:
                ok, message = _test(card, body)
            except ValueError:
                raise
            except Exception as error:      # couldn't reach it: say why, plainly
                ok, message = False, f"Couldn't connect: {getattr(error, 'reason', None) or error}"
            return (200 if ok else 400), ({"ok": True, "message": message} if ok else {"error": message})
        settings, secrets = _changes(card, body, off=action == "off")
        build_config(local._merge(local.read_settings(), settings),
                     {**os.environ, **{name: value for name, value in secrets.items() if value}})
    except ValidationError as error:
        problem = error.errors()[0]
        return 400, {"error": f"{'.'.join(map(str, problem['loc']))}: {problem['msg']}"}
    except ValueError as error:
        return 400, {"error": str(error)}

    if secrets:
        local.save_secrets(secrets)
    if settings:
        local.save_settings(settings)
    if card == "internet" and action == "off":       # resolve its alerts and drop the last answer right away
        from lanxang.clock import utcnow
        from lanxang.posture.internet_view import turn_off
        from lanxang.posture.store import PostureStore
        turn_off(PostureStore(), utcnow())

    return 200, {"ok": True, "message": "Turned off." if action == "off" else "Saved."}


def _save_display(body):
    """Preferences > Time & date: clock, time_zone, date_format into display: (the config file's values still win)."""

    from lanxang.config.models import DisplayConfig, zone_problem

    body = body if isinstance(body, dict) else {}
    fields = {key: body[key] for key in DisplayConfig.model_fields if key in body}
    if not fields or not all(isinstance(value, str) for value in fields.values()):
        return 400, {"error": "Send clock, time_zone and date_format."}
    if "time_zone" in fields and zone_problem(fields["time_zone"].strip()):
        return 400, {"error": zone_problem(fields["time_zone"].strip())}
    try:
        chosen = DisplayConfig(**fields)
    except ValidationError as error:
        return 400, {"error": str(error.errors()[0]["msg"]).removeprefix("Value error, ")}
    current = load_config().display
    pinned = [key for key in fields if local.locked(("display", key)) and getattr(chosen, key) != getattr(current, key)]
    if pinned:
        return 400, {"error": f"display.{pinned[0]} is set in {config_name()} — change it there."}
    local.save_settings({"display": {key: getattr(chosen, key) for key in fields}})

    return 200, {"ok": True, "message": "Saved.", "display": load_config().display.model_dump()}


def _dismiss(card, body):
    """'Don't ask': never suggest this address (or MAC) for a login again."""

    key = str(body.get("ip") or "").strip().lower()
    if card != "switches" or not re.fullmatch(r"[0-9a-f.:]{3,39}", key):
        return 400, {"error": "Nothing to dismiss."}
    if local.locked(("wiring", "not_managed")):
        return 400, {"error": f"wiring.not_managed is set in {config_name()} — add it there."}
    current = _get(local.read_settings(), ("wiring", "not_managed")) or []
    if key not in current:
        local.save_settings({"wiring": {"not_managed": current + [key]}})

    return 200, {"ok": True, "message": "Won't suggest it again."}


def _found_html(suggested):

    if not suggested:
        return ""
    rows = "".join(
        f'<li><b>{_esc(entry["name"])}</b> {_esc(entry["ip"])} <span class="muted">— {_esc("; ".join(entry["why"]))}'
        f'</span><br><button data-use="{_esc(entry["ip"])}" data-name="{_esc(entry["suggested_name"])}">Use</button> '
        f'<button data-dismiss="{_esc(entry["ip"])}">Don\'t ask</button></li>'
        for entry in suggested)

    return f'<div class="found"><p><b>Found on your network</b> — these could show their ports with a login:</p><ul>{rows}</ul></div>'


def _field_html(card, field, config):

    name = f"{card}-{field.key}"
    locked = _locked(field)
    note = f' <span class="lock">set in {config_name()}</span>' if locked else ""
    disabled = " disabled" if locked else ""
    value = _get(config.model_dump(), field.path) if field.path else None

    if field.kind == "secret" and "{}" in field.secret:     # per-switch: named by the switch
        return (f'<label for="{name}">{_esc(field.label)}</label><input id="{name}" name="{field.key}" '
                f'type="password" autocomplete="new-password" placeholder="blank keeps a saved switch\'s passphrase">')
    if field.kind == "secret":
        env = _from_env(field.secret)
        saved = field.secret in local.secret_names() or env or (locked and value)
        placeholder = "set in .env" if env else "saved — leave blank to keep it" if saved else "not set"
        return (f'<label for="{name}">{_esc(field.label)}{note}</label>'
                f'<input id="{name}" name="{field.key}" type="password" autocomplete="new-password" '
                f'placeholder="{_esc(placeholder)}"{" disabled" if env or locked else ""}>')
    if field.kind == "lines":
        count = len(value or [])
        placeholder = (f"{count} saved — paste new ones to replace them" if count else "https://discord.com/api/webhooks/...")
        return (f'<label for="{name}">{_esc(field.label)}{note}</label>'
                f'<textarea id="{name}" name="{field.key}" placeholder="{_esc(placeholder)}"{disabled}></textarea>')
    if field.kind == "bool":
        return (f'<label><input type="checkbox" name="{field.key}"{" checked" if value else ""}{disabled}> '
                f'{_esc(field.label)}{note}</label>')
    if field.kind == "select":
        options = "".join(f'<option{" selected" if option == value else ""}>{_esc(option)}</option>'
                          for option in field.options)
        return f'<label for="{name}">{_esc(field.label)}{note}</label><select id="{name}" name="{field.key}"{disabled}>{options}</select>'
    shown = ", ".join(map(str, value or [])) if field.kind == "list" else "" if value is None else value
    kind = "number" if field.kind == "number" else "text"

    return (f'<label for="{name}">{_esc(field.label)}{note}</label>'
            f'<input id="{name}" name="{field.key}" type="{kind}" value="{_esc(shown)}" '
            f'placeholder="{_esc(field.hint)}" size="40"{disabled}>')


def _on(card, config):

    alerts = config.notify
    return {"ntfy": bool(alerts.ntfy.url and alerts.ntfy.topic), "webhooks": bool(alerts.webhooks),
            "email": bool(alerts.email.host and alerts.email.to),
            "summary": bool(alerts.daily_summary),
            "ai": config.intelligence.provider != "none", "switches": bool(config.wiring.switches),
            "unifi": config.wiring.unifi.enabled, "proxmox": config.proxmox.enabled, "ups": config.ups.enabled,
            "dnsfilter": config.dns_filter.enabled, "nas": config.nas.enabled,
            "homeassistant": config.homeassistant.enabled, "router": config.router.enabled,
            "internet": config.posture.internet_view}[card]


SCRIPT = """
<script>
const fill = (ip, name) => {
  const form = document.querySelector('form[data-card="switches"]');
  if (!form) return;
  form.closest("section").hidden = false;
  form.elements.host.value = ip;
  if (name && !form.elements.name.value) form.elements.name.value = name;
  form.elements.name.focus();
  form.scrollIntoView({block: "center"});
};
// Show only the login fields the chosen SNMP version uses (v2c: a community; v3: user + passphrases).
const snmpVersion = document.getElementById("switches-version");
const showVersion = () => {
  const v2 = snmpVersion && snmpVersion.value === "2c";
  for (const key of ["community", "snmp_user", "priv", "auth", "priv_pass"]) {
    const input = document.getElementById("switches-" + key);
    const label = input && document.querySelector('label[for="switches-' + key + '"]');
    const hide = (key === "community") !== v2;
    if (input) { input.hidden = hide; input.disabled = hide; }
    if (label) label.hidden = hide;
  }
};
if (snmpVersion) { snmpVersion.addEventListener("change", showVersion); showVersion(); }
// "What's on your network?": show the hardware cards for what's ticked, save the ticks.
const gearBoxes = [...document.querySelectorAll("#gear input[type=checkbox]")];
const hardware = ["switches", "unifi", "proxmox", "ups", "dnsfilter", "nas", "homeassistant", "router"];
const showGear = () => {
  const want = new Set(gearBoxes.filter((box) => box.checked).flatMap((box) => box.dataset.cards.split(" ")));
  for (const card of hardware) {
    const section = document.getElementById(card);
    if (section && !section.querySelector(".badge.on")) section.hidden = !want.has(card);
  }
  const plain = document.querySelector(".gear-plain");
  if (plain) plain.hidden = !(gearBoxes.some((b) => b.checked) && want.size === 0);
};
for (const box of gearBoxes) box.addEventListener("change", () => {
  showGear();
  fetch("/api/settings/gear/save", {method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({gear: gearBoxes.filter((b) => b.checked).map((b) => b.value)})});
});
showGear();
const linked = document.getElementById(location.hash.slice(1));   // /settings#proxmox from Home: show that card
if (linked && linked.hidden) { linked.hidden = false; linked.scrollIntoView(); }
document.getElementById("show-all")?.addEventListener("click", (event) => {
  event.preventDefault();
  for (const card of hardware) { const section = document.getElementById(card); if (section) section.hidden = false; }
});
const wanted = new URLSearchParams(location.search);
if (wanted.get("add")) fill(wanted.get("add"), wanted.get("name"));
document.addEventListener("click", async (event) => {
  const use = event.target.closest("[data-use]"), skip = event.target.closest("[data-dismiss]");
  if (use) { event.preventDefault(); fill(use.dataset.use, use.dataset.name); return; }
  if (skip) {
    event.preventDefault();
    const response = await fetch("/api/settings/switches/dismiss", {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({ip: skip.dataset.dismiss})});
    if (response.ok) skip.closest("li").remove();
    return;
  }
  const button = event.target.closest("[data-act]");
  if (!button) return;
  event.preventDefault();
  const form = button.closest("form"), status = form.querySelector(".status");
  const body = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    body[el.name] = el.type === "checkbox" ? el.checked : el.value;
  }
  status.className = "status muted"; status.textContent = button.dataset.act === "test" ? "Testing..." : "Saving...";
  try {
    const response = await fetch("/api/settings/" + form.dataset.card + "/" + button.dataset.act, {method: "POST",
      credentials: "same-origin", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json().catch(() => ({}));
    status.className = "status " + (response.ok ? "ok" : "bad");
    status.textContent = response.ok ? data.message : (data.error || ("Failed: " + response.status +
      (response.status === 401 || response.status === 403 ? " (session expired? reload the page)" : "")));
    if (response.ok && button.dataset.act !== "test") setTimeout(() => location.reload(), 900);
  } catch (error) { status.className = "status bad"; status.textContent = "Request failed: " + error; }
});
</script>
"""

STYLE = """<style>
.setup { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:1rem; }
.setup form input[type=text], .setup form input[type=number], .setup form input[type=password],
.setup form select, .setup form textarea { width:100%; box-sizing:border-box; }
.setup .badge { font-size:.75rem; border-radius:999px; padding:1px 8px; margin-left:.4rem; vertical-align:middle;
  border:1px solid var(--line2); color:var(--muted); }
.setup .badge.on { border-color:var(--ok-line); color:var(--green); }
.setup .status { min-height:1.5em; margin:.6rem 0 .2rem; }
.setup .status.ok { color:var(--green); } .setup .status.bad { color:var(--red); }
.setup .lock { font-size:.75rem; border:1px solid var(--line2); border-radius:999px; padding:0 6px; margin-left:.3rem; }
.setup input:disabled, .setup select:disabled, .setup textarea:disabled { opacity:.55; cursor:not-allowed; }
.setup .buttons { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; margin-top:auto; }
.setup .buttons .off { margin-right:auto; }
.setup > .card { display:flex; flex-direction:column; } .setup > .card[hidden] { display:none; }
.setup > .card > form { flex:1; display:flex; flex-direction:column; }
.setup .found { border:1px dashed var(--line2); border-radius:8px; padding:.4rem .8rem; margin-bottom:.6rem; }
.gear-list { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:.5rem; margin:.6rem 0; }
.gear-item { display:flex; gap:.6rem; align-items:flex-start; border:1px solid var(--line2); border-radius:8px;
  padding:.55rem .7rem; cursor:pointer; }
.gear-item:has(input:checked) { border-color:var(--accent); background:color-mix(in srgb, var(--accent) 10%, transparent); }
.gear-item input { margin-top:.25rem; } .gear-item small { display:block; color:var(--muted); }
.gear-item em { font-style:normal; font-size:.7rem; color:var(--green); border:1px solid var(--ok-line); border-radius:999px;
  padding:0 6px; margin-left:.4rem; }
.gear { margin-bottom:1rem; }
.setup .found ul { margin:.3rem 0; padding-left:1rem; } .setup .found li { margin:.3rem 0; }
</style>"""


def render_settings_page():

    from lanxang.wiring import suggest

    config = load_config()
    suggested = suggest.current()
    detected = _detected(config)
    saved_gear = (local.read_settings().get("setup") or {}).get("gear")
    chosen = set(saved_gear) if isinstance(saved_gear, list) else detected
    wanted = {card for key, *_, cards in GEAR if key in chosen for card in cards}
    cards = []
    for card, (title, intro, fields) in CARDS.items():
        on = _on(card, config)
        hidden = card in HARDWARE_CARDS and card not in wanted and not on
        saved = _found_html(suggested) if card == "switches" else ""
        if card == "switches" and config.wiring.switches:
            where = f" (from {config_name()})" if local.locked(("wiring", "switches")) else ""
            saved += '<ul class="saved">' + "".join(
                f"<li><b>{_esc(s.name)}</b> {_esc(s.host)} — "
                + (f"SNMPv2c (community){where}</li>" if s.version == "2c" else f"user {_esc(s.snmp_user)}, {s.priv}{where}</li>")
                for s in config.wiring.switches) + "</ul>"
        cards.append(
            f'<section class="card" id="{card}"{" hidden" if hidden else ""}><h2>{_esc(title)}<span class="badge{" on" if on else ""}">{"on" if on else "off"}'
            f'</span></h2><p class="muted">{_esc(intro)}</p>{saved}<form data-card="{card}">'
            + "".join(_field_html(card, field, config) for field in fields) +
            '<p class="status muted" role="status"></p><div class="buttons">'
            + (f'<button class="danger off" data-act="off">{"Remove this switch" if card == "switches" else "Turn off"}</button>'
               if on else "")
            + f'<button data-act="test">{"Send test" if card in ("ntfy", "webhooks", "email") else "Test"}</button>'
            '<button class="primary" data-act="save">Save</button></div></form></section>')

    body = (STYLE + '<p class="muted">Changes here take effect within a minute, no restart. Anything set in '
            f'{config_name()} or .env stays read-only here — edit it there. Passwords and keys are stored privately '
            'on this machine and never shown again.</p>' + _gear_html(chosen, detected)
            + '<div class="setup">' + "".join(cards) + "</div>"
            '<p class="muted"><a href="#" id="show-all">Show every integration</a></p>' + SCRIPT)

    return render_page("Setup", body, active="settings")
