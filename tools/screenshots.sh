#!/bin/bash
# Renders the README/docs screenshots in light and dark from made-up demo data. From the repo root:
#   tools/screenshots.sh
# Needs google-chrome (or CHROME=...) and the dev install (websocket-client drives Chrome over DevTools).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=$PWD/docs/images/screenshots
PY=$PWD/.venv/bin/python; [ -x "$PY" ] || PY=python3
CHROME=${CHROME:-google-chrome}
# three free ports (demo page, degraded page, Chrome DevTools), so another run or service on 18499 never collides
read -r PORT PORT2 DEBUG < <("$PY" -c 'import socket
s = [socket.socket() for _ in range(3)]
[x.bind(("127.0.0.1", 0)) for x in s]
print(*(x.getsockname()[1] for x in s))')
TMP=$(mktemp -d)
PIDS=()
cleanup() { for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done; wait 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

"$PY" tools/demo_data.py "$TMP/demo"
"$PY" tools/demo_data.py "$TMP/degraded" --degraded
( cd "$TMP/demo" && exec "$PY" -m lanxang.cli.main web --port $PORT >/dev/null 2>&1 ) & PIDS+=($!)
( cd "$TMP/degraded" && exec "$PY" -m lanxang.cli.main web --port $PORT2 >/dev/null 2>&1 ) & PIDS+=($!)
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --user-data-dir="$TMP/chrome" \
  --remote-debugging-port=$DEBUG --window-size=1280,800 about:blank >/dev/null 2>&1 & PIDS+=($!)
for url in http://127.0.0.1:$PORT/ http://127.0.0.1:$PORT2/ http://127.0.0.1:$DEBUG/json/version; do
  for _ in $(seq 60); do curl -s -o /dev/null "$url" && continue 2; sleep 0.5; done
  echo "screenshots: no answer from $url after 30 s" >&2; exit 1
done

"$PY" - "$OUT" $PORT $PORT2 $DEBUG <<'EOF'
import base64, json, sys, time, urllib.request
import websocket

out, port, port2, debug = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
target = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{debug}/json")) if t["type"] == "page")
ws = websocket.create_connection(target["webSocketDebuggerUrl"], suppress_origin=True)
ids = iter(range(1, 10**6))

def call(method, **params):
    n = next(ids)
    ws.send(json.dumps({"id": n, "method": method, "params": params}))
    while True:
        reply = json.loads(ws.recv())
        if reply.get("id") == n:
            return reply.get("result", {})

CABLING_DIAGRAM = ('document.querySelector(\'.views button[data-view="diagram"]\').click();'
                   'setTimeout(() => window.scrollTo(0, document.querySelector("#diagram svg").getBoundingClientRect().top + scrollY - 16), 300)')
PICK_PORT = 'var p=[...document.querySelectorAll(".fp .port[data-detail]")].find(c=>c.dataset.detail.includes("pve1")); p && p.click()'
SHOTS = [("home", "/", ""), ("devices", "/devices", ""), ("setup", "/settings", ""), ("coverage", "/coverage", ""), ("overview", "/overview", ""),
         ("cabling-map", "/cabling", CABLING_DIAGRAM), ("cabling-ports", "/cabling", PICK_PORT)]

call("Page.enable")
call("Emulation.setDeviceMetricsOverride", width=1280, height=800, deviceScaleFactor=1, mobile=False)

def shoot(name, url, scheme, script=""):
    # the viewer's saved choice, set before the page loads; light is the default
    sid = call("Page.addScriptToEvaluateOnNewDocument", source=f'try {{ localStorage.clear(); localStorage.setItem("atlas-theme", "{scheme}") }} catch (e) {{}}')["identifier"]
    call("Page.navigate", url=url)
    time.sleep(2)                                         # the cabling diagram lays itself out after load
    if script:
        call("Runtime.evaluate", expression=script)
        time.sleep(1)
    data = call("Page.captureScreenshot", format="png")["data"]
    call("Page.removeScriptToEvaluateOnNewDocument", identifier=sid)
    with open(f"{out}/{name}.png", "wb") as f:
        f.write(base64.b64decode(data))
    print(f"{out}/{name}.png")

for name, path, script in SHOTS:
    for scheme in ("light", "dark"):
        shoot(f"{name}-{scheme}", f"http://127.0.0.1:{port}{path}", scheme, script)
shoot("nas-degraded", f"http://127.0.0.1:{port2}/", "light")
EOF
