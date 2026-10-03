"""
/chat: a chat panel over POST /api/chat. Suggested actions/plans render as
steps with Approve buttons; each Approve runs exactly one step via
POST /api/actions/execute, and the next step only unlocks after the
previous one succeeded. Text only ever goes in via textContent.
"""

from atlas.web.render import _esc, render_page


CHAT_STYLE = """
<style>
  #log { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem; }
  .bubble { padding: 0.6rem 0.9rem; border-radius: 8px; max-width: 80ch; white-space: pre-wrap; }
  .you { align-self: flex-end; background: #1f6feb33; border: 1px solid #1f6feb; }
  .atlas { align-self: flex-start; background: #161b22; border: 1px solid #30363d; }
  .step { margin: 0.4rem 0; padding: 0.4rem 0.6rem; border: 1px solid #30363d; border-radius: 6px; }
  .step code { margin-right: 0.5rem; }
  .ok { color: #3fb950; } .bad { color: #f85149; }
  #ask { width: 100%; box-sizing: border-box; min-height: 4rem; }
</style>
"""

CHAT_SCRIPT = """
<script>
const log = document.getElementById("log");
const ask = document.getElementById("ask");
const sendButton = document.getElementById("send");
const status = document.getElementById("chat-status");

function bubble(text, who) {
  const div = document.createElement("div");
  div.className = "bubble " + who;
  div.textContent = text;
  log.appendChild(div);
  div.scrollIntoView({block: "end"});
  return div;
}

function failureText(response, data) {
  if (data && data.error) return data.error;
  const expired = response.status === 401 || response.status === 403 || response.redirected;
  return "Failed: " + response.status + (expired ? " (session expired? reload the page)" : "");
}

async function post(url, body) {
  const response = await fetch(url, {method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await response.json().catch(() => null);
  return {response, data};
}

function renderSteps(container, steps) {
  // Each step unlocks only after the previous one succeeded - a failed or skipped step stops the plan.
  const buttons = [];
  steps.forEach((step, index) => {
    const row = document.createElement("div");
    row.className = "step";
    const code = document.createElement("code");
    code.textContent = step.action.command || (step.action.type + " " + step.action.target);
    const why = document.createElement("span");
    why.className = "muted";
    why.textContent = step.rationale || "";
    const button = document.createElement("button");
    button.textContent = "Approve";
    button.className = "primary";
    button.disabled = index > 0;
    const result = document.createElement("div");
    button.addEventListener("click", async () => {
      button.disabled = true;
      result.textContent = "Running...";
      try {
        const {response, data} = await post("/api/actions/execute", {action: step.action});
        if (!response.ok || !data) { result.className = "bad"; result.textContent = failureText(response, data); return; }
        result.className = data.ok ? "ok" : "bad";
        result.textContent = data.ok ? "Done." : ("Failed: " + (data.result && data.result.error || "unknown error"));
        if (data.ok && buttons[index + 1]) buttons[index + 1].disabled = false;
      } catch (error) { result.className = "bad"; result.textContent = "Request failed: " + error; }
    });
    buttons.push(button);
    row.append(code, button, why, result);
    container.appendChild(row);
  });
}

async function send() {
  const message = ask.value.trim();
  if (!message) return;
  bubble(message, "you");
  ask.value = "";
  sendButton.disabled = true;
  status.textContent = "atlas is thinking... (a local model can take 10-30 seconds)";
  try {
    const {response, data} = await post("/api/chat", {message, session: sessionStorage.getItem("atlasChat")});
    if (!response.ok || !data) { bubble(failureText(response, data), "atlas"); return; }
    sessionStorage.setItem("atlasChat", data.session);
    const reply = bubble(data.text, "atlas");
    if (data.plan) {
      const title = document.createElement("div");
      title.textContent = "Suggested plan: " + data.plan.summary;
      reply.appendChild(title);
      renderSteps(reply, data.plan.steps);
    } else if (data.action) {
      renderSteps(reply, [{action: data.action, rationale: ""}]);
    }
  } catch (error) { bubble("Request failed: " + error, "atlas"); }
  finally { sendButton.disabled = false; status.textContent = ""; }
}

sendButton.addEventListener("click", send);
ask.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } });
document.getElementById("new-chat").addEventListener("click", () => { sessionStorage.removeItem("atlasChat"); log.textContent = ""; });
</script>
"""


def render_chat_page(prefill=""):

    body = (
        CHAT_STYLE
        + "<p class=\"muted\">Same assistant as <code>atlas-chat</code>: it can look at containers, logs, Proxmox, "
          "Jellyfin and your notes. Anything it suggests runs only when you press Approve, one step at a time, "
          "after atlas re-checks the target still exists.</p>"
        + "<div id=\"log\"></div>"
        + f"<textarea id=\"ask\" placeholder=\"Ask about your network...\">{_esc(prefill)}</textarea>"
        + "<p><button class=\"primary\" id=\"send\">Send</button> <button id=\"new-chat\">New conversation</button> "
          "<span class=\"muted\" id=\"chat-status\"></span></p>"
        + CHAT_SCRIPT
    )

    return render_page("Chat", body)
