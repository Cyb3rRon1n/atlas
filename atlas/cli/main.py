import json

import typer
from atlas.discovery import run_discovery
from atlas.inventory import save_inventory
from atlas.inventory import load_inventory
from atlas.reporting.generator import generate_report
from atlas.config import load_config, write_config, write_setup_log
from atlas.config.loader import CONFIG_FILE
from atlas.config.models import AtlasConfig, IntelligenceConfig, MonitoringConfig, ProxmoxConfig
from atlas.health import run_checks
from atlas.plugins import PluginManager
from atlas.events import AtlasEvent
from atlas.knowledge.queries import KnowledgeQueries
from atlas.knowledge.store import KnowledgeStore
from atlas.core.application import application

from atlas import __version__
from atlas.cli.app import app, console


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

    by_category = {}

    for plugin in manager.get_plugins():

        by_category.setdefault(
            plugin.category, {}
        )[plugin.name] = plugin_data.get(plugin.name)

    for category, category_data in by_category.items():

        runtime.environment.update(
            category,
            category_data
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
def report(
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of generating a Markdown report."
    )
):
    """
    Generate Atlas infrastructure report.
    """

    inventory = load_inventory()

    if json_output:
        print(json.dumps(inventory, indent=2))
        return

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
            f"✓ {plugin.name} ({plugin.version}) — {plugin.category}"
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
def web(
    host: str = "127.0.0.1",
    port: int = 8420
):
    """
    Serve a local web view over Atlas's existing data (overview, triage,
    devices, map, coverage, history, trends) — read-only except the
    device inventory's edit/merge/split, which are same-origin-gated JSON
    POSTs. Sign-in is atlas's own (web.auth: builtin) unless web.auth: proxy.
    """

    from atlas.web.auth import Auth
    from atlas.web.server import run_server

    console.print(
        "[bold blue]Atlas Web[/bold blue]\n"
    )

    auth = Auth() if load_config().web.auth == "builtin" else None
    if auth and not auth.configured():
        console.print(f"First run: open the page and set the admin password. Setup code: [bold]{auth.setup_code()}[/bold]")

    console.print(
        f"Serving at http://{host}:{port} (Ctrl+C to stop)"
    )

    try:
        run_server(host, port, auth)
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Stopped.[/yellow]"
        )

auth_app = typer.Typer(help="Sign-in for atlas web (web.auth: builtin).")
app.add_typer(auth_app, name="auth")


@auth_app.command("password")
def auth_password():
    """Set or reset the admin password (signs everyone out). Reads stdin when it isn't a terminal."""

    import getpass
    import sys

    from atlas.web.auth import Auth

    if sys.stdin.isatty():
        password = getpass.getpass("New atlas password: ")
        if getpass.getpass("Again: ") != password:
            console.print("[red]The passwords don't match.[/red]")
            raise typer.Exit(1)
    else:
        password = sys.stdin.readline().rstrip("\n")
    try:
        Auth().set_password(password)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1)
    console.print("[green]Password saved.[/green]")


@auth_app.command("setup-code")
def auth_setup_code():
    """The one-time code the first-run web page asks for."""

    from atlas.web.auth import Auth

    auth = Auth()
    if auth.configured():
        console.print("A password is already set - use `atlas auth password` to change it.")
        return
    print(auth.setup_code())


@auth_app.command("token")
def auth_token(new: bool = typer.Option(False, "--new", help="Replace the token (the old one stops working).")):
    """The read-only API token for dashboards (header: Authorization: Bearer <token>)."""

    from atlas.web.auth import Auth

    print(Auth().token(new=new))


# Each module registers its commands on the shared app when imported.
from atlas.cli import ai, containers, virt, watch  # noqa: E402,F401


if __name__ == "__main__":
    app()
