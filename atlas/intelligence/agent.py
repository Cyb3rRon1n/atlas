from atlas.actions import is_action_grounded
from atlas.config.models import AtlasConfig
from atlas.intelligence.providers import AIProvider, ChatReply
from atlas.intelligence.tools import build_tools, execute_tool


class AtlasAgent:
    """
    Runs a multi-turn conversation through an AI provider's tool-use
    loop, backing atlas chat. Plays the same orchestration role
    AtlasAnalyzer plays for atlas analyze's single-shot flow, but for
    an ongoing session that has no guaranteed prior atlas discover.
    """

    def __init__(self, provider: AIProvider, config: AtlasConfig):

        self.provider = provider
        self.config = config
        self.tools = build_tools(config)

    def converse(self, messages: list) -> ChatReply:

        reply = self.provider.converse(self._with_notes(messages), self.tools)

        if not reply.action and not reply.plan:
            return reply

        environment = self._live_environment()

        if reply.action and not is_action_grounded(reply.action, environment):
            reply.action = None

        if reply.plan and not all(
            is_action_grounded(step.action, environment)
            for step in reply.plan.steps
        ):

            # Same "drop the whole plan on one bad step" rule
            # AtlasAnalyzer applies - see its analyze() for why.
            reply.plan = None

        if reply.plan and reply.action:

            # Seen in real testing: the model can propose a plan and
            # still fill in the standalone action (usually a copy of
            # the plan's own first step), which would print as a
            # redundant "suggested action" alongside the plan. The
            # prompt asks the model not to do this, but that's not
            # enforced - same reasoning as grounding above.
            reply.action = None

        return reply

    def _with_notes(self, messages: list) -> list:
        """
        Attach pinned notes + the best-matching note sections to the latest
        question, instead of trusting the model to call search_notes -
        found live: a small local model often skips the lookup and answers
        from generic knowledge (or misreads a failed tool call). Works on a
        copy, so the session history doesn't accumulate the excerpts.
        """

        knowledge = self.config.knowledge

        if not (knowledge.pinned_paths or (knowledge.notes_paths and knowledge.auto_context)):
            return messages

        last = next(
            (index for index in range(len(messages) - 1, -1, -1)
             if messages[index].get("role") == "user" and isinstance(messages[index].get("content"), str)),
            None
        )

        if last is None:
            return messages

        question = messages[last]["content"]
        parts = []

        for path in knowledge.pinned_paths:

            try:
                with open(path, errors="replace") as handle:
                    parts.append(f"[Pinned: {path}]\n{handle.read()[:3000]}")

            except OSError:
                continue

        if knowledge.notes_paths and knowledge.auto_context:

            from atlas.knowledge.notes import search_notes

            for hit in search_notes(knowledge.notes_paths, question, limit=knowledge.auto_context)["results"]:
                parts.append(f"[Note: {hit['file']} - {hit['section']}]\n{hit['excerpt'][:900]}")

        if not parts:
            return messages

        augmented = list(messages)
        augmented[last] = {
            **messages[last],
            "content": (
                "Background from the operator's own notes (use it if relevant, "
                "verify with tools, ignore if unrelated):\n\n"
                + "\n\n".join(parts)
                + f"\n\nQuestion: {question}"
            )
        }

        return augmented

    def _live_environment(self) -> dict:
        """
        A minimal, freshly-queried stand-in for the saved environment
        snapshot atlas analyze grounds suggested actions against.
        Chat has no guaranteed prior atlas discover to read a
        snapshot from, so it grounds against current live state
        instead - the same read paths the get_containers/
        get_proxmox_status tools already use, not a second copy of
        the connection logic.
        """

        from atlas.docker import collect_containers

        environment = {
            "containers": {
                "Docker": collect_containers()
            }
        }

        if "get_proxmox_status" in self.tools:

            proxmox_data = execute_tool(self.tools, "get_proxmox_status", {})

            environment["virtualization"] = {
                "guests": proxmox_data.get("guests", [])
            }

            if "error" in proxmox_data:

                # Lets atlas/web/chat.py's execute_step() tell "Proxmox is
                # down" (503) apart from "this target genuinely doesn't
                # exist" (409) - known_guest_ids()/the CLI only ever read
                # "guests", so this extra key doesn't affect them.
                environment["virtualization"]["error"] = proxmox_data["error"]

        return environment
