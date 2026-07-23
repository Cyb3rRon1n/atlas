import typer
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

    console.print(
        "Discovery engine coming soon..."
    )
