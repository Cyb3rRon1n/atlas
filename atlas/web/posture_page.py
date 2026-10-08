"""
/ - the posture page: status strip, zone map (inbound / outbound direct /
outbound via VPN), details panel and public exposure. Markup only here; data
comes from /api/posture via POSTURE_SCRIPT (Task 10).
"""

from atlas.web.render import render_page


POSTURE_STYLE = """
<style>
#strip { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-bottom:16px; }
#strip .chip { padding:14px 16px; background:var(--surface); border:1px solid var(--line); border-radius:12px;
               color:var(--text); text-align:left; font:inherit; cursor:pointer; }
#strip .chip .k { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
#strip .chip .v { font-size:20px; font-weight:600; margin-top:4px; }
#strip .chip .d { font-size:13px; color:var(--muted); }
#strip .chip.ok .v { color:#7fdcb5; } #strip .chip.warn { border-color:var(--red); } #strip .chip.warn .v { color:#ffb4a2; }
#strip .chip.review { border-color:var(--orange); background:#2b2213; } #strip .chip.review .v { color:#ffd08a; }
#strip .chip.unknown .v { color:var(--muted); }
.posture { display:flex; flex-wrap:wrap; gap:20px; }
.posture .mapcard { flex:999 1 720px; min-width:0; background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.posture aside { flex:1 1 320px; min-width:0; display:flex; flex-direction:column; gap:16px; }
.posture aside section { background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.mapbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:12px; }
.mapbar .windows { display:flex; gap:4px; padding:3px; border:1px solid var(--line); border-radius:8px; }
.mapbar .windows button { font:inherit; font-size:13px; padding:8px 12px; border:0; border-radius:6px;
                          background:transparent; color:var(--muted); cursor:pointer; }
.mapbar .windows button[aria-pressed="true"] { background:var(--surface2); color:var(--text); }
.legend { margin-left:auto; display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); }
.legend i { display:inline-block; width:18px; height:3px; margin-right:6px; vertical-align:middle; }
#posture-map { height:560px; border-radius:10px; background:var(--bg); }
#exposure li { display:flex; justify-content:space-between; gap:8px; padding:4px 0; }
.prot-authelia { color:#7fdcb5; } .prot-public { color:#ffd08a; }
@media (max-width: 900px) { #strip { grid-template-columns:repeat(2,minmax(0,1fr)); } #posture-map { height:420px; } }
</style>
"""


def render_posture_page():

    body = (
        POSTURE_STYLE
        + '<section id="strip" aria-label="Posture summary"><p class="muted">Loading...</p></section>'
        + '<div class="posture"><section class="mapcard">'
        + '<div class="mapbar"><h2 style="margin:0;font-size:16px">Network posture</h2>'
        + '<div class="windows" role="group" aria-label="Time window">'
        + '<button data-window="live" aria-pressed="false">Live</button>'
        + '<button data-window="1h" aria-pressed="false">1 h</button>'
        + '<button data-window="24h" aria-pressed="true">24 h</button></div>'
        + '<div class="legend"><span><i style="background:#5aa7f0"></i>Inbound</span>'
        + '<span><i style="background:#8b98a6"></i>Outbound</span>'
        + '<span><i style="background:#43c08f"></i>Via VPN</span>'
        + '<span><i style="background:#f0a23a"></i>New / unreviewed</span></div></div>'
        + '<div id="posture-map" role="img" aria-label="Zone map of inbound, outbound and VPN traffic"></div>'
        + '<p class="muted" id="posture-msg">Click a box for details. Line width = traffic; dashed orange = '
          'a network this container never used before.</p></section>'
        + '<aside><section id="posture-panel"><h2 style="margin:0 0 8px;font-size:15px">Details</h2>'
        + '<p class="muted">Select a destination on the map.</p></section>'
        + '<section><h2 style="margin:0 0 8px;font-size:15px">Public exposure</h2><ul id="exposure" '
          'style="list-style:none;margin:0;padding:0"></ul></section></aside></div>'
        + '<script src="/static/cytoscape.min.js?v=3.34.3"></script>'
    )

    return render_page("Posture", body, active="posture")
