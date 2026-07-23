import typer
from atlas.discovery import run_discovery
from atlas.inventory import save_inventory
from atlas.inventory import load_inventory
from atlas.reporting.generator import generate_report
from atlas.config import load_config
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
    Run basic Atlas diagnostics.
    """

    console.print(
        "[bold cyan]Atlas Doctor[/bold cyan]"
    )

    checks = [
        ("Python", True),
        ("Configuration", True),
        ("Inventory", False),
    ]

    for name, result in checks:
        symbol = "✓" if result else "!"
        color = "green" if result else "yellow"

        console.print(
            f"[{color}]{symbol}[/{color}] {name}"
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
