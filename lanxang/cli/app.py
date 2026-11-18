"""The `atlas` Typer app and helpers the command modules share."""


import typer
from lanxang.config import load_config
from rich.console import Console



app = typer.Typer(
    name="atlas",
    help="Self-hosted watchdog for your home network: devices, cabling, security and alerts."
)

console = Console()



def _resolve_fleet_node(node_name):
    """
    Look up a configured FleetNode by name for --node on
    restart/stop/resize commands (Docker and libvirt). Returns
    (FleetNode, error) - error is set and the node is None when
    node_name doesn't match any configured node; both are None when
    node_name itself is None (the normal, local-target case).
    """

    if node_name is None:
        return None, None

    settings = load_config()

    for node in settings.fleet.nodes:
        if node.name == node_name:
            return node, None

    return None, f"No fleet node named '{node_name}' configured"

def _print_trend_summaries(summaries):

    for metric_name, summary in summaries.items():

        console.print(
            f"  {metric_name}: latest {summary['latest']:.1f}%, "
            f"min {summary['min']:.1f}%, max {summary['max']:.1f}%, "
            f"avg {summary['avg']:.1f}% ({summary['samples']} samples)"
        )

