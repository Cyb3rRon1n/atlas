"""Docker containers and the local monitoring scan."""

import json

import typer
from atlas.config import load_config
from atlas.docker import collect_containers, get_container_info, resize_container, restart_container, stop_container
from atlas.services import detect_services
from atlas.compose import parse_compose_file
from atlas.monitoring import collect_container_metrics, collect_metrics, evaluate_thresholds
from atlas.monitoring.changes import diff_monitoring, format_change as format_monitoring_change
from atlas.events import AtlasEvent
from atlas.knowledge.queries import KnowledgeQueries
from atlas.knowledge.store import KnowledgeStore
from atlas.core.application import application

from atlas.cli.app import app, console, _resolve_fleet_node


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
def restart(
    name: str,
    node: str = typer.Option(
        None, "--node",
        help="Restart on this fleet node's Docker daemon instead of locally."
    )
):
    """
    Restart a Docker container (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Restart[/bold blue]\n"
    )

    fleet_node, error = _resolve_fleet_node(node)

    if error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    info = get_container_info(name, node=fleet_node)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    if fleet_node:
        console.print(f"Node: {fleet_node.name} ({fleet_node.host})")

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

    result = restart_container(name, node=fleet_node)

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.container_restarted",
            source="RestartAction",
            payload={
                "container": name,
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
        f"\n[green]✓ Container '{name}' restarted[/green]"
    )


@app.command()
def stop(
    name: str,
    node: str = typer.Option(
        None, "--node",
        help="Stop on this fleet node's Docker daemon instead of locally."
    )
):
    """
    Stop a Docker container (requires confirmation).
    """

    console.print(
        "[bold blue]Atlas Stop[/bold blue]\n"
    )

    fleet_node, error = _resolve_fleet_node(node)

    if error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    info = get_container_info(name, node=fleet_node)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    if fleet_node:
        console.print(f"Node: {fleet_node.name} ({fleet_node.host})")

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

    result = stop_container(name, node=fleet_node)

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.container_stopped",
            source="StopAction",
            payload={
                "container": name,
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
        f"\n[green]✓ Container '{name}' stopped[/green]"
    )


@app.command()
def resize(
    name: str,
    cpus: float = typer.Option(None, help="New CPU limit in cores, e.g. 1.5"),
    memory: str = typer.Option(None, help="New memory limit, e.g. 512m or 1g"),
    node: str = typer.Option(
        None, "--node",
        help="Resize on this fleet node's Docker daemon instead of locally."
    )
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

    fleet_node, error = _resolve_fleet_node(node)

    if error:

        console.print(
            f"[red]{error}[/red]"
        )

        return

    info = get_container_info(name, node=fleet_node)

    if not info["found"]:

        console.print(
            f"[red]{info['error']}[/red]"
        )

        return

    if fleet_node:
        console.print(f"Node: {fleet_node.name} ({fleet_node.host})")

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
        mem_limit=memory,
        node=fleet_node
    )

    runtime = application.runtime

    runtime.events.publish(
        AtlasEvent(
            event_type="atlas.action.container_resized",
            source="ResizeAction",
            payload={
                "container": name,
                "node": fleet_node.name if fleet_node else None,
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
