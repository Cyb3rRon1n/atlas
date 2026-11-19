"""
Shared chat CSS/JS/markup, used by both the full /chat page (chat_page.py)
and the slide-out drawer render_page() puts on every other page. No
imports from lanxang.web.render - render.py imports this module, so a
reverse import would be circular.
"""


CHAT_STYLE = """
<style>
  #log { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem; }
  .bubble { padding: 0.6rem 0.9rem; border-radius: 8px; max-width: 80ch; white-space: pre-wrap; }
  .you { align-self: flex-end; background: color-mix(in srgb, var(--accent) 20%, transparent); border: 1px solid var(--accent); }
  .atlas { align-self: flex-start; background: var(--surface); border: 1px solid var(--line2); }
  .step { margin: 0.4rem 0; padding: 0.4rem 0.6rem; border: 1px solid var(--line2); border-radius: 6px; }
  .step code { margin-right: 0.5rem; }
  .ok { color: var(--green); } .bad { color: var(--red); }
  #ask { width: 100%; box-sizing: border-box; min-height: 4rem; }
</style>
"""

DRAWER_HTML = (
    # Closed until someone opens it (then remembered), applied before first paint so the page never jumps.
    '<script>try { if (localStorage.getItem("atlasChatCollapsed") !== "0") document.body.classList.add("chat-collapsed"); }'
    ' catch (error) { document.body.classList.add("chat-collapsed"); }</script>'
    '<aside id="chat-drawer" aria-label="Chat with Lanxang">'
    '<div class="drawer-head"><h2>Chat with Lanxang</h2>'
    '<button id="chat-close" aria-label="Collapse chat" aria-controls="chat-drawer">&rsaquo;</button></div>'
    '<div id="log"></div>'
    '<label for="ask" class="sr-only">Message Lanxang</label>'
    '<textarea id="ask" placeholder="Ask, troubleshoot, diagnose..."></textarea>'
    '<p><button class="primary" id="send">Send</button> <button id="new-chat">New conversation</button> '
    '<span class="muted" id="chat-status"></span></p></aside>'
    '<button id="chat-fab" class="primary" aria-controls="chat-drawer">Chat</button>'
)

DRAWER_STYLE = """
<style>
.shell.docked { display:grid; grid-template-columns:minmax(0,1fr) clamp(280px, 30vw, 380px); }   /* narrower beside a small window */
@media (min-width: 901px) {
  /* Desktop: the page scrolls inside <main>, so the chat column always fills the window beside it. */
  body:has(.shell.docked) { height:100vh; display:flex; flex-direction:column; overflow:hidden; }
  body:has(.shell.docked) .app { flex:1; min-height:0; }
  body:has(.shell.docked) .side { overflow-y:auto; }
  .shell.docked { flex:1; min-height:0; }
  .shell.docked > main { overflow-y:auto; min-height:0; }
  .shell.docked #chat-drawer { position:static; height:auto; min-height:0; }
}
body.chat-collapsed .shell.docked { grid-template-columns:minmax(0,1fr) 44px; }
#chat-drawer { position:sticky; top:0; height:100vh; box-sizing:border-box; background:var(--surface);
  border-left:1px solid var(--line); padding:16px; display:flex; flex-direction:column; gap:12px; min-width:0; }
#chat-drawer .drawer-head { display:flex; justify-content:space-between; align-items:center; gap:8px; }
#chat-drawer .drawer-head h2 { margin:0; font-size:.9375rem; border:0; }
#chat-drawer #log { flex:1; overflow-y:auto; }
#chat-drawer .bubble { max-width:100%; }
body.chat-collapsed #chat-drawer { padding:12px 4px; }
body.chat-collapsed #chat-drawer > :not(.drawer-head), body.chat-collapsed #chat-drawer h2 { display:none; }
#chat-close { width:32px; min-height:32px; padding:0; font-size:1.125rem; line-height:1; }
#chat-fab { display:none; box-shadow:0 2px 8px color-mix(in srgb, var(--text) 25%, transparent); }
.sr-only { position:absolute; left:-9999px; }
@media (max-width: 900px) {
  .shell.docked, body.chat-collapsed .shell.docked { display:block; }
  #chat-drawer { position:fixed; inset:0; height:auto; z-index:10; border-left:0; }
  body.chat-collapsed #chat-drawer { display:none; }
  body.chat-collapsed #chat-fab { display:block; position:fixed; right:16px; bottom:16px; z-index:9; }
}
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

function syncCollapseButton(open) {
  const close = document.getElementById("chat-close");
  close.textContent = open ? "\u203a" : "\u2039";
  close.setAttribute("aria-label", open ? "Collapse chat" : "Expand chat");
}

function setDrawerOpen(open) {
  if (!drawer) return;
  document.body.classList.toggle("chat-collapsed", !open);
  syncCollapseButton(open);
  try { localStorage.setItem("atlasChatCollapsed", open ? "0" : "1"); } catch (error) {}
  window.dispatchEvent(new Event("resize"));   // Cytoscape maps refit to the new width
  if (open) ask.focus();
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

async function sendText(message, useTools = true) {
  bubble(message, "you");
  sendButton.disabled = true;
  newChat.disabled = true;  // a reset mid-flight must not let this reply's setSession() overwrite the new session
  status.textContent = "Lanxang is thinking... (a local model can take up to a minute)";
  try {
    const {response, data} = await post("/api/chat", {message, session: getSession(), tools: useTools});
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

async function send() {
  if (sendButton.disabled) return;  // in-flight guard - also blocks Enter firing a second send mid-request
  const message = ask.value.trim();
  if (!message) return;
  ask.value = "";
  await sendText(message);
}

// Send several messages one after another, each awaiting its own reply. A question covering a
// long list is answered in small batches the local model can actually finish, instead of one
// turn it runs out of room on. Used by the posture page's "Investigate all".
globalThis.atlasAskAll = async (texts) => {
  setDrawerOpen(true);
  for (const text of texts) { if (text) await sendText(text, false); }
};

sendButton.addEventListener("click", send);
ask.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } });
newChat.addEventListener("click", () => {
  clearSession();
  log.textContent = "";
  try { sessionStorage.removeItem(LOG_KEY); } catch (error) {}
});

restoreLog();
if (drawer) {
  const collapsed = () => document.body.classList.contains("chat-collapsed");
  ["chat-toggle", "chat-close", "chat-fab"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.addEventListener("click", () => setDrawerOpen(collapsed()));
  });
  syncCollapseButton(!collapsed());   // the pre-paint script may have collapsed it
}
</script>
"""
