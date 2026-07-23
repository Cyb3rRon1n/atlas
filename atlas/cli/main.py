import typer
from atlas.discovery import run_discovery
from atlas.inventory import save_inventory
from atlas.inventory import load_inventory
from atlas.reporting.generator import generate_report
from atlas.config import load_config
from atlas.health import run_checks
from atlas.docker import collect_containers
from atlas.services import detect_services
from atlas.compose import parse_compose_file
from atlas.proxmox import connect, discover_nodes
from rich.console import Console

from atlas import __version__


app = typer.Typer(
    name="atlas",
    help="AI-powered operations platform for self-hosted infrastructure."
)

console = Console()


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
def doctor():
    """
    Run Atlas health checks.
    """

    console.print(
        "[bold cyan]Atlas Doctor[/bold cyan]\n"
    )

    results = run_checks()

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

    console.print(
        "\n[green]✓ Discovery complete[/green]"
    )

    console.print(
        f"[cyan]Inventory saved:[/cyan] {inventory_file}"
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
def proxmox():
    """
    Display Proxmox infrastructure.
    """

    console.print(
        "[bold blue]Proxmox Discovery[/bold blue]\n"
    )


    console.print(
        "Proxmox integration configured."
    )
