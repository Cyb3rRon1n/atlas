"""The watchers atlas-scan runs: LAN scan, map, posture, access, wiring, ports, certificates, uptime, UPS."""

import json

import typer
from lanxang.config.local import config_name
from lanxang.config import load_config
from lanxang.proxmox import (
    connect,
    discover_resources,
)
from lanxang.reporting.trends import build_trends_payload
from lanxang.events import AtlasEvent
from lanxang.knowledge.store import KnowledgeStore
from lanxang.core.application import application

from lanxang.cli.app import app, console, _print_trend_summaries
from lanxang.clock import utcnow


@app.command(name="map")
def network_map(
    json_output: bool = typer.Option(False, "--json", help="Print the map as JSON")
):
    """
    Build the network map (lanxang web /map): containers by network with
    their public hostnames, Proxmox guests, configured LAN hosts'
    reachability, the AI endpoint - and what atlas may act on. Saved so
    the web view can render it; run it on a schedule to keep
    the map current.
    """

    from lanxang.discovery.topology import collect_topology
    from lanxang.docker.manager import get_client

    settings = load_config()

    guests = []
    ok, error = True, ""

    if settings.proxmox.enabled:

        client = connect(
            settings.proxmox.host,
            settings.proxmox.user,
            password=settings.proxmox.password,
            token_name=settings.proxmox.token_name,
            token_value=settings.proxmox.token_value,
            verify_ssl=settings.proxmox.verify_ssl
        )

        if client is None:
            ok, error = False, "could not connect to Proxmox"

        else:
            try:
                guests = discover_resources(client)

            except Exception as exc:  # token auth means connect() did no I/O - this can be the first real failure
                guests, ok, error = [], False, str(exc)

        from lanxang.devices import Sighting
        from lanxang.devices.store import InventoryStore

        InventoryStore().record_run(
            "proxmox",
            [Sighting("proxmox", f"pve:{guest['vmid']}", hostname=guest.get("name"),
                      detail={"type": guest.get("type"), "status": guest.get("status")})
             for guest in guests if not guest.get("template") and guest.get("status") == "running"],
            ok=ok,
            error=error
        )

    topology = collect_topology(settings, docker_client=get_client(), proxmox_resources=guests)

    runtime = application.runtime

    runtime.environment.update("topology", topology)

    KnowledgeStore().save_environment(runtime.environment)

    if json_output:
        print(json.dumps(topology, indent=2))
        return

    docker_networks = topology["docker"]["networks"]

    console.print("[bold blue]Lanxang Network Map[/bold blue]\n")
    console.print(f"{topology['host']}: {sum(len(m) for m in docker_networks.values())} containers on {len(docker_networks)} networks")

    if settings.proxmox.enabled:
        running = sum(guest["status"] == "running" for guest in topology["proxmox"]["guests"])
        console.print(f"Proxmox {settings.proxmox.host}: {running}/{len(topology['proxmox']['guests'])} guests running")

    for host in topology["lan"]:
        mark = "[green]✓[/green]" if host["reachable"] else "[red]✗[/red]"
        console.print(f"{mark} {host['name']} ({host['address']}) {host['role']}")

    console.print("\nSaved - view it at /map in lanxang web.")


@app.command(name="scan")
def lan_scan(
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON")
):
    """
    Find every device on the LAN and update the device inventory: links
    each sighting to a known device when certain, queues new devices for
    triage, and sends alerts (every notify: channel) for new devices and
    for important devices gone quiet. Run by the atlas-scan container.
    """

    from datetime import datetime
    from lanxang.devices import lan
    from lanxang.devices.notify import deliver
    from lanxang.devices.store import InventoryStore

    settings = load_config()

    if not settings.scan.enabled:
        console.print(f"LAN scanning is off (scan.enabled: false in {config_name()}).")
        return

    store = InventoryStore()
    store.import_manual_hosts(settings.map.hosts)

    try:
        subnets, sightings = lan.scan(settings.scan.subnets, settings.scan.timeout)

    except Exception as error:  # any failure is a failed source run, shown on Coverage
        store.record_run("lan", [], ok=False, error=str(error))
        console.print(f"[red]Scan failed:[/red] {error}")
        raise typer.Exit(1)

    if settings.scan.discover:
        from lanxang.devices.discover import discover
        announced = discover()
        for sighting in sightings:
            if sighting.ip in announced:
                sighting.detail["announce"] = announced[sighting.ip]

    result = store.record_run("lan", sightings)
    result["subnets"] = subnets
    from lanxang.devices import identify
    identify.refresh(utcnow())     # the maker list for naming new devices; monthly, skipped offline
    result["offline"] = store.queue_offline()
    result["notify_errors"] = deliver(store, settings.notify, display=settings.display)
    from lanxang.devices.notify import report_alerts
    report_alerts(store, store.devices(), utcnow(), display=settings.display)
    if settings.dns_filter.enabled:
        try:
            from lanxang.monitoring.dnsfilter import run as dns_run
            from lanxang.posture.store import PostureStore
            dns_run(settings, PostureStore(), utcnow())
        except Exception as error:                      # Pi-hole trouble never fails the LAN scan
            console.print(f"[yellow]Pi-hole / AdGuard Home check failed: {error}[/yellow]")

    if settings.nas.enabled:
        try:
            from lanxang.monitoring.nas import run as nas_run
            from lanxang.posture.store import PostureStore
            nas_run(settings, PostureStore(), utcnow())
        except Exception as error:                      # NAS trouble never fails the LAN scan
            console.print(f"[yellow]NAS check failed: {error}[/yellow]")

    if settings.router.enabled:
        from lanxang.devices import router
        try:
            store.record_run("router", router.sightings(router.fetch(settings.router)))
        except Exception as error:                      # router trouble never fails the LAN scan
            store.record_run("router", [], ok=False, error=str(error))
            console.print(f"[yellow]Router check failed: {error}[/yellow]")

    if settings.homeassistant.enabled:
        try:
            from lanxang.monitoring.homeassistant import run as ha_run
            from lanxang.posture.store import PostureStore
            ha_run(settings, PostureStore(), utcnow())
        except Exception as error:                      # Home Assistant trouble never fails the LAN scan
            console.print(f"[yellow]Home Assistant check failed: {error}[/yellow]")

    try:                                                # Sunday evening: how the week went
        from lanxang.monitoring.summary import run as summary_run
        from lanxang.posture.store import PostureStore
        if summary_run(settings, PostureStore(), utcnow()):
            console.print("Weekly summary sent.")
    except Exception as error:
        console.print(f"[yellow]Weekly summary failed: {error}[/yellow]")

    try:                                                # notify.daily_summary: what changed in the last 24 hours
        from lanxang.monitoring.summary import run_daily
        from lanxang.posture.store import PostureStore
        if run_daily(settings, PostureStore(), utcnow()):
            console.print("Daily summary sent.")
    except Exception as error:
        console.print(f"[yellow]Daily summary failed: {error}[/yellow]")

    if result["new"] or result["offline"] or result["notify_errors"]:
        application.runtime.events.publish(
            AtlasEvent(event_type="atlas.devices.scan.completed", source="LanScan", payload=result)
        )

    if json_output:
        print(json.dumps(result, indent=2))
        return

    console.print(f"Scanned {', '.join(subnets)}: {result['seen']} devices, "
                  f"{len(result['new'])} new, {result['linked']} linked"
                  + (" (baseline - no alerts on the first scan)" if result["baseline"] else ""))

    for name in result["offline"]:
        console.print(f"[red]Offline:[/red] {name}")

    for error in result["notify_errors"]:
        console.print(f"[yellow]Signal alert not sent:[/yellow] {error}")


@app.command()
def devices(
    json_output: bool = typer.Option(False, "--json", help="Print the inventory as JSON")
):
    """The device inventory: every device Lanxang knows, its status and where it was seen."""

    from lanxang.devices.store import InventoryStore

    inventory = InventoryStore().devices()

    if json_output:
        print(json.dumps(inventory, indent=2))
        return

    colors = {"seen": "green", "quiet": "yellow", "invisible": "dim"}

    for device in inventory:
        sources = ",".join(sorted({sighting["source"] for sighting in device["sightings"]}))
        console.print(f"[{colors.get(device['status'], 'white')}]{device['status']:<9}[/] "
                      f"{device['name']:<24} {device['ip'] or '-':<16} {device['state']:<7} {sources}")


@app.command()
def trends(
    limit: int = 20,
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Show resource-usage trends from saved lanxang monitor snapshots.
    """

    if not json_output:

        console.print(
            "[bold blue]Lanxang Trends[/bold blue]\n"
        )

    payload = build_trends_payload(limit)

    if not payload["host"] and not payload["containers"] and not payload["guests"]:

        if json_output:
            print(json.dumps(payload, indent=2))

        else:

            console.print(
                "[yellow]No monitoring history found.[/yellow]"
            )

            console.print(
                "Run: lanxang monitor and/or lanxang proxmox scan "
                "(a few times, to build history)"
            )

        return

    if json_output:
        print(json.dumps(payload, indent=2))
        return

    console.print(
        "[bold]Host:[/bold]"
    )

    _print_trend_summaries(payload["host"])

    for container_name, container_payload in payload["containers"].items():

        console.print(
            f"\n[bold]{container_name}:[/bold]"
        )

        _print_trend_summaries(container_payload)

    for vmid, guest_payload in payload["guests"].items():

        console.print(
            f"\n[bold]{guest_payload['name']} ({vmid}):[/bold]"
        )

        _print_trend_summaries(
            {k: v for k, v in guest_payload.items() if k != "name"}
        )



posture_app = typer.Typer(
    name="posture",
    help="Egress/posture collector"
)

@posture_app.command("watch")
def posture_watch(
    once: bool = typer.Option(False, "--once", help="Collect a single sample and exit"),
    json_output: bool = typer.Option(False, "--json", help="Print each sample's result as JSON")
):
    """
    Poll the connection table, routes, tunnel, VPN and CrowdSec every
    posture.interval seconds for the posture page. Runs in the atlas-scan
    container; needs NET_ADMIN for conntrack (read-only listing).
    """

    import time
    from datetime import datetime

    from lanxang.docker.manager import get_client
    from lanxang.posture.collect import Collector
    from lanxang.posture.store import PostureStore

    settings = load_config()

    if not settings.posture.enabled:
        console.print(f"Posture collection is off (posture.enabled: false in {config_name()}).")
        if once:
            return
        # Idle instead of exiting: atlas-scan restarts this command in a loop, and exiting
        # would print the line above every 30 s forever on default installs.
        while True:
            time.sleep(3600)

    client = get_client()

    if client is None:
        console.print("[red]Docker is unavailable - posture needs the Docker socket.[/red]")
        raise typer.Exit(1)

    collector = Collector(settings.posture, PostureStore(), client)
    last_error = None

    while True:
        try:
            result = collector.run_once(utcnow())
        except Exception as error:
            message = str(error)[:300]
            if message != last_error:   # log once per state change, not every poll
                console.print(f"[red]posture watch: {message}[/red]")
            last_error = message
            if once:
                return
            time.sleep(settings.posture.interval)
            continue
        last_error = None
        if json_output:
            print(json.dumps(result, default=str))
        elif result["new"]:
            for item in result["new"]:
                console.print(f"new destination: {item['source']} -> {item['asn_key']} {item['org']} {item['cc']}")
        if once:
            return
        time.sleep(settings.posture.interval)



app.add_typer(
    posture_app
)

@app.command("sample")
def sample():
    """
    Record one host sample (CPU load %, RAM %, root disk %, hottest sensor,
    configured storage_paths usage, container counts) as an atlas.host.sample
    event for the Trends charts. atlas-scan runs it every cycle.
    """

    import psutil

    from lanxang.discovery.host_health import get_host_health
    from lanxang.docker.manager import get_client

    settings = load_config()
    health = get_host_health(settings.health.status_urls)
    payload = {
        "cpu": round(min(100.0, health["load_average"][0] / max(1, health["cpu_count"]) * 100), 1),
        "mem": health["memory_percent"], "disk": health["root_disk_percent"],
        "temp": max(health["max_temperature_c_by_sensor"].values(), default=None),
        "storage": {},
    }

    for label, path in settings.health.storage_paths.items():
        try:
            payload["storage"][label] = psutil.disk_usage(path).percent
        except OSError:
            pass

    from datetime import datetime

    from lanxang.health.alerts import container_state, run as health_run
    from lanxang.posture.store import PostureStore

    containers = []
    client = get_client()
    if client is not None:
        for c in client.containers.list(all=True):
            state = c.attrs.get("State", {})
            labels = c.attrs.get("Config", {}).get("Labels") or {}
            containers.append({"name": c.name, "status": state.get("Status", c.status),
                               "health": (state.get("Health") or {}).get("Status", ""),
                               "exit_code": state.get("ExitCode"),
                               "on_demand": str(labels.get("lanxang.on-demand", labels.get("atlas.on-demand", ""))).lower() in ("1", "true", "yes")})
        states = [container_state(c) for c in containers]
        payload["containers"] = {
            "total": len(containers),
            "running": sum(c["status"] == "running" for c in containers),
            "asleep": states.count("asleep"),
            "unhealthy": sum(c["health"] == "unhealthy" for c in containers),
        }

    application.runtime.events.publish(AtlasEvent(event_type="atlas.host.sample", source="HostSample", payload=payload))
    console.print(json.dumps(payload))

    # host health alerts: temperatures near their limit, memory/disks nearly full, crashed containers
    health["disks"] = {"root disk": payload["disk"], **payload["storage"]}
    for issue in health_run(settings, PostureStore(), health, containers if client is not None else [],
                            utcnow()):
        console.print(f"[yellow]! {issue['reason']}: {issue['detail']}[/yellow]")


access_app = typer.Typer(
    name="access",
    help="Who reaches the public services and from where (web /access)."
)


@access_app.command("collect")
def access_collect(
    json_output: bool = typer.Option(False, "--json", help="Print the pass result as JSON")
):
    """
    Read new Traefik access-log lines and app sign-ins, geolocate new IPs
    locally (DB-IP City Lite + the posture ASN table). atlas-scan runs this
    every scan cycle; first run starts at the end of the log.
    """

    from datetime import datetime

    from lanxang.access.collect import AccessCollector
    from lanxang.access.store import AccessStore

    settings = load_config()

    if not settings.access.enabled:
        console.print(f"[yellow]access.enabled is false in {config_name()} — nothing to do.[/yellow]")
        return

    from lanxang.docker.manager import get_client

    result = AccessCollector(settings.access, settings.posture, AccessStore(),
                             notify=settings.notify, docker=get_client()).run(utcnow())

    if json_output:
        print(json.dumps(result, default=str))
    else:
        console.print(", ".join(f"{k}={v}" for k, v in result.items()))


app.add_typer(
    access_app
)


wiring_app = typer.Typer(
    name="wiring",
    help="Port-level wired map: switches, patch panels, cables (web /cabling)."
)


@wiring_app.command("scan")
def wiring_scan(
    json_output: bool = typer.Option(False, "--json", help="Print the scan result as JSON")
):
    """
    One read-only pass over the configured switches (SNMPv3) and, if enabled,
    the UniFi console; saves a snapshot for /cabling. On demand, like every
    atlas command - the web Refresh button runs the same thing.
    """

    from lanxang.devices.store import InventoryStore
    from lanxang.wiring.scan import WiringBusy, run_scan
    from lanxang.wiring.store import WiringStore, diff_snapshots

    settings = load_config()

    if not settings.wiring.enabled:
        console.print(f"[yellow]wiring.enabled is false in {config_name()} — nothing to do.[/yellow]")
        return

    store = WiringStore()
    previous = store.latest(1)

    try:
        result = run_scan(settings, store, InventoryStore().devices())
    except WiringBusy:
        console.print("[yellow]A wiring scan is already running.[/yellow]")
        raise typer.Exit(code=1)

    changes = diff_snapshots(previous[0]["snapshot"] if previous else None, result["snapshot"])
    failed = any(not source["ok"] for source in result["sources"].values())

    if json_output:
        print(json.dumps({**result, "changes": changes}, default=str))
    else:
        for name, source in result["sources"].items():
            mark = "[green]✓" if source["ok"] else ("[yellow]! stale" if source["stale"] else "[red]✗")
            console.print(f"{mark} {name}[/] {source['error'] or source['note']}")
        snapshot = result["snapshot"]
        for warning in snapshot["warnings"]:
            console.print(f"[yellow]! {warning}[/yellow]")
        console.print(f"{len(snapshot['links'])} links, {len(snapshot['warnings'])} warnings, "
                      f"{len(changes)} changes since last scan")

    if failed:
        raise typer.Exit(code=1)


app.add_typer(
    wiring_app
)


ports_app = typer.Typer(
    name="ports",
    help="Open-port watch: new open ports on LAN devices, this host and the router (alerts)."
)


@ports_app.command("check")
def ports_check(
    json_output: bool = typer.Option(False, "--json", help="Print the saved state as JSON")
):
    """
    TCP-connects to ~25 common service ports on every device online now, reads
    this host's listening sockets and the router's port forwards / UPnP. The
    first run learns; later runs alert once per newly open port. atlas-scan
    runs it every pass.
    """

    from datetime import datetime

    from lanxang.devices.ports import run
    from lanxang.devices.store import InventoryStore
    from lanxang.posture.store import PostureStore

    settings = load_config()

    if not settings.security.port_watch:
        console.print(f"[yellow]security.port_watch is false in {config_name()} — nothing to do.[/yellow]")
        return

    texts, state = run(settings, PostureStore(), InventoryStore().devices(), utcnow())

    if json_output:
        print(json.dumps(state, default=str))
        return

    for device in sorted(state["devices"].values(), key=lambda d: d["name"].lower()):
        if device["open"]:
            console.print(f"{device['name']} ({device['ip']}): {', '.join(map(str, device['open']))}")
    listeners = (state.get("listeners") or {}).get("open")
    if listeners is not None:
        console.print(f"This host listens on: {', '.join(map(str, listeners)) or 'nothing'}")
    forwards = (state.get("forwards") or {}).get("open")
    console.print("Router: " + ("unknown (no UniFi console and no UPnP answer)" if forwards is None else
                                f"{len(forwards)} port forward(s), UPnP {'on' if state.get('upnp') else 'off'}"))
    console.print(f"[green]{state['probed']} devices checked, {len(texts)} new[/green]")
    for text in texts:
        console.print(f"[yellow]! {text.splitlines()[0].strip('*')}[/yellow]")


app.add_typer(
    ports_app
)


certs_app = typer.Typer(
    name="certs",
    help="Certificate expiry of your public hostnames"
)


@certs_app.command("check")
def certs_check(
    json_output: bool = typer.Option(False, "--json", help="Print the saved state as JSON"),
    force: bool = typer.Option(False, "--force", help="Check now even if checked in the last 24 hours")
):
    """
    Opens a TLS connection to every hostname in the Traefik routes (plus
    security.cert_hosts) and reads each certificate's expiry date. Alerts at
    14 and 3 days left, on an untrusted certificate, and when it's renewed.
    atlas-scan runs it every pass; it only checks once a day.
    """

    from datetime import datetime

    from lanxang.posture.certs import run
    from lanxang.posture.store import PostureStore

    settings = load_config()

    if not settings.security.cert_watch:
        console.print(f"[yellow]security.cert_watch is false in {config_name()} — nothing to do.[/yellow]")
        return

    texts, detail = run(settings, PostureStore(), utcnow(), force=force)

    if json_output:
        print(json.dumps(detail, default=str))
        return

    hosts = detail.get("hosts") or {}
    if not hosts:
        console.print("No hostnames to check yet (no Traefik routes seen, security.cert_hosts empty).")
    for host, entry in sorted(hosts.items()):
        colour = {"ok": "green", "unreachable": "dim"}.get(entry["level"], "yellow")
        days = "" if entry["days"] is None else f"{entry['days']} days"
        console.print(f"[{colour}]{host}: {entry['level']} {days} {entry['error']}[/{colour}]".replace("  ", " "))
    console.print(f"[green]Checked {detail.get('checked_at', 'never')}, {len(texts)} alert(s)[/green]")


app.add_typer(
    certs_app
)


internet_app = typer.Typer(
    name="internet",
    help="What Shodan sees on your public IP: open ports and reported CVEs (opt-in)"
)


@internet_app.command("check")
def internet_check(
    json_output: bool = typer.Option(False, "--json", help="Print the saved state as JSON"),
    force: bool = typer.Option(False, "--force", help="Look up now even if checked in the last 24 hours")
):
    """
    Asks Shodan's free InternetDB what it last saw on your home's public IP
    (the one posture watch reads). Alerts on an open port that isn't in
    posture.expected_ports and on reported CVEs. Sends the IP to Shodan, so
    it is off unless posture.internet_view is true. atlas-scan runs it every
    pass; it only looks up once a day, or when the IP changes.
    """

    from lanxang.posture.internet_view import run
    from lanxang.posture.store import PostureStore

    settings = load_config()
    texts, detail = run(settings, PostureStore(), utcnow(), force=force)      # when off: only tidies up

    if not settings.posture.internet_view:
        console.print(f"Internet view is off (posture.internet_view: false in {config_name()}).")
        return

    if json_output:
        print(json.dumps(detail, default=str))
        return

    if not detail:
        console.print("No public IP yet — posture watch reads it (posture.enabled).")
        return
    if not detail["ok"]:
        console.print(f"[yellow]Shodan lookup failed: {detail['error']}[/yellow]")
    if detail["known"] is False:
        console.print(f"Nothing known about {detail['ip']}.")
    for port in detail["ports"]:
        colour = "green" if port["expected"] else "yellow"
        console.print(f"[{colour}]{port['port']}: {'expected' if port['expected'] else 'not expected'}[/{colour}]")
    for cve in detail["vulns"]:
        console.print(f"[yellow]{cve}[/yellow]")
    console.print(f"[green]{detail['ip']} checked {detail['checked_at']}, {len(texts)} alert(s)[/green]")


app.add_typer(
    internet_app
)


uptime_app = typer.Typer(
    name="uptime",
    help="Uptime checks: is each listed service answering? (web Servers > Uptime)"
)


@uptime_app.command("check")
def uptime_check(json_output: bool = typer.Option(False, "--json", help="Print the results as JSON")):
    """
    One pass over uptime.checks (and the checks added on the web page). atlas-scan runs it once a minute;
    a check is down after uptime.fail_after failures in a row, and alerts once then and once when it's back.
    """

    from datetime import datetime

    from lanxang.monitoring import internet
    from lanxang.monitoring.uptime import UptimeStore, run

    settings, store, now = load_config(), UptimeStore(), utcnow()
    results = run(settings, store, now)
    try:
        results = {**internet.run(settings, store, now), **results}
    except Exception as error:                         # the internet check never stops the uptime checks
        console.print(f"[yellow]Internet check failed: {error}[/yellow]")
    if settings.uptime.heartbeats:
        try:
            from lanxang.monitoring.heartbeat import run as heartbeat_run
            from lanxang.posture.store import PostureStore
            for name, beat in heartbeat_run(settings, PostureStore(), now).items():
                if not json_output:
                    console.print(f"heartbeat {name}: {beat['state']}" + (f" (last ping {beat['at']})" if beat["at"] else ""))
        except Exception as error:
            console.print(f"[yellow]Heartbeat check failed: {error}[/yellow]")

    if json_output:
        print(json.dumps({name: {"ok": ok, "ms": ms, "detail": detail} for name, (ok, ms, detail) in results.items()}))
        return
    if not settings.uptime.checks:
        console.print("No uptime checks yet - add them on the web page (Servers > Uptime) or under uptime.checks.")
    for name, (ok, ms, detail) in results.items():
        timing = f" {ms:.0f} ms" if ms is not None else ""
        console.print(f"[{'green' if ok else 'red'}]{name}: {'up' if ok else 'failed'}{timing} ({detail})[/]")


app.add_typer(
    uptime_app
)


ups_app = typer.Typer(name="ups", help="UPS watch over NUT (Network UPS Tools): power cuts and low battery")


@ups_app.command("check")
def ups_check(json_output: bool = typer.Option(False, "--json", help="Print the result as JSON")):
    """
    Reads the NUT server in ups: (host, port 3493) and alerts once on a power cut, once when the battery runs
    low, and once when power is back. atlas-scan runs it once a minute; it does nothing until ups.enabled.
    """

    from datetime import datetime

    from lanxang.monitoring.ups import STATES, run
    from lanxang.posture.store import PostureStore

    settings = load_config()
    if not settings.ups.enabled:
        console.print(f"UPS watch is off — turn it on in Setup (UPS) or under ups: in {config_name()}.")
        return
    detail = run(settings, PostureStore(), utcnow())
    if json_output:
        print(json.dumps(detail))
        return
    if detail["error"]:
        console.print(f"[red]Can't read the UPS server: {detail['error']}[/red]")
    for name, info in detail["upses"].items():
        console.print(f"{name}: {STATES.get(info['state'], info['state'])}, "
                      f"battery {info['charge'] if info['charge'] is not None else '?'}%")


app.add_typer(ups_app)


lan_app = typer.Typer(
    name="lan",
    help="LAN watch: rogue DHCP servers and gateway ARP spoofing (web /posture)."
)


@lan_app.command("check")
def lan_check(
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON"),
    trust_gateway: bool = typer.Option(False, "--trust-gateway",
                                       help="Accept the gateway's current MAC (after replacing the router)")
):
    """
    One DHCP discover (no address is taken) plus a look at the ARP table for
    the gateway's MAC. Alerts once per new problem. Needs host networking -
    atlas-scan runs it every pass.
    """

    from datetime import datetime

    from lanxang.devices.lanwatch import run
    from lanxang.posture.store import PostureStore
    from lanxang.wiring.store import WiringStore

    settings = load_config()
    clients = []

    if settings.wiring.enabled:
        latest = WiringStore().latest(1)
        clients = ((latest[0]["raw"].get("unifi") or {}).get("clients") or []) if latest else []

    result = run(settings, PostureStore(), utcnow(), unifi_clients=clients, trust_gateway=trust_gateway)

    if json_output:
        print(json.dumps(result, default=str))
    else:
        if result["probe_error"]:
            console.print(f"[yellow]! DHCP probe failed: {result['probe_error']}[/yellow]")
        elif result["offers"] is not None:
            for offer in result["offers"]:
                console.print(f"DHCP server {offer['server']} offered {offer['offered']} (gateway {offer['router']})")
        console.print(f"Gateway {result['gateway_ip']} at {result['gateway_seen'] or 'unknown MAC'}")
        for issue in result["issues"]:
            color = "red" if issue["level"] == "bad" else "yellow"
            console.print(f"[{color}]! {issue['reason']}: {issue['detail']}[/{color}]")
        if not result["issues"]:
            console.print("[green]✓ No rogue DHCP server, gateway MAC unchanged[/green]")

    if any(issue["level"] == "bad" for issue in result["issues"]):
        raise typer.Exit(code=1)


app.add_typer(
    lan_app
)


vpn_app = typer.Typer(
    name="vpn",
    help="Check that the torrent clients behind gluetun are connected."
)


@vpn_app.command("check")
def vpn_check():
    """
    Probe each vpn.clients qBittorrent; alert (every notify: channel) after two
    bad checks in a row, and again when it recovers. atlas-scan runs it every cycle.
    """

    from lanxang.access.store import AccessStore
    from lanxang import notify
    from lanxang.monitoring.vpn import check

    settings = load_config()

    if not settings.vpn.clients:
        console.print(f"[yellow]vpn.clients is empty in {config_name()} — nothing to do.[/yellow]")
        return

    send = (lambda text: notify.send(settings.notify, text)) if notify.configured(settings.notify) else None

    for name, problem in check(settings.vpn.clients, AccessStore(), send).items():
        console.print(f"{name}: {problem or 'ok'}")


app.add_typer(
    vpn_app
)


notify_app = typer.Typer(
    name="notify",
    help="Alert channels (notify: in the config file)."
)


@notify_app.command("test")
def notify_test():
    """
    Send a test alert to every channel set under notify: and show which
    ones got it. Exits 1 if any channel failed or none is set.
    """

    from lanxang import notify

    settings = load_config()
    results = notify.send_each(settings.notify, notify.test_text(settings.display))

    if not results:
        console.print(f"[yellow]No alert channels set — add one under notify: in {config_name()} "
                      "(signal, ntfy, webhooks, email or apprise).[/yellow]")
        raise typer.Exit(1)

    for name, ok, error in results:
        console.print(f"[green]✓ {name}[/green]" if ok else f"[red]✗ {name}:[/red] {error}")

    if not all(ok for _, ok, _ in results):
        raise typer.Exit(1)


app.add_typer(
    notify_app
)


dns_app = typer.Typer(name="dns", help="Pi-hole or AdGuard Home: ad blocking on, queries, blocked, busiest devices")


@dns_app.command("check")
def dns_check(json_output: bool = typer.Option(False, "--json", help="Print the result as JSON")):
    """
    Reads Pi-hole (v6) or AdGuard Home from dns_filter: (Setup -> Pi-hole or AdGuard Home). `lanxang scan` runs it
    too; ad blocking off at two checks in a row sends one alert, and another when it's back on.
    """

    from datetime import datetime

    from lanxang.monitoring.dnsfilter import run
    from lanxang.posture.store import PostureStore

    settings = load_config()
    if not settings.dns_filter.enabled:
        console.print(f"Pi-hole / AdGuard Home watch is off — turn it on in Setup or under dns_filter: in {config_name()}.")
        return
    detail = run(settings, PostureStore(), utcnow())
    if json_output:
        print(json.dumps(detail))
        return
    if detail["error"]:
        console.print(f"[red]{detail['error']}[/red]")
    info = detail["info"]
    if info:
        console.print(f"{info['kind']}: ad blocking {'on' if info['blocking'] else 'OFF'}, "
                      f"{info.get('queries')} queries, {info.get('blocked')} blocked ({info.get('percent')}%)")


app.add_typer(dns_app)


nas_app = typer.Typer(name="nas", help="TrueNAS or Synology: pool health, disk health and temperatures")


@nas_app.command("check")
def nas_check(json_output: bool = typer.Option(False, "--json", help="Print the result as JSON")):
    """
    Reads TrueNAS or Synology from nas: (Setup -> TrueNAS or Synology). `lanxang scan` runs it too; a pool that
    isn't healthy, or a disk that fails, runs hot or wears out, sends one alert, and another when it's fine.
    """

    from datetime import datetime

    from lanxang.monitoring.nas import run
    from lanxang.posture.store import PostureStore

    settings = load_config()
    if not settings.nas.enabled:
        console.print(f"NAS watch is off — turn it on in Setup or under nas: in {config_name()}.")
        return
    detail = run(settings, PostureStore(), utcnow())
    if json_output:
        print(json.dumps(detail))
        return
    if detail["error"]:
        console.print(f"[red]{detail['error']}[/red]")
    for pool in detail["info"].get("pools") or []:
        console.print(f"{detail['name']} {pool['name']}: {pool['health']}")
    for disk in detail["info"].get("disks") or []:
        temp = f", {disk['temp']}°C" if disk.get("temp") is not None else ""
        console.print(f"  {disk['dev']} {disk.get('model', '')}: {disk['health']}{temp}")


app.add_typer(nas_app)


ha_app = typer.Typer(name="ha", help="Home Assistant: is it up, offline smart devices, low batteries, updates")


@ha_app.command("check")
def ha_check(json_output: bool = typer.Option(False, "--json", help="Print the result as JSON")):
    """
    Reads Home Assistant from homeassistant: (Setup -> Home Assistant). `lanxang scan` runs it too; HA not
    answering, a device dropping out or a low battery sends one alert, and another when it's fine.
    """

    from lanxang.monitoring.homeassistant import run
    from lanxang.posture.store import PostureStore

    settings = load_config()
    if not settings.homeassistant.enabled:
        console.print(f"Home Assistant watch is off — turn it on in Setup or under homeassistant: in {config_name()}.")
        return
    detail = run(settings, PostureStore(), utcnow())
    if json_output:
        print(json.dumps(detail))
        return
    if detail["error"]:
        console.print(f"[red]{detail['error']}[/red]")
    info = detail["info"] or {}
    console.print(f"Home Assistant {info.get('version') or '?'}: {len(info.get('offline') or [])} devices offline, "
                  f"{len(info.get('batteries') or [])} low batteries, {len(info.get('updates') or [])} updates waiting")
    for device in info.get("offline") or []:
        console.print(f"  offline {device['hours']} h: {device['name']} ({', '.join(device['kinds'])})")
    for battery in info.get("batteries") or []:
        console.print(f"  battery: {battery['name']} {battery['level'] if battery['level'] is not None else 'low'}")


app.add_typer(ha_app)
