import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from atlas.web.chat_page import CHAT_SCRIPT, render_chat_page


def test_chat_page_prefills_from_q_and_has_no_drawer():

    html = render_chat_page("hello <b>")

    assert "hello &lt;b&gt;" in html and 'id="chat-drawer"' not in html
    assert html.count('id="ask"') == 1


def test_chat_page_structure_and_prefill_escaping():

    page = render_chat_page('Tell me about <b>"tv"</b>')

    assert '<div id="log"' in page and '<textarea id="ask"' in page and 'id="send"' in page
    assert "&lt;b&gt;&quot;tv&quot;&lt;/b&gt;" in page and "<b>" not in page.split("<script>")[0].split("<h1>")[1]
    assert "/api/chat" in page and "/api/actions/execute" in page
    assert "innerHTML" not in CHAT_SCRIPT
    assert "<code>atlas chat</code>" in page and "<code>atlas-chat</code>" not in page
    assert "whatever integrations are configured, plus your notes" in page
    assert "a local model can take up to a minute" in CHAT_SCRIPT
    assert "10-30 seconds" not in CHAT_SCRIPT


def test_chat_script_enables_next_step_only_after_success():

    # The step-gating contract lives in the script: a step button starts disabled unless it is
    # the first, and the next one only flips to enabled once its predecessor reports ok: true.
    # These are the literal fragments that implement that contract, not just loosely-related words.
    assert "disabled" in CHAT_SCRIPT and "sessionStorage" in CHAT_SCRIPT
    assert "button.disabled = index > 0" in CHAT_SCRIPT
    assert "if (data.ok && buttons[index + 1])" in CHAT_SCRIPT


# --- Node-driven test: a minimal stubbed DOM + fetch, running CHAT_SCRIPT for real under node,
# since the two assertions above only prove the gating *fragments* exist in the source text, not
# that the gating actually behaves correctly when real clicks and real (mocked) responses happen.

NODE_SETUP = """
"use strict";

class FakeElement {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.listeners = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.hidden = false;
  }
  appendChild(child) { this.children.push(child); return child; }
  append(...kids) { kids.forEach((kid) => this.children.push(kid)); }
  addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
  dispatch(type, event) {
    // Mirrors real DOM behavior: a disabled element does not receive click events at all -
    // this is what makes "a second click on a disabled/running button sends no request" true.
    if (this.disabled) return Promise.resolve();
    const handlers = this.listeners[type] || [];
    return Promise.all(handlers.map((handler) => handler(event || {})));
  }
  scrollIntoView() {}
}

const elements = {};
["log", "ask", "send", "chat-status", "new-chat"].forEach((id) => { elements[id] = new FakeElement(id); });

global.document = {
  getElementById: (id) => elements[id] || null,
  createElement: (tag) => new FakeElement(tag),
};

let executeCalls = 0;
global.calls = [];
global.fetch = async (url, options) => {
  global.calls.push({url, body: JSON.parse(options.body)});
  if (url === "/api/chat") {
    return {
      ok: true, status: 200, redirected: false,
      json: async () => ({
        session: "s1",
        text: "Here is a plan.",
        plan: {
          summary: "fix it",
          steps: [
            {action: {type: "restart_container", target: "a", command: "atlas restart a"}, rationale: "r1"},
            {action: {type: "restart_container", target: "b", command: "atlas restart b"}, rationale: "r2"},
            {action: {type: "restart_container", target: "c", command: "atlas restart c"}, rationale: "r3"},
          ],
        },
      }),
    };
  }
  if (url === "/api/actions/execute") {
    executeCalls += 1;
    const payload = executeCalls === 1 ? {ok: true, result: {}}
      : executeCalls === 2 ? {ok: false, result: {error: "boom"}}
      : {ok: true, result: {}};
    return {ok: true, status: 200, redirected: false, json: async () => payload};
  }
  throw new Error("unexpected fetch url " + url);
};
"""

# CHAT_SCRIPT is spliced in between NODE_SETUP and NODE_ASSERTIONS: it defines send()/renderSteps()
# at load time (reading the stubbed document from NODE_SETUP), and the assertions below call send()
# directly, so they must run after CHAT_SCRIPT's top-level code has executed.
NODE_ASSERTIONS = """
function check(condition, message) {
  if (!condition) { console.error("FAIL: " + message); process.exit(1); }
}

(async () => {
  elements["ask"].value = "what's wrong with a?";
  await send();

  const log = elements["log"];
  check(log.children.length === 2, "expected a you-bubble and an atlas-bubble, got " + log.children.length);
  const reply = log.children[1];
  const rows = reply.children.filter((child) => child.className === "step");
  check(rows.length === 3, "expected 3 step rows, got " + rows.length);
  const buttons = rows.map((row) => row.children[1]);
  const results = rows.map((row) => row.children[3]);

  check(buttons[0].disabled === false, "step 1 should start enabled");
  check(buttons[1].disabled === true, "step 2 should start disabled");
  check(buttons[2].disabled === true, "step 3 should start disabled");

  // Rapid double-click on step 1 while its own request is still in flight: the second
  // dispatch must be a no-op (disabled flips synchronously before the first await), so
  // only one /api/actions/execute call should ever go out for this click.
  const callsBeforeStep1 = global.calls.length;
  const firstClick = buttons[0].dispatch("click");
  const secondClick = buttons[0].dispatch("click");
  await Promise.all([firstClick, secondClick]);
  check(global.calls.length === callsBeforeStep1 + 1,
    "a disabled/running button must not send a second request, got " + (global.calls.length - callsBeforeStep1) + " calls");
  check(results[0].textContent === "Done.", "step 1 result should say Done., got " + results[0].textContent);
  check(buttons[1].disabled === false, "step 2 should unlock after step 1 succeeds");

  await buttons[1].dispatch("click");
  check(results[1].textContent === "Failed: boom", "step 2 result should surface the failure, got " + results[1].textContent);
  check(buttons[2].disabled === true, "step 3 should stay locked after step 2 fails");

  // Step 3 is still disabled - clicking it must not send a request either.
  const callsBeforeStep3 = global.calls.length;
  await buttons[2].dispatch("click");
  check(global.calls.length === callsBeforeStep3, "a disabled step must not send a request");

  console.log("OK");
  process.exit(0);
})().catch((error) => { console.error("FAIL: " + (error.stack || error)); process.exit(1); });
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_chat_script_step_gating_under_a_real_js_engine():

    script = CHAT_SCRIPT.split("<script>")[1].split("</script>")[0]

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "chat_gating_test.js"
        path.write_text(NODE_SETUP + "\n\n" + script + "\n\n" + NODE_ASSERTIONS)

        result = subprocess.run([shutil.which("node"), str(path)], capture_output=True, text=True, timeout=10)

        assert result.returncode == 0, f"stdout:\\n{result.stdout}\\nstderr:\\n{result.stderr}"
        assert "OK" in result.stdout
