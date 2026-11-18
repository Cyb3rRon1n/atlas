"""The AI model: status, analysis and chat."""

import json
from dataclasses import asdict

import typer
from lanxang.actions import ACTIONS, PLAN_STEP_EVENT_TYPES, execute_action
from lanxang.config import load_config
from lanxang.events import AtlasEvent
from lanxang.knowledge.queries import KnowledgeQueries
from lanxang.knowledge.store import KnowledgeStore
from lanxang.core.application import application
from lanxang.intelligence.agent import AtlasAgent
from lanxang.intelligence.analyzer import AtlasAnalyzer
from lanxang.intelligence.providers import AIProviderError, get_provider
from lanxang.intelligence.tools import build_tools

from lanxang.cli.app import app, console


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
def analyze(
    json_output: bool = typer.Option(
        False, "--json",
        help="Print machine-readable JSON instead of formatted output."
    )
):
    """
    Analyze the latest environment snapshot with AI and
    produce a summary and recommendations.
    """

    if not json_output:

        console.print(
            "[bold blue]Atlas Analysis[/bold blue]\n"
        )

    query = KnowledgeQueries()

    environment = query.latest_environment()

    if not environment:

        if json_output:

            print(json.dumps(None))

        else:

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

        if json_output:

            print(json.dumps({"error": str(error)}, indent=2))

        else:

            console.print(
                f"[red]Analysis failed:[/red] {error}"
            )

        raise typer.Exit(code=1)

    if json_output:

        print(
            json.dumps(
                {
                    **asdict(result),
                    "provider": settings.intelligence.provider,
                    "model": settings.intelligence.model
                },
                indent=2
            )
        )

    else:

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
            reply = agent.converse(list(messages))

        except AIProviderError as error:

            messages.pop()  # drop the question - this turn never got a reply

            console.print(
                f"\n[red]{error}[/red]\n"
            )

            continue

        messages.append({
            "role": "assistant",
            "content": reply.text
        })

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
