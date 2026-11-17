"""Proxmox, libvirt and fleet (remote node) commands."""

import json

import typer
from atlas.config import load_config
from atlas.libvirt import (
    get_guest_info as get_libvirt_guest_info,
    resize_guest as resize_libvirt_guest,
    restart_guest as restart_libvirt_guest,
    stop_guest as stop_libvirt_guest,
)
from atlas.fleet import run_remote_doctor, run_remote_report, run_remote_trends
from atlas.proxmox import (
    connect,
    discover_node_storage,
    discover_nodes,
    discover_resources,
    diff_virtualization,
    format_change,
    get_guest_info,
    resize_guest,
    restart_guest,
    stop_guest,
)
from atlas.events import AtlasEvent
from atlas.knowledge.queries import KnowledgeQueries
from atlas.knowledge.store import KnowledgeStore
from atlas.core.application import application

from atlas.cli.app import app, console, _resolve_fleet_node, _print_trend_summaries


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

    for node in nodes:
        node.update(discover_node_storage(client, node["name"]))
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


libvirt_app = typer.Typer(
    name="libvirt",
    help="Manage libvirt/KVM guests."
)


@libvirt_app.command(name="restart")
def restart_libvirt_guest_command(
    name: str,
    node: str = typer.Option(
        None, "--node",
        help="Restart on this fleet node's libvirt instead of locally."
    )
):
    """
    Restart a libvirt/KVM guest (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Libvirt Restart[/bold blue]\n"
    )

    fleet_node, error = _resolve_fleet_node(node)

    if error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    info = get_libvirt_guest_info(name, node=fleet_node)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    if fleet_node:
        console.print(f"Node: {fleet_node.name} ({fleet_node.host})")

    console.print(f"Guest: {info['name']}")
    console.print(f"Current state: {info['state']}\n")

    console.print(
        "This sends an ACPI reboot request to the guest. Unlike "
        "Docker's restart, there is no automatic force-fallback - if "
        "the guest OS isn't listening, this can stall rather than "
        "guarantee completion.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = restart_libvirt_guest(name, node=fleet_node)

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.libvirt_guest_restarted",
            source="LibvirtRestartAction",
            payload={
                "guest": name,
                "node": fleet_node.name if fleet_node else None,
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
        f"\n[green]✓ Guest '{name}' restarted[/green]"
    )


@libvirt_app.command(name="stop")
def stop_libvirt_guest_command(
    name: str,
    node: str = typer.Option(
        None, "--node",
        help="Stop on this fleet node's libvirt instead of locally."
    )
):
    """
    Stop a libvirt/KVM guest (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Libvirt Stop[/bold blue]\n"
    )

    fleet_node, error = _resolve_fleet_node(node)

    if error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    info = get_libvirt_guest_info(name, node=fleet_node)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    if fleet_node:
        console.print(f"Node: {fleet_node.name} ({fleet_node.host})")

    console.print(f"Guest: {info['name']}")
    console.print(f"Current state: {info['state']}\n")

    console.print(
        "This sends an ACPI shutdown request to the guest. There is "
        "no automatic force-fallback - if the guest OS isn't "
        "listening, this can stall rather than guarantee completion.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = stop_libvirt_guest(name, node=fleet_node)

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.libvirt_guest_stopped",
            source="LibvirtStopAction",
            payload={
                "guest": name,
                "node": fleet_node.name if fleet_node else None,
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
        f"\n[green]✓ Guest '{name}' stopped[/green]"
    )


@libvirt_app.command(name="resize")
def resize_libvirt_guest_command(
    name: str,
    vcpus: int = typer.Option(None, help="New vCPU count, e.g. 2"),
    memory: str = typer.Option(None, help="New memory size, e.g. 512MiB or 2GiB"),
    node: str = typer.Option(
        None, "--node",
        help="Resize on this fleet node's libvirt instead of locally."
    )
):
    """
    Resize a libvirt/KVM guest's vCPU count and/or memory allocation
    (requires confirmation). Applies at next boot only - a running
    guest needs its own hotplug config to pick this up live, which
    this command does not attempt.
    """

    console.print(
        "[bold blue]Atlas Libvirt Resize[/bold blue]\n"
    )

    if vcpus is None and memory is None:

        console.print(
            "[red]Specify --vcpus and/or --memory.[/red]"
        )

        return

    fleet_node, error = _resolve_fleet_node(node)

    if error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    info = get_libvirt_guest_info(name, node=fleet_node)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    if fleet_node:
        console.print(f"Node: {fleet_node.name} ({fleet_node.host})")

    console.print(f"Guest: {info['name']}\n")

    if vcpus is not None:
        console.print(f"New vCPU count: {vcpus}")

    if memory is not None:
        console.print(f"New memory size: {memory}")

    console.print(
        "\nThis applies at next boot only. A running guest needs "
        "hotplug already configured to pick this up live - not "
        "attempted here, so a restart may be required.\n"
    )

    if not typer.confirm("Proceed?"):

        console.print(
            "[yellow]Cancelled.[/yellow]"
        )

        return

    result = resize_libvirt_guest(name, vcpus=vcpus, memory=memory, node=fleet_node)

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.libvirt_guest_resized",
            source="LibvirtResizeAction",
            payload={
                "guest": name,
                "node": fleet_node.name if fleet_node else None,
                "vcpus": vcpus,
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
        f"\n[green]✓ Guest '{name}' resized[/green]"
    )


fleet_app = typer.Typer(
    name="fleet",
    help="Aggregate views across multiple Atlas nodes."
)


@fleet_app.command(name="doctor")
def fleet_doctor(
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Run atlas doctor on every configured fleet node over SSH and
    aggregate the results.
    """

    settings = load_config()

    nodes = settings.fleet.nodes

    if not nodes:

        if json_output:

            print(
                json.dumps(
                    {"nodes": [], "healthy": True},
                    indent=2
                )
            )

        else:

            console.print(
                "[yellow]No fleet nodes configured.[/yellow]"
            )

            console.print(
                "Add nodes under fleet.nodes in atlas.yaml"
            )

        return

    if not json_output:

        console.print(
            "[bold cyan]Atlas Fleet Doctor[/bold cyan]\n"
        )

    results = []

    for node in nodes:

        result = run_remote_doctor(node)

        results.append(
            {
                "name": node.name,
                "host": node.host,
                **result
            }
        )

    healthy = all(
        result.get("reachable") and result.get("healthy")
        for result in results
    )

    if json_output:

        print(
            json.dumps(
                {"nodes": results, "healthy": healthy},
                indent=2
            )
        )

    else:

        for result in results:

            if not result["reachable"]:

                console.print(
                    f"[red]✗ {result['name']} ({result['host']}): "
                    f"unreachable - {result['error']}[/red]"
                )

                continue

            symbol = (
                "[green]✓[/green]" if result["healthy"] else "[yellow]![/yellow]"
            )

            console.print(
                f"{symbol} {result['name']} ({result['host']})"
            )

            for check in result["checks"]:

                sub_symbol = (
                    "[green]✓[/green]" if check["status"] else "[yellow]![/yellow]"
                )

                console.print(
                    f"    {sub_symbol} {check['name']}: {check['details']}"
                )

    if not healthy:
        raise typer.Exit(code=1)


@fleet_app.command(name="trends")
def fleet_trends(
    limit: int = 20,
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Run atlas trends on every configured fleet node over SSH and
    aggregate the results. Unlike fleet doctor, there is no fleet-wide
    "healthy" concept - atlas trends itself has no health/threshold
    concept to signal - so the exit code reflects reachability only.
    """

    settings = load_config()

    nodes = settings.fleet.nodes

    if not nodes:

        if json_output:

            print(
                json.dumps(
                    {"nodes": []},
                    indent=2
                )
            )

        else:

            console.print(
                "[yellow]No fleet nodes configured.[/yellow]"
            )

            console.print(
                "Add nodes under fleet.nodes in atlas.yaml"
            )

        return

    if not json_output:

        console.print(
            "[bold cyan]Atlas Fleet Trends[/bold cyan]\n"
        )

    results = []

    for node in nodes:

        result = run_remote_trends(node, limit=limit)

        results.append(
            {
                "name": node.name,
                "host": node.host,
                **result
            }
        )

    all_reachable = all(result["reachable"] for result in results)

    if json_output:

        print(
            json.dumps(
                {"nodes": results},
                indent=2
            )
        )

    else:

        for result in results:

            console.print(
                f"[bold]{result['name']} ({result['host']}):[/bold]"
            )

            if not result["reachable"]:

                console.print(
                    f"  [red]unreachable - {result['error']}[/red]\n"
                )

                continue

            if (
                not result["host"]
                and not result["containers"]
                and not result["guests"]
            ):

                console.print(
                    "  [yellow]No monitoring history found.[/yellow]\n"
                )

                continue

            _print_trend_summaries(result["host"])

            for container_name, container_payload in result["containers"].items():

                console.print(
                    f"  {container_name}:"
                )

                _print_trend_summaries(container_payload)

            for vmid, guest_payload in result["guests"].items():

                console.print(
                    f"  {guest_payload['name']} ({vmid}):"
                )

                _print_trend_summaries(
                    {k: v for k, v in guest_payload.items() if k != "name"}
                )

            console.print()

    if not all_reachable:
        raise typer.Exit(code=1)


@fleet_app.command(name="report")
def fleet_report(
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Run atlas report on every configured fleet node over SSH and
    aggregate the results. No fleet-wide "healthy" concept - the exit
    code reflects reachability only, same as atlas fleet trends.
    """

    settings = load_config()

    nodes = settings.fleet.nodes

    if not nodes:

        if json_output:

            print(
                json.dumps(
                    {"nodes": []},
                    indent=2
                )
            )

        else:

            console.print(
                "[yellow]No fleet nodes configured.[/yellow]"
            )

            console.print(
                "Add nodes under fleet.nodes in atlas.yaml"
            )

        return

    if not json_output:

        console.print(
            "[bold cyan]Atlas Fleet Report[/bold cyan]\n"
        )

    results = []

    for node in nodes:

        result = run_remote_report(node)

        results.append(
            {
                "name": node.name,
                "host": node.host,
                **result
            }
        )

    all_reachable = all(result["reachable"] for result in results)

    if json_output:

        print(
            json.dumps(
                {"nodes": results},
                indent=2
            )
        )

    else:

        for result in results:

            console.print(
                f"[bold]{result['name']} ({result['host']}):[/bold]"
            )

            if not result["reachable"]:

                console.print(
                    f"  [red]unreachable - {result['error']}[/red]\n"
                )

                continue

            if "inventory" in result and result["inventory"] is None:

                console.print(
                    "  [yellow]No inventory found - run atlas discover "
                    "on that node.[/yellow]\n"
                )

                continue

            console.print(
                "  System:", result["system"]
            )

            console.print(
                "  Hardware:", result["hardware"], "\n"
            )

    if not all_reachable:
        raise typer.Exit(code=1)



app.add_typer(
    proxmox_app
)

app.add_typer(
    libvirt_app
)

app.add_typer(
    fleet_app
)
