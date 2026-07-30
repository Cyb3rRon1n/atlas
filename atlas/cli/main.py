import json

import typer
from atlas.actions import ACTIONS, execute_action
from atlas.discovery import run_discovery
from atlas.inventory import save_inventory
from atlas.inventory import load_inventory
from atlas.reporting.generator import generate_report
from atlas.config import load_config, write_config, write_setup_log
from atlas.config.loader import CONFIG_FILE
from atlas.config.models import AtlasConfig, IntelligenceConfig, MonitoringConfig, ProxmoxConfig
from atlas.health import run_checks
from atlas.docker import collect_containers, get_container_info, resize_container, restart_container, stop_container
from atlas.services import detect_services
from atlas.compose import parse_compose_file
from atlas.proxmox import (
    connect,
    discover_nodes,
    discover_resources,
    diff_virtualization,
    format_change,
    get_guest_info,
    resize_guest,
    restart_guest,
    stop_guest,
)
from atlas.plugins import PluginManager
from atlas.monitoring import collect_container_metrics, collect_metrics, evaluate_thresholds
from atlas.monitoring.changes import diff_monitoring, format_change as format_monitoring_change
from atlas.monitoring.trends import (
    container_metric_trend,
    host_metric_trend,
    known_container_names,
)
from rich.console import Console
from atlas.events import AtlasEvent
from atlas.knowledge.queries import KnowledgeQueries
from atlas.knowledge.store import KnowledgeStore
from atlas.core.application import application
from atlas.intelligence.context import AtlasEnvironmentContext
from atlas.intelligence.agent import AtlasAgent
from atlas.intelligence.analyzer import AtlasAnalyzer
from atlas.intelligence.providers import AIProviderError, get_provider
from atlas.intelligence.tools import build_tools

from atlas import __version__


app = typer.Typer(
    name="atlas",
    help="AI-powered operations platform for self-hosted infrastructure."
)

console = Console()

PLAN_STEP_EVENT_TYPES = {
    "restart_container": "atlas.action.container_restarted",
    "stop_container": "atlas.action.container_stopped",
    "resize_container": "atlas.action.container_resized",
    "restart_guest": "atlas.action.guest_restarted",
    "stop_guest": "atlas.action.guest_stopped",
    "resize_guest": "atlas.action.guest_resized",
}

proxmox_app = typer.Typer(
    name="proxmox",
    help="Manage Proxmox infrastructure."
)

@proxmox_app.command()
def scan():
    """
    Scan Proxmox infrastructure.
    """

    console.print(
        "[bold blue]Atlas Proxmox Scan[/bold blue]\n"
    )

    settings = load_config()

    proxmox_settings = settings.proxmox


    if not proxmox_settings.enabled:

        console.print(
            "[yellow]Proxmox integration disabled.[/yellow]"
        )

        console.print(
            "Enable it in atlas.yaml"
        )

        return


    previous = KnowledgeQueries().latest_environment()


    client = connect(
        proxmox_settings.host,
        proxmox_settings.user,
        password=proxmox_settings.password,
        token_name=proxmox_settings.token_name,
        token_value=proxmox_settings.token_value,
        verify_ssl=proxmox_settings.verify_ssl
    )


    if not client:

        console.print(
            "[red]Unable to connect to Proxmox.[/red]"
        )

        return


    nodes = discover_nodes(client)
    guests = discover_resources(client)


    console.print(
        "[green]✓ Proxmox discovery complete[/green]\n"
    )


    for node in nodes:

        console.print(
            f"""
Node:
{node['name']}

Status:
{node['status']}
"""
        )


    for guest in guests:

        console.print(
            f"""
Guest:
{guest['name']} ({guest['type']}, id {guest['vmid']})

Node:
{guest['node']}

Status:
{guest['status']}

CPU / Memory:
{guest['cpu']} / {guest['mem']}
"""
        )

    data = {
        "nodes": nodes,
        "guests": guests
    }

    previous_virtualization = (
        previous.get("virtualization") if previous else None
    )

    changes = diff_virtualization(previous_virtualization, data)

    runtime = application.runtime

    if previous_virtualization:

        console.print()

        if changes:

            console.print("[bold]Changes since last scan:[/bold]\n")

            for change in changes:

                console.print(format_change(change))

            console.print()

            runtime.events.publish(
                AtlasEvent(
                    event_type="atlas.proxmox.changes_detected",
                    source="ProxmoxScan",
                    payload={"changes": changes}
                )
            )

        else:

            console.print("No changes since last scan.\n")

    runtime.environment.update(
        "virtualization",
        data
    )

    store = KnowledgeStore()

    store.save_environment(
        runtime.environment
    )

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.proxmox.scan.completed",
            source="ProxmoxScan",
            payload=data
        )
    )


@proxmox_app.command(name="restart")
def restart_guest_command(vmid: int):
    """
    Restart a Proxmox VM or LXC guest (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Proxmox Restart[/bold blue]\n"
    )

    settings = load_config()

    proxmox_settings = settings.proxmox

    if not proxmox_settings.enabled:

        console.print(
            "[yellow]Proxmox integration disabled.[/yellow]"
        )

        console.print(
            "Enable it in atlas.yaml"
        )

        return

    client = connect(
        proxmox_settings.host,
        proxmox_settings.user,
        password=proxmox_settings.password,
        token_name=proxmox_settings.token_name,
        token_value=proxmox_settings.token_value,
        verify_ssl=proxmox_settings.verify_ssl
    )

    if not client:

        console.print(
            "[red]Unable to connect to Proxmox.[/red]"
        )

        return

    info = get_guest_info(client, vmid)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    console.print(f"Guest: {info['name']} ({info['type']}, id {vmid})")
    console.print(f"Node: {info['node']}")
    console.print(f"Current status: {info['status']}\n")

    console.print(
        "This will restart the guest. Any unsaved in-guest state is "
        "lost; the guest's own disks are unaffected.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = restart_guest(
        client,
        info["node"],
        vmid,
        info["type"]
    )

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.guest_restarted",
            source="ProxmoxRestartAction",
            payload={
                "vmid": vmid,
                "node": info["node"],
                "result": result
            }
        )
    )

    if not result["success"]:

        console.print(
            f"\n[red]Restart failed: {result['error']}[/red]"
        )

        return

    console.print(
        f"\n[green]✓ Guest '{info['name']}' ({vmid}) restarted[/green]"
    )


@proxmox_app.command(name="stop")
def stop_guest_command(vmid: int):
    """
    Stop a Proxmox VM or LXC guest (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Proxmox Stop[/bold blue]\n"
    )

    settings = load_config()

    proxmox_settings = settings.proxmox

    if not proxmox_settings.enabled:

        console.print(
            "[yellow]Proxmox integration disabled.[/yellow]"
        )

        console.print(
            "Enable it in atlas.yaml"
        )

        return

    client = connect(
        proxmox_settings.host,
        proxmox_settings.user,
        password=proxmox_settings.password,
        token_name=proxmox_settings.token_name,
        token_value=proxmox_settings.token_value,
        verify_ssl=proxmox_settings.verify_ssl
    )

    if not client:

        console.print(
            "[red]Unable to connect to Proxmox.[/red]"
        )

        return

    info = get_guest_info(client, vmid)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    console.print(f"Guest: {info['name']} ({info['type']}, id {vmid})")
    console.print(f"Node: {info['node']}")
    console.print(f"Current status: {info['status']}\n")

    console.print(
        "This will shut down the guest via an ACPI request. If the "
        "guest OS isn't responding, this may not complete - use the "
        "Proxmox UI for a hard stop if needed.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = stop_guest(
        client,
        info["node"],
        vmid,
        info["type"]
    )

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.guest_stopped",
            source="ProxmoxStopAction",
            payload={
                "vmid": vmid,
                "node": info["node"],
                "result": result
            }
        )
    )

    if not result["success"]:

        console.print(
            f"\n[red]Stop failed: {result['error']}[/red]"
        )

        return

    console.print(
        f"\n[green]✓ Guest '{info['name']}' ({vmid}) stopped[/green]"
    )


@proxmox_app.command(name="resize")
def resize_guest_command(
    vmid: int,
    cpus: float = typer.Option(None, help="New CPU limit in cores, e.g. 1.5"),
    memory: str = typer.Option(None, help="New memory limit, e.g. 512m or 1g")
):
    """
    Resize a Proxmox guest's CPU and/or memory limit (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Proxmox Resize[/bold blue]\n"
    )

    if cpus is None and memory is None:

        console.print(
            "[red]Specify --cpus and/or --memory.[/red]"
        )

        return

    settings = load_config()

    proxmox_settings = settings.proxmox

    if not proxmox_settings.enabled:

        console.print(
            "[yellow]Proxmox integration disabled.[/yellow]"
        )

        console.print(
            "Enable it in atlas.yaml"
        )

        return

    client = connect(
        proxmox_settings.host,
        proxmox_settings.user,
        password=proxmox_settings.password,
        token_name=proxmox_settings.token_name,
        token_value=proxmox_settings.token_value,
        verify_ssl=proxmox_settings.verify_ssl
    )

    if not client:

        console.print(
            "[red]Unable to connect to Proxmox.[/red]"
        )

        return

    info = get_guest_info(client, vmid)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    console.print(f"Guest: {info['name']} ({info['type']}, id {vmid})\n")

    if cpus is not None:
        console.print(f"New CPU limit: {cpus} cores")

    if memory is not None:
        console.print(f"New memory limit: {memory}")

    console.print(
        "\nThis changes the guest's cpulimit/memory cap, not how many "
        "CPUs or how much RAM the guest OS sees."
    )

    if info["type"] == "qemu":

        console.print(
            "Note: for a running VM, this may not take effect until "
            "restart unless the guest has hotplug enabled - LXC "
            "guests apply this live."
        )

    console.print()

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = resize_guest(
        client,
        info["node"],
        vmid,
        info["type"],
        cpus=cpus,
        memory=memory
    )

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.guest_resized",
            source="ProxmoxResizeAction",
            payload={
                "vmid": vmid,
                "node": info["node"],
                "cpus": cpus,
                "memory": memory,
                "result": result
            }
        )
    )

    if not result["success"]:

        console.print(
            f"\n[red]Resize failed: {result['error']}[/red]"
        )

        return

    console.print(
        f"\n[green]✓ Guest '{info['name']}' ({vmid}) resized[/green]"
    )


@app.command()
def monitor(
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Query Prometheus for host metrics.
    """

    if not json_output:

        console.print(
            "[bold blue]Atlas Monitoring[/bold blue]\n"
        )

    settings = load_config()

    monitoring_settings = settings.monitoring


    if not monitoring_settings.enabled:

        if json_output:

            print(json.dumps({"enabled": False}, indent=2))

        else:

            console.print(
                "[yellow]Monitoring integration disabled.[/yellow]"
            )

            console.print(
                "Enable it in atlas.yaml"
            )

        return


    previous = KnowledgeQueries().latest_environment()


    data = collect_metrics(
        monitoring_settings.prometheus_url
    )


    if not data["available"]:

        if json_output:

            print(
                json.dumps(
                    {"enabled": True, "available": False},
                    indent=2
                )
            )

        else:

            console.print(
                "[red]Unable to reach Prometheus.[/red]"
            )

        raise typer.Exit(code=1)


    metrics = data["metrics"]

    thresholds = {
        "cpu_percent": monitoring_settings.cpu_threshold,
        "memory_percent": monitoring_settings.memory_threshold,
        "disk_percent": monitoring_settings.disk_threshold,
    }

    exceeded = evaluate_thresholds(metrics, thresholds)

    if not json_output:

        for name, value in metrics.items():

            if value is None:

                console.print(
                    f"{name}: unavailable"
                )

                continue

            if exceeded.get(name):

                console.print(
                    f"[yellow]![/yellow] {name}: {value:.1f}% "
                    f"(threshold: {thresholds[name]:.1f}%)"
                )

            else:

                console.print(
                    f"[green]✓[/green] {name}: {value:.1f}%"
                )


    container_data = collect_container_metrics(
        monitoring_settings.prometheus_url
    )

    containers = container_data["containers"]

    # cpu_percent_of_limit/memory_percent_of_limit are "percent of what
    # this container was actually allocated" - a different question
    # from cpu_percent/memory_percent's "percent of the host". Most
    # containers have no configured limit at all, so those two keys
    # are None a lot more often than the host-relative ones - that's
    # "not applicable", not "unavailable", so they're skipped entirely
    # below rather than printed as unavailable.
    allocation_metric_names = {"cpu_percent_of_limit", "memory_percent_of_limit"}

    container_thresholds = {
        **thresholds,
        "cpu_percent_of_limit": monitoring_settings.cpu_allocation_threshold,
        "memory_percent_of_limit": monitoring_settings.memory_allocation_threshold,
    }

    if not json_output:

        console.print(
            "\n[bold]Containers:[/bold]"
        )

        if not containers:

            console.print(
                "No container metrics available (is cAdvisor being scraped?)"
            )

    containers_payload = {}

    for container_name, values in containers.items():

        container_exceeded = evaluate_thresholds(values, container_thresholds)

        containers_payload[container_name] = {
            "metrics": values,
            "exceeded": container_exceeded
        }

        if json_output:
            continue

        console.print(f"\n{container_name}:")

        for name, value in values.items():

            if value is None:

                if name in allocation_metric_names:
                    continue

                console.print(
                    f"  {name}: unavailable"
                )

                continue

            if container_exceeded.get(name):

                console.print(
                    f"  [yellow]![/yellow] {name}: {value:.1f}% "
                    f"(threshold: {container_thresholds[name]:.1f}%)"
                )

            else:

                console.print(
                    f"  [green]✓[/green] {name}: {value:.1f}%"
                )


    data["containers"] = containers

    previous_monitoring = previous.get("monitoring") if previous else None

    changes = diff_monitoring(previous_monitoring, data, container_thresholds)

    if not json_output and previous_monitoring:

        console.print()

        if changes:

            console.print("[bold]Changes since last scan:[/bold]\n")

            for change in changes:

                console.print(format_monitoring_change(change))

            console.print()

        else:

            console.print("No changes since last scan.\n")


    runtime = application.runtime

    runtime.environment.update(
        "monitoring",
        data
    )

    store = KnowledgeStore()

    store.save_environment(
        runtime.environment
    )

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.monitoring.scan.completed",
            source="MonitoringScan",
            payload=data
        )
    )

    if any(exceeded.values()):

        runtime.events.publish(
            AtlasEvent(
                event_type="atlas.monitoring.threshold_exceeded",
                source="MonitoringScan",
                payload={
                    "metrics": metrics,
                    "thresholds": thresholds,
                    "exceeded": [
                        name for name, over in exceeded.items() if over
                    ]
                }
            )
        )

    if changes:

        runtime.events.publish(
            AtlasEvent(
                event_type="atlas.monitoring.changes_detected",
                source="MonitoringScan",
                payload={"changes": changes}
            )
        )

    healthy = (
        not any(exceeded.values())
        and not any(
            any(container["exceeded"].values())
            for container in containers_payload.values()
        )
    )

    if json_output:

        print(
            json.dumps(
                {
                    "enabled": True,
                    "available": True,
                    "metrics": metrics,
                    "thresholds": thresholds,
                    "exceeded": exceeded,
                    "container_thresholds": container_thresholds,
                    "containers": containers_payload,
                    "changes": changes,
                    "healthy": healthy
                },
                indent=2
            )
        )

    else:

        console.print(
            "\n[green]✓ Monitoring scan complete[/green]"
        )

    if not healthy:
        raise typer.Exit(code=1)


def _trend_summary(points):

    values = [value for _, value in points]

    return {
        "latest": values[-1],
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "samples": len(values)
    }


@app.command()
def trends(
    limit: int = 20,
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Show resource-usage trends from saved atlas monitor snapshots.
    """

    if not json_output:

        console.print(
            "[bold blue]Atlas Trends[/bold blue]\n"
        )

    records = KnowledgeQueries().environment_history(limit)

    if not any(record["data"].get("monitoring") for record in records):

        if json_output:

            print(json.dumps({"host": {}, "containers": {}}, indent=2))

        else:

            console.print(
                "[yellow]No monitoring history found.[/yellow]"
            )

            console.print(
                "Run: atlas monitor (a few times, to build history)"
            )

        return

    host_payload = {}

    if not json_output:

        console.print(
            "[bold]Host:[/bold]"
        )

    for metric_name in ("cpu_percent", "memory_percent", "disk_percent"):

        points = host_metric_trend(records, metric_name)

        if not points:
            continue

        summary = _trend_summary(points)
        host_payload[metric_name] = summary

        if json_output:
            continue

        console.print(
            f"  {metric_name}: latest {summary['latest']:.1f}%, "
            f"min {summary['min']:.1f}%, max {summary['max']:.1f}%, "
            f"avg {summary['avg']:.1f}% ({summary['samples']} samples)"
        )

    containers_payload = {}

    for container_name in known_container_names(records):

        container_payload = {}

        if not json_output:

            console.print(
                f"\n[bold]{container_name}:[/bold]"
            )

        for metric_name in (
            "cpu_percent", "memory_percent",
            "cpu_percent_of_limit", "memory_percent_of_limit"
        ):

            points = container_metric_trend(
                records, container_name, metric_name
            )

            if not points:
                continue

            summary = _trend_summary(points)
            container_payload[metric_name] = summary

            if json_output:
                continue

            console.print(
                f"  {metric_name}: latest {summary['latest']:.1f}%, "
                f"min {summary['min']:.1f}%, max {summary['max']:.1f}%, "
                f"avg {summary['avg']:.1f}% ({summary['samples']} samples)"
            )

        containers_payload[container_name] = container_payload

    if json_output:

        print(
            json.dumps(
                {"host": host_payload, "containers": containers_payload},
                indent=2
            )
        )


@app.command()
def version():
    """
    Display Atlas version.
    """

    console.print(
        f"[bold blue]Atlas[/bold blue] version {__version__}"
    )


@app.command()
def status():
    """
    Display current Atlas status.
    """

    console.print(
        "[bold green]Atlas Status[/bold green]"
    )

    console.print(
        "✓ Atlas CLI operational"
    )

    console.print(
        "✓ Discovery engine not configured"
    )


@app.command()
def doctor(
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Run Atlas health checks.
    """

    results = run_checks()

    healthy = all(check["status"] for check in results)

    if json_output:

        print(
            json.dumps(
                {"checks": results, "healthy": healthy},
                indent=2
            )
        )

    else:

        console.print(
            "[bold cyan]Atlas Doctor[/bold cyan]\n"
        )

        for check in results:

            if check["status"]:
                symbol = "[green]✓[/green]"
            else:
                symbol = "[yellow]![/yellow]"

            console.print(
                f"{symbol} "
                f"{check['name']}: "
                f"{check['details']}"
            )

    if not healthy:
        raise typer.Exit(code=1)


@app.command()
def init():
    """
    Interactively generate atlas.yaml.
    """

    console.print(
        "[bold cyan]Atlas Init[/bold cyan]\n"
    )

    if CONFIG_FILE.exists():

        console.print(
            f"{CONFIG_FILE} already exists.\n"
        )

        if not typer.confirm("Overwrite?"):

            console.print(
                "[yellow]Cancelled.[/yellow]"
            )

            return

    log_lines = ["Atlas init started"]

    name = typer.prompt(
        "Instance name (just a label for this Atlas install)",
        default="atlas-node"
    )

    log_lines.append(f"name: {name}")

    console.print()

    proxmox = ProxmoxConfig()

    console.print(
        "[dim]Proxmox: connects to a Proxmox server you already have "
        "running - Atlas does not install Proxmox itself.[/dim]"
    )

    if typer.confirm("Configure Proxmox integration?"):

        host = typer.prompt(
            "Proxmox host (its IP address or hostname, e.g. 192.168.1.103)"
        )

        user = typer.prompt(
            "Proxmox user (the user the token/password below belongs to)",
            default="atlas@pve"
        )

        if typer.confirm("Use an API token instead of a password?", default=True):

            console.print(
                "[dim]From the Proxmox UI: Datacenter -> Permissions -> "
                "API Tokens.[/dim]"
            )

            token_name = typer.prompt("Token name")

            token_value = typer.prompt(
                "Token value (typed here, visible as you type - this "
                "prompt does not hide input)"
            )

            password = ""
            auth = "token"

        else:

            token_name = ""
            token_value = ""

            password = typer.prompt(
                "Password (visible as you type - this prompt does not "
                "hide input)"
            )

            auth = "password"

        verify_ssl = typer.confirm("Verify TLS certificate?", default=False)

        proxmox = ProxmoxConfig(
            enabled=True,
            host=host,
            user=user,
            token_name=token_name,
            token_value=token_value,
            password=password,
            verify_ssl=verify_ssl
        )

        log_lines.append(
            f"proxmox: enabled, host={host}, user={user}, auth={auth}, "
            f"verify_ssl={verify_ssl}"
        )

    else:

        log_lines.append("proxmox: disabled")

    console.print()

    console.print(
        "[dim]AI provider: Anthropic uses an API key from an Anthropic "
        "account you already have (nothing is installed by this step). "
        "Ollama needs Ollama already installed and running somewhere "
        "Atlas can reach.[/dim]"
    )

    while True:

        provider = typer.prompt(
            "AI provider (anthropic/ollama)",
            default="anthropic"
        )

        if provider in ("anthropic", "ollama"):
            break

        console.print(
            "[yellow]Please enter 'anthropic' or 'ollama'.[/yellow]"
        )

    ollama_host = "http://localhost:11434"

    if provider == "ollama":

        ollama_host = typer.prompt(
            "Ollama host (address of your already-running Ollama server)",
            default=ollama_host
        )

        model = typer.prompt(
            "Model (must already be pulled in Ollama, "
            "e.g. via 'ollama pull llama3.1')",
            default="llama3.1"
        )

    else:

        model = typer.prompt(
            "Model",
            default="claude-opus-5"
        )

        console.print(
            "\n[yellow]Remember to set the ANTHROPIC_API_KEY environment "
            "variable[/yellow] - it is never stored in atlas.yaml."
        )

    intelligence = IntelligenceConfig(
        provider=provider,
        model=model,
        ollama_host=ollama_host
    )

    log_lines.append(
        f"intelligence: provider={provider}, model={model}"
    )

    console.print()

    console.print(
        "[dim]Monitoring: connects to a Prometheus server you already "
        "have running - Atlas does not install Prometheus.[/dim]"
    )

    monitoring = MonitoringConfig()

    if typer.confirm("Configure Prometheus monitoring?"):

        prometheus_url = typer.prompt(
            "Prometheus URL (e.g. http://192.168.1.50:9090)",
            default="http://localhost:9090"
        )

        monitoring = MonitoringConfig(
            enabled=True,
            prometheus_url=prometheus_url
        )

        log_lines.append(
            f"monitoring: enabled, prometheus_url={prometheus_url}"
        )

    else:

        log_lines.append("monitoring: disabled")

    config = AtlasConfig(
        name=name,
        proxmox=proxmox,
        intelligence=intelligence,
        monitoring=monitoring
    )

    console.print(
        "\n[bold]Review[/bold] - check this matches what you meant to "
        "enter, especially if anything looked odd while typing:\n"
    )

    console.print(f"  Name: {config.name}")

    if config.proxmox.enabled:

        if config.proxmox.token_value:
            auth_display = (
                f"API token '{config.proxmox.token_name}' "
                f"({len(config.proxmox.token_value)} characters entered)"
            )
        else:
            auth_display = (
                f"password ({len(config.proxmox.password)} characters entered)"
            )

        console.print(
            f"  Proxmox: enabled, host={config.proxmox.host}, "
            f"user={config.proxmox.user}, auth={auth_display}, "
            f"verify_ssl={config.proxmox.verify_ssl}"
        )

    else:

        console.print("  Proxmox: disabled")

    console.print(
        f"  Intelligence: provider={config.intelligence.provider}, "
        f"model={config.intelligence.model}"
    )

    if config.monitoring.enabled:

        console.print(
            f"  Monitoring: enabled, prometheus_url="
            f"{config.monitoring.prometheus_url}"
        )

    else:

        console.print("  Monitoring: disabled")

    if not typer.confirm("\nSave this configuration?", default=True):

        console.print(
            "[yellow]Cancelled - nothing written.[/yellow]"
        )

        return

    write_config(config)

    log_lines.append(f"{CONFIG_FILE} written")
    log_lines.append("Atlas init completed")

    log_path = write_setup_log(log_lines)

    console.print(
        f"\n[green]✓ {CONFIG_FILE} created[/green]"
    )

    console.print(
        f"[green]✓ Setup log saved to {log_path}[/green]\n"
    )

    console.print(
        "Run: atlas doctor"
    )


@app.command()
def discover():
    """
    Discover infrastructure information.
    """

    console.print(
        "[bold purple]Atlas Discovery[/bold purple]"
    )

    data = run_discovery()

    inventory_file = save_inventory(data)

    runtime = application.runtime

    runtime.environment.ingest_discovery(
        data
    )

    manager = PluginManager()

    manager.load_plugins()

    manager.initialize(runtime)

    plugin_data = manager.discover_all()

    runtime.environment.update(
        "containers",
        plugin_data
    )

    store = KnowledgeStore()

    store.save_environment(
        runtime.environment
    )

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.discovery.completed",
            source="DiscoveryEngine",
            payload=data
        )
    )

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.plugins.discovery.completed",
            source="PluginManager",
            payload=plugin_data
        )
    )

    console.print(
        "\n[green]✓ Discovery complete[/green]"
    )

    console.print(
        f"[cyan]Inventory saved:[/cyan] {inventory_file}"
    )

    console.print(
        f"[cyan]Plugins discovered:[/cyan] {list(plugin_data.keys())}"
    )


@app.command()
def config():
    """
    Display Atlas configuration.
    """

    settings = load_config()

    console.print(
        "[bold cyan]Atlas Configuration[/bold cyan]"
    )

    console.print(
        settings.model_dump()
    )


@app.command()
def report():
    """
    Generate Atlas infrastructure report.
    """

    inventory = load_inventory()

    if not inventory:
        console.print(
            "[yellow]No inventory found.[/yellow]"
        )

        console.print(
            "Run: atlas discover"
        )

        return

    output = generate_report(
        inventory
    )

    console.print(
        "[green]✓ Report generated[/green]"
    )

    console.print(
        f"Saved: {output}"
    )


@app.command()
def docker():
    """
    Display Docker container status.
    """

    console.print(
        "[bold blue]Docker Status[/bold blue]\n"
    )

    data = collect_containers()


    if not data["available"]:

        console.print(
            "[yellow]! Docker unavailable[/yellow]"
        )

        return


    containers = data["containers"]


    if not containers:

        console.print(
            "No containers found."
        )

        return


    for container in containers:

        console.print(
            f"""
[cyan]{container['name']}[/cyan]

Image:
{container['image']}

Status:
{container['status']}

ID:
{container['id']}
"""
        )


@app.command()
def restart(name: str):
    """
    Restart a Docker container (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Restart[/bold blue]\n"
    )

    info = get_container_info(name)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    console.print(f"Container: {info['name']}")
    console.print(f"Image: {info['image']}")
    console.print(f"Current status: {info['status']}\n")

    console.print(
        "This will restart the container. Any unsaved in-container "
        "state is lost; the container's own persistent volumes are "
        "unaffected.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = restart_container(name)

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.container_restarted",
            source="RestartAction",
            payload={
                "container": name,
                "result": result
            }
        )
    )

    if not result["success"]:

        console.print(
            f"\n[red]Restart failed: {result['error']}[/red]"
        )

        return

    console.print(
        f"\n[green]✓ Container '{name}' restarted[/green]"
    )


@app.command()
def stop(name: str):
    """
    Stop a Docker container (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Stop[/bold blue]\n"
    )

    info = get_container_info(name)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    console.print(f"Container: {info['name']}")
    console.print(f"Image: {info['image']}")
    console.print(f"Current status: {info['status']}\n")

    console.print(
        "This will stop the container. It will not be removed - "
        f"restart it anytime with atlas restart {name}.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = stop_container(name)

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.container_stopped",
            source="StopAction",
            payload={
                "container": name,
                "result": result
            }
        )
    )

    if not result["success"]:

        console.print(
            f"\n[red]Stop failed: {result['error']}[/red]"
        )

        return

    console.print(
        f"\n[green]✓ Container '{name}' stopped[/green]"
    )


@app.command()
def resize(
    name: str,
    cpus: float = typer.Option(None, help="New CPU limit in cores, e.g. 1.5"),
    memory: str = typer.Option(None, help="New memory limit, e.g. 512m or 1g")
):
    """
    Resize a Docker container's CPU and/or memory limit (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Resize[/bold blue]\n"
    )

    if cpus is None and memory is None:

        console.print(
            "[red]Specify --cpus and/or --memory.[/red]"
        )

        return

    info = get_container_info(name)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    console.print(f"Container: {info['name']}")

    console.print(
        f"Current CPU limit: "
        f"{info['cpu_limit_cores']:.2f} cores" if info["cpu_limit_cores"] else
        "Current CPU limit: unlimited"
    )

    console.print(
        f"Current memory limit: {info['memory_limit_bytes']} bytes"
        if info["memory_limit_bytes"] else
        "Current memory limit: unlimited"
    )

    console.print()

    if cpus is not None:
        console.print(f"New CPU limit: {cpus} cores")

    if memory is not None:
        console.print(f"New memory limit: {memory}")

    console.print(
        "\nThis changes the container's resource limit live, without a "
        "restart. Lowering memory below what the container is currently "
        "using may fail.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = resize_container(
        name,
        cpus=cpus,
        mem_limit=memory
    )

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.container_resized",
            source="ResizeAction",
            payload={
                "container": name,
                "cpus": cpus,
                "memory": memory,
                "result": result
            }
        )
    )

    if not result["success"]:

        console.print(
            f"\n[red]Resize failed: {result['error']}[/red]"
        )

        return

    console.print(
        f"\n[green]✓ Container '{name}' resized[/green]"
    )


@app.command()
def services():
    """
    Detect known homelab services.
    """

    from atlas.docker import collect_containers


    console.print(
        "[bold blue]Atlas Services[/bold blue]\n"
    )


    docker = collect_containers()


    if not docker["available"]:
        console.print(
            "[yellow]Docker unavailable[/yellow]"
        )
        return


    services = detect_services(
        docker["containers"]
    )


    if not services:
        console.print(
            "No recognized services found."
        )
        return


    for service in services:

        console.print(
            f"""
[cyan]{service['name']}[/cyan]

Category:
{service['category']}

Purpose:
{service['purpose']}

Container:
{service['container']}

Status:
{service['status']}
"""
        )


@app.command()
def compose(path: str = "docker-compose.yml"):
    """
    Analyze a Docker Compose file.
    """

    console.print(
        "[bold blue]Compose Analysis[/bold blue]\n"
    )


    project = parse_compose_file(
        path
    )


    if not project:

        console.print(
            "[yellow]No compose file found[/yellow]"
        )

        return


    console.print(
        f"Project: {project.name}\n"
    )


    for service in project.services:

        console.print(
            f"""
[cyan]{service.name}[/cyan]

Image:
{service.image}

Ports:
{service.ports}

Volumes:
{service.volumes}
"""
        )

@app.command()
def runtime():
    """
    Display Atlas runtime information.
    """

    runtime = application.runtime

    ctx = runtime.get_context()

    console.print("[bold blue]Atlas Runtime[/bold blue]\n")

    console.print(ctx)

@app.command()
def plugins():
    """
    Display registered Atlas plugins.
    """

    runtime = application.runtime

    manager = PluginManager()

    manager.load_plugins()

    manager.initialize(runtime)

    console.print(
        "[bold blue]Atlas Plugins[/bold blue]\n"
    )

    for plugin in manager.get_plugins():
        console.print(
            f"✓ {plugin.name} ({plugin.version})"
        )

@app.command()
def history(
    limit: int = 10
):
    """
    Display Atlas historical events.
    """

    console.print(
        "[bold blue]Atlas History[/bold blue]\n"
    )

    query = KnowledgeQueries()

    events = query.recent_events(
        limit
    )

    if not events:

        console.print(
            "No historical events found."
        )

        return


    for event in events:

        console.print(
            f"""
[cyan]{event.created_at}[/cyan]

Event:
{event.event_type}

Source:
{event.source}

Payload:
{event.payload}

"""
        )

@app.command()
def intelligence():
    """
    Display Atlas intelligence context.
    """

    query = KnowledgeQueries()

    environment = query.latest_environment()

    console.print(
        "[bold blue]Atlas Intelligence[/bold blue]\n"
    )

    if not environment:

        console.print(
            "[yellow]No environment data found.[/yellow]"
        )

        console.print(
            "Run: atlas discover"
        )

        return

    console.print(
        environment
    )


@app.command()
def analyze():
    """
    Analyze the latest environment snapshot with AI and
    produce a summary and recommendations.
    """

    console.print(
        "[bold blue]Atlas Analysis[/bold blue]\n"
    )

    query = KnowledgeQueries()

    environment = query.latest_environment()

    if not environment:

        console.print(
            "[yellow]No environment data found.[/yellow]"
        )

        console.print(
            "Run: atlas discover"
        )

        return

    settings = load_config()

    try:

        provider = get_provider(settings.intelligence)

        analyzer = AtlasAnalyzer(provider)

        tools = build_tools(settings)

        result = analyzer.analyze(environment, tools)

    except AIProviderError as error:

        console.print(
            f"[red]Analysis failed:[/red] {error}"
        )

        return

    console.print(
        f"{result.summary}\n"
    )

    severity_styles = {
        "critical": "bold red",
        "warning": "yellow",
        "info": "cyan"
    }

    if not result.recommendations:

        console.print(
            "[green]No recommendations at this time.[/green]"
        )

    for recommendation in result.recommendations:

        style = severity_styles.get(
            recommendation.severity, "white"
        )

        console.print(
            f"[{style}]● {recommendation.title}[/{style}] "
            f"({recommendation.severity})"
        )

        console.print(
            f"  {recommendation.detail}"
        )

        if recommendation.action:

            definition = ACTIONS.get(
                recommendation.action.type
            )

            if definition:

                console.print(
                    f"\n  [cyan]→ Suggested:[/cyan] "
                    f"{definition.command_template(recommendation.action)}"
                )

        console.print()

    if result.plan:

        console.print(
            f"[bold]Suggested plan:[/bold] {result.plan.summary}\n"
        )

        for index, step in enumerate(result.plan.steps, start=1):

            definition = ACTIONS.get(step.action.type)

            if not definition:
                continue

            console.print(
                f"  {index}. {definition.command_template(step.action)}"
            )

            console.print(
                f"     ({step.rationale})\n"
            )

        console.print(
            "Each step runs one at a time, with its own confirmation.\n"
        )

    if result.plan and typer.confirm("Run this plan now?"):

        for index, step in enumerate(result.plan.steps, start=1):

            definition = ACTIONS.get(step.action.type)

            console.print(
                f"\nStep {index}: {definition.command_template(step.action)}"
            )

            console.print(
                f"  ({step.rationale})"
            )

            if not typer.confirm("Run this step?"):

                console.print(
                    "[yellow]Stopped - remaining steps not run.[/yellow]"
                )

                break

            step_result = execute_action(step.action)

            application.runtime.events.publish(
                AtlasEvent(
                    event_type=PLAN_STEP_EVENT_TYPES[step.action.type],
                    source="PlanStep",
                    payload={
                        "target": step.action.target,
                        "result": step_result
                    }
                )
            )

            if not step_result["success"]:

                console.print(
                    f"[red]Step failed: {step_result['error']}[/red]"
                )

                console.print(
                    "[yellow]Stopped - remaining steps not run.[/yellow]"
                )

                break

            console.print(
                f"[green]✓ Step {index} complete[/green]"
            )

        else:

            console.print(
                "\n[green]✓ Plan complete[/green]"
            )

    store = KnowledgeStore()

    store.save_analysis(
        result,
        provider=settings.intelligence.provider,
        model=settings.intelligence.model
    )

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.analysis.completed",
            source="AtlasAnalyzer",
            payload={
                "provider": settings.intelligence.provider,
                "model": settings.intelligence.model,
                "recommendation_count": len(result.recommendations)
            }
        )
    )


@app.command()
def chat():
    """
    Interactive chat with Atlas about your infrastructure. Atlas can
    look up live container/Proxmox/monitoring state and recent
    history as needed - unlike atlas analyze, no prior atlas discover
    is required. Type 'exit' or 'quit' to end the session.
    """

    console.print(
        "[bold blue]Atlas Chat[/bold blue]\n"
    )

    settings = load_config()

    try:
        provider = get_provider(settings.intelligence)

    except AIProviderError as error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    agent = AtlasAgent(provider, settings)

    console.print(
        "Ask about your infrastructure. Type 'exit' to quit.\n"
    )

    messages = []
    transcript = []

    while True:

        try:
            user_input = typer.prompt("You")

        except (EOFError, KeyboardInterrupt):

            console.print()

            break

        if user_input.strip().lower() in {"exit", "quit"}:
            break

        messages.append({
            "role": "user",
            "content": user_input
        })

        transcript.append({
            "role": "user",
            "content": user_input
        })

        try:
            reply = agent.converse(messages)

        except AIProviderError as error:

            console.print(
                f"\n[red]{error}[/red]\n"
            )

            continue

        transcript.append({
            "role": "assistant",
            "content": reply.text
        })

        console.print(
            f"\n[bold]Atlas:[/bold] {reply.text}\n"
        )

        if reply.action:

            definition = ACTIONS.get(reply.action.type)

            if definition:

                console.print(
                    f"[cyan]→ Suggested:[/cyan] "
                    f"{definition.command_template(reply.action)}\n"
                )

        if reply.plan:

            console.print(
                f"[bold]Suggested plan:[/bold] {reply.plan.summary}\n"
            )

            for index, step in enumerate(reply.plan.steps, start=1):

                definition = ACTIONS.get(step.action.type)

                if not definition:
                    continue

                console.print(
                    f"  {index}. {definition.command_template(step.action)}"
                )

                console.print(
                    f"     ({step.rationale})\n"
                )

            console.print(
                "Each step runs one at a time, with its own confirmation.\n"
            )

            if typer.confirm("Run this plan now?"):

                for index, step in enumerate(reply.plan.steps, start=1):

                    definition = ACTIONS.get(step.action.type)

                    console.print(
                        f"\nStep {index}: "
                        f"{definition.command_template(step.action)}"
                    )

                    console.print(
                        f"  ({step.rationale})"
                    )

                    if not typer.confirm("Run this step?"):

                        console.print(
                            "[yellow]Stopped - remaining steps not "
                            "run.[/yellow]"
                        )

                        break

                    step_result = execute_action(step.action)

                    application.runtime.events.publish(
                        AtlasEvent(
                            event_type=(
                                PLAN_STEP_EVENT_TYPES[step.action.type]
                            ),
                            source="PlanStep",
                            payload={
                                "target": step.action.target,
                                "result": step_result
                            }
                        )
                    )

                    if not step_result["success"]:

                        console.print(
                            f"[red]Step failed: "
                            f"{step_result['error']}[/red]"
                        )

                        console.print(
                            "[yellow]Stopped - remaining steps not "
                            "run.[/yellow]"
                        )

                        break

                    console.print(
                        f"[green]✓ Step {index} complete[/green]"
                    )

                else:

                    console.print(
                        "\n[green]✓ Plan complete[/green]"
                    )

    if transcript:

        runtime = application.runtime

        runtime.events.publish(
            AtlasEvent(
                event_type="atlas.chat.transcript_saved",
                source="AtlasChat",
                payload={"messages": transcript}
            )
        )

    console.print(
        "[green]Chat ended.[/green]"
    )


app.add_typer(
    proxmox_app
)


if __name__ == "__main__":
    app()
