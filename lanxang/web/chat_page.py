"""
/chat: a chat panel over POST /api/chat. Suggested actions/plans render as
steps with Approve buttons; each Approve runs exactly one step via
POST /api/actions/execute, and the next step only unlocks after the
previous one succeeded. Text only ever goes in via textContent.
"""

from lanxang.web.chat_assets import CHAT_SCRIPT, CHAT_STYLE
from lanxang.web import render
from lanxang.web.render import _esc, empty_state, render_page


def render_chat_page(prefill=""):

    if not render.AI_ON:
        return render_page("Chat", empty_state(
            "chat", "No AI assistant set up", "Chat answers questions about your network once an AI model is "
            "connected: Ollama on your own hardware, or Claude with an API key.",
            ("/settings#ai", "Set up in Setup")), drawer=False)

    body = (
        CHAT_STYLE
        + "<p class=\"muted\">Same assistant as <code>lanxang chat</code>: it can look at containers, logs and "
          "whatever integrations are configured, plus your notes. Anything it suggests runs only when you press "
          "Approve, one step at a time, after Lanxang re-checks the target still exists.</p>"
        + "<div id=\"log\"></div>"
        + f"<textarea id=\"ask\" placeholder=\"Ask about your network...\">{_esc(prefill)}</textarea>"
        + "<p><button class=\"primary\" id=\"send\">Send</button> <button id=\"new-chat\">New conversation</button> "
          "<span class=\"muted\" id=\"chat-status\"></span></p>"
        + CHAT_SCRIPT
    )

    return render_page("Chat", body, drawer=False)
