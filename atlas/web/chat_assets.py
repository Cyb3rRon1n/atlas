"""
Shared chat CSS/JS/markup, used by both the full /chat page (chat_page.py)
and the slide-out drawer render_page() puts on every other page. No
imports from atlas.web.render - render.py imports this module, so a
reverse import would be circular.
"""


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

DRAWER_HTML = (
    '<aside id="chat-drawer" hidden aria-label="Chat with Atlas">'
    '<div class="drawer-head"><h2>Chat with Atlas</h2>'
    '<button id="chat-close" aria-label="Close chat">Close</button></div>'
    '<div id="log"></div>'
    '<label for="ask" class="sr-only">Message Atlas</label>'
    '<textarea id="ask" placeholder="Ask, troubleshoot, diagnose..."></textarea>'
    '<p><button class="primary" id="send">Send</button> <button id="new-chat">New conversation</button> '
    '<span class="muted" id="chat-status"></span></p></aside>'
)

DRAWER_STYLE = """
<style>
#chat-drawer { position:fixed; top:0; right:0; bottom:0; width:min(420px,100vw); box-sizing:border-box;
  background:#111821; border-left:1px solid #222c38; padding:16px; display:flex; flex-direction:column; gap:12px; z-index:10; }
#chat-drawer[hidden] { display:none; }
#chat-drawer .drawer-head { display:flex; justify-content:space-between; align-items:center; }
#chat-drawer .drawer-head h2 { margin:0; font-size:15px; }
#chat-drawer #log { flex:1; overflow-y:auto; }
.sr-only { position:absolute; left:-9999px; }
@media (min-width: 1400px) { body.drawer-open .page { margin-right:420px; } }
</style>
"""

CHAT_SCRIPT = """
<script>
const log = document.getElementById("log");
const ask = document.getElementById("ask");
const sendButton = document.getElementById("send");
const newChat = document.getElementById("new-chat");
const status = document.getElementById("chat-status");
const drawer = document.getElementById("chat-drawer");
const LOG_KEY = "atlasChatLog";

function setDrawerOpen(open) {
  if (!drawer) return;
  drawer.hidden = !open;
  document.body.classList.toggle("drawer-open", open);
}

function saveLog(who, text) {
  try { const items = JSON.parse(sessionStorage.getItem(LOG_KEY) || "[]"); items.push({who, text});
        sessionStorage.setItem(LOG_KEY, JSON.stringify(items.slice(-50))); } catch (error) {}
}

function restoreLog() {
  try { JSON.parse(sessionStorage.getItem(LOG_KEY) || "[]").forEach((m) => bubble(m.text, m.who, true)); } catch (error) {}
}

// Exposed as window.atlasAsk in a real browser (globalThis === window there); globalThis is used
// directly so this script also loads cleanly under a bare Node engine with no window global (see
// tests/test_web_chat_page.py's real-JS-engine test).
globalThis.atlasAsk = (text) => { setDrawerOpen(true); ask.value = text; ask.focus(); };

let memorySession = null;

function getSession() {
  // Private-browsing/quota-denied sessionStorage must not crash the page - fall back to a plain variable.
  try { return sessionStorage.getItem("atlasChat"); } catch (error) { return memorySession; }
}

function setSession(value) {
  try { sessionStorage.setItem("atlasChat", value); } catch (error) { memorySession = value; }
}

function clearSession() {
  try { sessionStorage.removeItem("atlasChat"); } catch (error) { memorySession = null; }
}

function bubble(text, who, restoring) {
  const div = document.createElement("div");
  div.className = "bubble " + who;
  div.textContent = text;
  log.appendChild(div);
  div.scrollIntoView({block: "end"});
  if (!restoring) saveLog(who, text);
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
  if (sendButton.disabled) return;  // in-flight guard - also blocks Enter firing a second send mid-request
  const message = ask.value.trim();
  if (!message) return;
  bubble(message, "you");
  ask.value = "";
  sendButton.disabled = true;
  newChat.disabled = true;  // a reset mid-flight must not let this reply's setSession() overwrite the new session
  status.textContent = "atlas is thinking... (a local model can take up to a minute)";
  try {
    const {response, data} = await post("/api/chat", {message, session: getSession()});
    if (!response.ok || !data) { bubble(failureText(response, data), "atlas"); return; }
    setSession(data.session);
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
  finally { sendButton.disabled = false; newChat.disabled = false; status.textContent = ""; }
}

sendButton.addEventListener("click", send);
ask.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } });
newChat.addEventListener("click", () => {
  clearSession();
  log.textContent = "";
  try { sessionStorage.removeItem(LOG_KEY); } catch (error) {}
});

restoreLog();
if (drawer) {
  const chatToggle = document.getElementById("chat-toggle");
  const chatClose = document.getElementById("chat-close");
  if (chatToggle) chatToggle.addEventListener("click", () => setDrawerOpen(drawer.hidden));
  if (chatClose) chatClose.addEventListener("click", () => setDrawerOpen(false));
}
</script>
"""
