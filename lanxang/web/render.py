"""
Pure HTML-rendering functions for the web view (`lanxang web`).
Every function here takes already-fetched data (from KnowledgeQueries/
data) and returns a plain HTML string - no I/O, no
database access, so these are unit-testable the same way format_change()/
_trend_summary() already are elsewhere in this codebase. These pages are
pure renderers; the write path (device edit/merge/split) lives in api.py
and server.py.
"""

from datetime import datetime, timezone
from html import escape

from lanxang.devices.store import CONNECTIONS, KINDS, STATES
from lanxang.health.alerts import container_state
from lanxang.web.icons import icon
from lanxang.web.blocks import BLOCKS_STYLE
from lanxang.clock import day, hhmm, local, parse, stamp, utcnow
from lanxang.web.chat_assets import CHAT_SCRIPT, CHAT_STYLE, DRAWER_HTML, DRAWER_STYLE


# Colours are tokens: light by default; dark, or the system's choice, when the viewer picks it (the header's theme
# button or Preferences, kept in localStorage). Pages use var(--...) only, never a raw colour.
LIGHT = """--bg:#f7fbf9; --surface:#ffffff; --surface2:#eef5f2; --deep:#e6efeb; --line:#dde8e3; --line2:#c4d4cd;
  --text:#10201c; --muted:#4f5f5a; --blue:#1e7f66; --accent:#1e7f66; --gold:#c9a227; --gold-text:#876808; --on-accent:#ffffff;
  --green:#15803d; --orange:#b45309; --red:#c42b2b; --purple:#7c3aed; --teal:#0f766e; --yellow:#a16207;
  --ok-text:#166534; --ok-line:#86d6a4; --warn-text:#92400e; --warn-line:#f2c97a; --warn-bg:#fff7eb;
  --bad-text:#991b1b; --bad-line:#f3a8a8; --bad-bg:#fef2f2; --lane:#a9d6c7;
  --nav-bg:#0e1a19; --nav-text:#cfe3dc; --nav-muted:#8fb0a6; --nav-on:#16302c; color-scheme:light;"""
DARK = """--bg:#0e1a19; --surface:#13231f; --surface2:#182c27; --deep:#0b1513; --line:#1f3631; --line2:#2a4740;
  --text:#e6f0ec; --muted:#9fb8af; --blue:#5ec2a4; --accent:#5ec2a4; --gold:#e9b44c; --gold-text:#e9b44c; --on-accent:#0e1a19;
  --green:#43c08f; --orange:#f0a23a; --red:#f47a5c; --purple:#b48cf2; --teal:#3ccfb4; --yellow:#d9b44a;
  --ok-text:#7fdcb5; --ok-line:#2f6b55; --warn-text:#ffd08a; --warn-line:#6b5530; --warn-bg:#1d1810;
  --bad-text:#ffb4a2; --bad-line:#6b3030; --bad-bg:#2a1d1a; --lane:#2a5248;
  --nav-bg:#08110f; --nav-text:#cfe3dc; --nav-muted:#8fb0a6; --nav-on:#16302c; color-scheme:dark;"""

# High contrast (Preferences): stronger text and borders, every text colour at least 7:1 on its background.
LIGHT_HC = """--bg:#ffffff; --surface:#ffffff; --surface2:#eef2f1; --deep:#eef2f1; --line:#4a5a55; --line2:#1f2b28;
  --text:#000000; --muted:#26332f; --blue:#0b5a46; --accent:#0b5a46; --on-accent:#ffffff; --gold:#8a6a0c; --gold-text:#5e4700;
  --green:#0b5e2a; --orange:#7a3600; --red:#9e1c1c; --purple:#5b21b6; --teal:#0b5a52; --yellow:#6b5200;
  --ok-text:#0f4a26; --ok-line:#0b5e2a; --warn-text:#6b2e05; --warn-line:#7a3600; --bad-text:#7a1212; --bad-line:#9e1c1c;
  --warn-bg:#fff1dc; --bad-bg:#fde8e8; --nav-text:#ffffff; --nav-muted:#d6e6e0;"""
DARK_HC = """--bg:#000000; --surface:#0a1210; --surface2:#11201c; --deep:#000000; --line:#5f8579; --line2:#9dbfb4;
  --text:#ffffff; --muted:#dbe8e3; --blue:#8fe6cb; --accent:#8fe6cb; --gold:#f5cc70; --gold-text:#f5cc70; --on-accent:#000000;
  --green:#7fe0b0; --orange:#ffc078; --red:#ff9e8a; --purple:#d2b8ff; --teal:#7ff0dc; --yellow:#f2d27a;
  --ok-text:#a8f0d0; --ok-line:#7fe0b0; --warn-text:#ffe0b0; --warn-line:#ffc078; --bad-text:#ffd0c4; --bad-line:#ff9e8a;
  --nav-bg:#000000; --nav-text:#ffffff; --nav-muted:#dbe8e3;"""

# Later rules win at equal specificity: system-dark overrides light high contrast, then [data-contrast] on top.
PAGE_STYLE = f"""
:root {{ {LIGHT} }}
:root[data-theme="dark"] {{ {DARK} }}
:root[data-contrast="on"] {{ {LIGHT_HC} }}
:root[data-theme="dark"][data-contrast="on"] {{ {DARK_HC} }}
@media (prefers-color-scheme: dark) {{
  :root[data-theme="system"] {{ {DARK} }}
  :root[data-theme="system"][data-contrast="on"] {{ {DARK_HC} }}
}}
""" + """
  @font-face { font-family:"Lexend"; src:url("/static/fonts/Lexend.woff2") format("woff2"); font-weight:100 900; font-display:swap; }
  @font-face { font-family:"Noto Sans Lao"; src:url("/static/fonts/NotoSansLao-Medium.woff2") format("woff2"); font-weight:500; font-display:swap; }
  body { font-family: Lexend, system-ui, -apple-system, "Segoe UI", sans-serif; background:var(--bg);
         color:var(--text); margin:0; line-height:1.5; }
  a { color:var(--blue); text-decoration:none; }
  a:hover { text-decoration:underline; }
  h1 { margin:0 0 16px; font-size:1.5rem; font-weight:600; }
  h2 { font-size:1.0625rem; font-weight:600; border-bottom:1px solid var(--line); padding-bottom:0.3rem; }
  table { border-collapse:collapse; width:100%; margin:0.75rem 0 1.5rem; }
  th, td { text-align:left; padding:0.5rem 0.8rem; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; font-size:.75rem; text-transform:uppercase; letter-spacing:.04em;
       background:var(--surface2); }
  .muted { color:var(--muted); }
  .card { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:1rem 1.5rem;
          margin-bottom:1.5rem; }
  code, pre { font-family: ui-monospace, "IBM Plex Mono", Menlo, monospace; background:var(--deep);
              border:1px solid var(--line); border-radius:4px; padding:0.15rem 0.4rem; font-size:0.85rem; }
  pre { padding:0.75rem; overflow-x:auto; white-space:pre-wrap; word-break:break-word; }
  /* One control system: buttons, inputs and selects share a height, border, radius and focus ring. Plain
     <button> is the secondary look; .primary, .danger (destructive) and .btn (a link styled as a button) add to it.
     :where() keeps these at zero specificity, so composite buttons (ports, map boxes, tabs, nav) restyle freely. */
  :root { --control-h:36px; --control-r:6px; }
  :where(button:not(.port, .box, .chip, [role=tab], .side button), .btn) { display:inline-flex; align-items:center;
           justify-content:center; gap:6px; min-height:var(--control-h); box-sizing:border-box; padding:0 14px;
           margin:0; background:var(--surface); color:var(--text); border:1px solid var(--line2);
           border-radius:var(--control-r); font:inherit; font-size:.875rem; line-height:1.2; cursor:pointer;
           text-decoration:none; white-space:nowrap; vertical-align:middle; }
  :where(button, .btn):not(:disabled):hover { border-color:var(--accent); text-decoration:none; }
  .btn { color:var(--text); } .btn:hover { text-decoration:none; }   /* beat the a / a:hover link styles */
  .primary { background:var(--accent); border-color:var(--accent); color:var(--on-accent); font-weight:600; }
  .primary:not(:disabled):hover { background:color-mix(in srgb, var(--accent) 86%, var(--text)); }
  .secondary { background:var(--surface); border-color:var(--line2); color:var(--text); }
  .danger { background:var(--surface); border-color:var(--bad-line); color:var(--bad-text); }
  .danger:not(:disabled):hover { background:var(--red); border-color:var(--red); color:var(--on-accent); }
  :where(button, .btn):disabled, :where(button, .btn)[aria-disabled="true"] { opacity:.55; cursor:not-allowed; }
  .sm { min-height:30px; padding:0 10px; font-size:.8125rem; }   /* compact: table rows, alert rows, suggestion chips */
  :where(input:not([type=checkbox], [type=radio], [type=hidden], [type=range], [type=file], [type=color]), select,
         textarea) { background:var(--surface); color:var(--text); border:1px solid var(--line2);
           border-radius:var(--control-r); padding:0 10px; font:inherit; font-size:.875rem; box-sizing:border-box;
           max-width:100%; }
  :where(input:not([type=checkbox], [type=radio], [type=hidden], [type=range], [type=file], [type=color]), select)
         { min-height:var(--control-h); }
  :where(input, select, textarea):focus-visible { border-color:var(--accent); outline:2px solid var(--accent);
           outline-offset:1px; }
  :where(input, select, textarea):disabled { opacity:.55; cursor:not-allowed; }
  textarea { width:100%; min-height:4rem; padding:8px 10px; }
  .actions { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  /* Segmented control: every time window or view switch. Links (aria-current) or buttons (aria-pressed). */
  .seg { display:inline-flex; flex-wrap:wrap; gap:2px; padding:3px; box-sizing:border-box;
         min-height:var(--control-h); border:1px solid var(--line2); border-radius:8px; background:var(--surface);
         vertical-align:middle; }
  .seg > a, .seg > button { display:inline-flex; align-items:center; min-height:calc(var(--control-h) - 8px);
         padding:0 12px; margin:0; border:0; border-radius:var(--control-r); background:transparent;
         color:var(--muted); font:inherit; font-size:.8125rem; font-weight:500; line-height:1.2; cursor:pointer;
         text-decoration:none; white-space:nowrap; }
  .seg > a:not([aria-current]):hover, .seg > button:not([aria-pressed="true"]):hover { color:var(--text); background:var(--surface2); text-decoration:none; }
  .seg > [aria-current], .seg > [aria-pressed="true"] { background:color-mix(in srgb, var(--accent) 14%, var(--surface));
         color:var(--accent); font-weight:600; }
  /* Empty state: what a page or card shows before it has data, with the one step that fills it. */
  .empty { display:flex; gap:14px; align-items:flex-start; padding:18px 20px; border:1px dashed var(--line2);
           border-radius:10px; background:var(--surface); margin:0 0 16px; }
  .empty > .ic { width:28px; height:28px; margin:2px 0 0; color:var(--accent); }
  .empty p { margin:0 0 4px; font-size:.875rem; } .empty .empty-title { font-size:.9375rem; font-weight:600; color:var(--text); }
  .empty .btn { margin-top:10px; } .empty details { margin-top:10px; font-size:.8125rem; }
  :is(.card, .hcard) .empty { border:0; padding:4px 0 0; margin:0; background:none; }   /* already inside a box */
  label { display:block; margin:0.5rem 0 0.2rem; color:var(--muted); font-size:0.85rem; }
  .ic { width:1.1em; height:1.1em; vertical-align:-0.2em; margin-right:.4em; flex:none; }
  :focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  /* Status is never colour alone: every status dot also carries a glyph (ok ✓, warning !, down ×, unknown –). */
  :root :is(.dot, .ddot) { width:14px; height:14px; border-radius:50%; display:inline-flex; align-items:center;
         justify-content:center; flex:none; color:var(--surface); font:700 10px/1 system-ui, sans-serif; }
  /* The glyph is visual only (alt text ""): the dot's label or row already says the status in words. */
  :is(.dot, .ddot)::after { content:"\\2013"; content:"\\2013" / ""; }
  :is(.dot.ok, .ddot.seen)::after { content:"\\2713"; content:"\\2713" / ""; }
  :is(.dot.warn, .dot.review, .ddot.quiet)::after { content:"!"; content:"!" / ""; }
  .dot.down::after { content:"\\00d7"; content:"\\00d7" / ""; }
  .skip { position:absolute; left:8px; top:-60px; z-index:60; padding:8px 14px; border-radius:6px;
          background:var(--accent); color:var(--on-accent); font-weight:600; }
  .skip:focus { top:8px; text-decoration:none; }
  main:focus { outline:none; }
  kbd { font:600 .75rem ui-monospace, Menlo, monospace; padding:1px 6px; border:1px solid var(--line2);
        border-bottom-width:2px; border-radius:4px; background:var(--surface2); color:var(--text); }
  .status-seen { color:var(--green); } .status-quiet { color:var(--orange); } .status-invisible { color:var(--muted); }
  time[data-when] { white-space:nowrap; }
  #msg { color:var(--red); min-height:1.2rem; } #msg:empty { display:none; }
  .table-wrap { overflow-x:auto; max-width:100%; } .table-wrap > table { margin-top:0; }
  input.wide { width:100%; max-width:26rem; box-sizing:border-box; }
"""

SHELL_STYLE = """
.app { display:flex; min-height:100vh; }
.side { flex:0 0 224px; box-sizing:border-box; background:var(--nav-bg); padding:18px 12px; display:flex;
        flex-direction:column; gap:2px; position:sticky; top:0; height:100vh; overflow-y:auto; }
.side a, .side button { display:block; width:100%; box-sizing:border-box; text-align:left; padding:8px 14px; margin:0;
        border:0; border-radius:6px; background:none; color:var(--nav-text); font:inherit; font-size:.875rem;
        text-decoration:none; cursor:pointer; }
.side a:hover, .side button:hover { background:var(--nav-on); text-decoration:none; }
.side .brand { display:flex; align-items:center; gap:10px; padding:4px 14px 18px; color:#fff; font-weight:700;
        font-size:1.0625rem; }
.side .brand:hover { background:none; }
.side .brand .name { display:flex; flex-direction:column; line-height:1.1; }
.side .brand small { font:500 .6875rem "Noto Sans Lao", sans-serif; color:var(--gold); }
.side ul { list-style:none; margin:0; padding:0; }
.side nav.main > ul > li > a[aria-current="page"] { background:var(--nav-on); color:#fff; font-weight:600; }
.side .tabs a { padding:6px 14px 6px 30px; font-size:.8125rem; color:var(--nav-muted); }
.side .tabs a[aria-current="page"] { color:#fff; font-weight:600; box-shadow:inset 2px 0 0 var(--accent); background:none; }
.side .foot { margin-top:auto; padding-top:16px; }
.side .foot form { margin:0; }
.page { padding:24px 32px 40px; min-width:0; }
/* Header bar: the quick theme button and Preferences, top right of every page (in the top bar on phones). */
.app { position:relative; }
.page-head { padding-right:90px; }   /* room for the header bar, which sits over the page's top right corner */
.page-head h1 { min-width:0; }
.hbar { display:flex; gap:6px; flex:none; }
.app > .hbar { position:absolute; top:20px; right:32px; z-index:5; }
body:has(.shell.docked) .app > .hbar { right:calc(380px + 32px); }
body.chat-collapsed:has(.shell.docked) .app > .hbar { right:calc(44px + 32px); }
.hbar .icon-btn { min-width:var(--control-h); padding:0; } .hbar .ic { margin:0; width:18px; height:18px; }
.side .hbar, .subnav { display:none; }
.theme-cycle .t-dark, .theme-cycle .t-system { display:none; }
:root[data-theme="dark"] .theme-cycle .t-light, :root[data-theme="system"] .theme-cycle .t-light { display:none; }
:root[data-theme="dark"] .theme-cycle .t-dark, :root[data-theme="system"] .theme-cycle .t-system { display:inline; }
/* Preferences: a right-side panel over the page. */
.prefs-back { position:fixed; inset:0; background:rgb(0 0 0 / .4); z-index:30; }
.prefs { position:fixed; top:0; right:0; bottom:0; width:min(400px, 100vw); box-sizing:border-box; z-index:31;
         overflow-y:auto; background:var(--surface); border-left:1px solid var(--line2); padding:18px 22px 28px;
         box-shadow:-8px 0 24px rgb(0 0 0 / .18); }
.prefs[hidden], .prefs-back[hidden], .keys[hidden] { display:none; }
/* Keyboard shortcuts sheet (press ?): a small dialog in the middle of the window. */
.keys { position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); width:min(380px, calc(100vw - 32px));
        box-sizing:border-box; z-index:31; background:var(--surface); border:1px solid var(--line2); border-radius:10px;
        padding:18px 22px 20px; box-shadow:0 12px 32px rgb(0 0 0 / .22); max-height:calc(100vh - 32px); overflow-y:auto; }
.keys dl { display:grid; grid-template-columns:auto 1fr; gap:8px 16px; margin:14px 0 0; font-size:.875rem; }
.keys dt { white-space:nowrap; } .keys dd { margin:0; }
.prefs-head { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.prefs-head h2 { margin:0; border:0; padding:0; font-size:1.125rem; }
.prefs h3 { margin:22px 0 4px; font-size:.75rem; font-weight:600; text-transform:uppercase; letter-spacing:.05em;
            color:var(--muted); }
.pref { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:6px 12px; padding:8px 0;
        border-bottom:1px solid var(--line); }
.pref > span, .pref > label { margin:0; color:var(--text); font-size:.875rem; }
.pref .hint { flex:1 1 100%; margin:0; color:var(--muted); font-size:.8125rem; }
/* Preferences: each one is a data-* attribute on <html>, set before first paint by THEME_SCRIPT. */
:root[data-text="s"] { font-size:87.5%; } :root[data-text="l"] { font-size:112.5%; }
:root[data-density="compact"] { --control-h:30px; }
:root[data-density="compact"] :is(th, td) { padding:.25rem .6rem; }
:root[data-density="compact"] .card { padding:.6rem 1rem; margin-bottom:1rem; }
:root[data-density="compact"] .page { padding:16px 24px 28px; }
:root[data-motion="on"] *, :root[data-motion="on"] ::before, :root[data-motion="on"] ::after {
  animation:none !important; transition:none !important; scroll-behavior:auto !important; }
@media (prefers-reduced-motion: reduce) {
  :root:not([data-motion="off"]) *, :root:not([data-motion="off"]) ::before, :root:not([data-motion="off"]) ::after {
    animation:none !important; transition:none !important; scroll-behavior:auto !important; }
}
.side-toggle .ic { transition:transform .15s; }
@media (min-width: 901px) {   /* collapsed sidebar: icons only; labels stay for screen readers, titles as tooltips */
  :root[data-sidebar="on"] .side { flex-basis:64px; padding:18px 8px; }
  :root[data-sidebar="on"] .side .lbl, :root[data-sidebar="on"] .side .brand .name { position:absolute; width:1px;
    height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
  :root[data-sidebar="on"] .side .tabs { display:none; }
  :root[data-sidebar="on"] .side :is(a, button) { padding:9px 0; text-align:center; }
  :root[data-sidebar="on"] .side .ic { margin:0; width:20px; height:20px; }
  :root[data-sidebar="on"] .side .brand { justify-content:center; padding:4px 0 18px; }
  :root[data-sidebar="on"] .side-toggle .ic { transform:scaleX(-1); }
  :root[data-sidebar="on"] .subnav { display:block; margin:-4px 0 16px; }
}
.shell { flex:1; min-width:0; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 16px; }
.chips button { font:inherit; font-size:.8125rem; min-height:32px; padding:4px 12px; border-radius:999px; margin:0;
                white-space:normal; text-align:left; }
@media (max-width: 900px) {
  .app { display:block; }
  .side { padding:10px 12px; flex-direction:row; flex-wrap:wrap; align-items:center; gap:4px; }
  .side .brand { padding:6px 10px; }
  .side nav.main { flex:1 1 100%; order:3; }
  .side nav.main > ul { display:flex; flex-wrap:wrap; gap:2px; }
  .side nav.main > ul > li { display:contents; }
  .side a, .side button { width:auto; }
  .side .tabs { flex:1 1 100%; order:5; display:flex; flex-wrap:wrap; }
  .side .tabs a { padding:6px 12px; }
  .side .foot { margin:0 0 0 auto; padding:0; display:flex; flex-wrap:wrap; align-items:center; order:2; }
  .side { position:static; height:auto; overflow:visible; }
  .side .hbar { display:flex; gap:2px; } .app > .hbar, .side .side-toggle { display:none; }
  .page-head { padding-right:0; }
  .page { padding:16px; }
}
"""

PAGE_STYLE += SHELL_STYLE

# Runs in <head> before first paint, so no saved choice ever flashes. Light is the default whatever the OS prefers;
# the OS colour scheme counts only when the viewer picked "system". Each preference becomes a data-* attribute on
# <html> that PAGE_STYLE keys on; a missing or blocked localStorage just means the defaults. Start page: opening /
# directly goes to the chosen page; the Home link (/?home) and reloads or back/forward stay on Home.
THEME_SCRIPT = """<script>(function(){var d=document.documentElement;
function g(k){try{return localStorage.getItem(k);}catch(e){return null;}}
var t=g("atlas-theme");if(t==="light"||t==="dark"||t==="system")d.dataset.theme=t;
try{document.cookie="lanxang-tz="+encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)+";path=/;max-age=31536000;samesite=lax";}catch(e){}
var V={motion:["on","off"],contrast:["on"],text:["s","l"],density:["compact"],sidebar:["on"]};
for(var k in V){var v=g("lanxang-pref-"+k);if(V[k].indexOf(v)>=0)d.setAttribute("data-"+k,v);}
window.lanxangReduced=function(){var m=d.getAttribute("data-motion");
return m==="on"||(m!=="off"&&!!window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches);};
if(location.pathname!=="/")return;
if(/[?&]home(=|&|$)/.test(location.search)){try{history.replaceState(null,"","/");}catch(e){}return;}
var s={devices:"/devices",alerts:"/alerts",map:"/cabling",servers:"/overview",security:"/posture"}[g("lanxang-pref-start")];
var n=window.performance&&performance.getEntriesByType?performance.getEntriesByType("navigation")[0]:null;
if(s&&(!n||n.type==="navigate"))location.replace(s);})();</script>"""

# Last in <body>: the header buttons, the Preferences panel and the sidebar toggle. Every change applies at once.
PREFS_SCRIPT = """<script>(function(){
var d=document.documentElement,panel=document.getElementById("prefs"),back=document.getElementById("prefs-back"),opener=null;
var DEF={theme:"light",motion:"system",contrast:"off",text:"m",density:"comfortable",start:"home",sidebar:"off"};
var START=["home","devices","alerts","map","servers","security"];
var NEXT={light:"dark",dark:"system",system:"light"},NAME={light:"Light",dark:"Dark",system:"System"};
function key(k){return k==="theme"?"atlas-theme":"lanxang-pref-"+k;}
function get(k){if(k==="theme")return NAME[d.dataset.theme]?d.dataset.theme:"light";
  if(k==="start"){var v=null;try{v=localStorage.getItem(key(k));}catch(e){}return START.indexOf(v)>=0?v:"home";}
  return d.getAttribute("data-"+k)||DEF[k];}
function set(k,v){
  if(k==="theme")d.dataset.theme=v;else if(k!=="start"){if(v===DEF[k])d.removeAttribute("data-"+k);else d.setAttribute("data-"+k,v);}
  try{localStorage.setItem(key(k),v);}catch(e){}
  sync();}
function sync(){
  document.querySelectorAll("[data-pref]").forEach(function(c){var v=get(c.dataset.pref);
    if(c.tagName==="SELECT")c.value=v;else c.querySelectorAll("button").forEach(function(b){b.setAttribute("aria-pressed",String(b.dataset.v===v));});});
  var t=get("theme");
  document.querySelectorAll(".theme-cycle").forEach(function(b){b.setAttribute("aria-label","Theme: "+NAME[t]+". Switch to "+NAME[NEXT[t]]);b.title="Theme: "+NAME[t];});
  var c=get("sidebar")==="on",say=c?"Expand sidebar":"Collapse sidebar";
  document.querySelectorAll(".side-toggle").forEach(function(b){b.setAttribute("aria-pressed",String(c));b.title=say;b.querySelector(".lbl").textContent=say;});}
window.atlasTheme=function(){set("theme",NEXT[get("theme")]);};
function show(b){opener=b;panel.hidden=back.hidden=false;var app=document.querySelector(".app");if(app)app.inert=true;sync();panel.focus();}
function hide(){panel.hidden=back.hidden=true;var app=document.querySelector(".app");if(app)app.inert=false;if(opener)opener.focus();}
document.addEventListener("click",function(e){var b=e.target.closest("[data-pref] button");
  if(b)set(b.parentNode.dataset.pref,b.dataset.v);
  else if(e.target.closest(".prefs-open"))show(e.target.closest(".prefs-open"));
  else if(e.target.closest("[data-prefs-close]")||e.target===back)hide();
  else if(e.target.closest(".side-toggle"))set("sidebar",get("sidebar")==="on"?"off":"on");});
document.addEventListener("change",function(e){if(e.target.matches("select[data-pref]"))set(e.target.dataset.pref,e.target.value);});
document.addEventListener("keydown",function(e){if(panel.hidden)return;
  if(e.key==="Escape"){e.preventDefault();hide();return;}
  if(e.key!=="Tab")return;
  var f=[].filter.call(panel.querySelectorAll("button,select,a[href],input"),function(x){return x.offsetParent!==null;});
  var a=document.activeElement;
  if(e.shiftKey&&(a===f[0]||a===panel||!panel.contains(a))){e.preventDefault();f[f.length-1].focus();}
  else if(!e.shiftKey&&(a===f[f.length-1]||!panel.contains(a))){e.preventDefault();f[0].focus();}});
sync();})();</script>"""


# Time & date: saved on the server (POST /api/settings/display/save, the same gated write path as Setup), then put
# on <html> for TIME_SCRIPT and applied without a reload.
TIME_PREFS_SCRIPT = """<script>(function(){
var R=document.documentElement,row=document.getElementById("pref-zone-row"),box=document.getElementById("pref-zone"),
  say=document.getElementById("pref-time-status"),other=false;
function cur(){return{clock:R.dataset.clock||"24h",date_format:R.dataset.datefmt||"iso",time_zone:R.dataset.tz||"browser"};}
function sync(){var c=cur(),z=other||(c.time_zone!=="browser"&&c.time_zone!=="UTC")?"other":c.time_zone,v={clock:c.clock,date_format:c.date_format,zone:z};
  document.querySelectorAll("[data-spref]").forEach(function(g){g.querySelectorAll("button").forEach(function(b){
    b.setAttribute("aria-pressed",String(b.dataset.v===v[g.dataset.spref]));});});
  row.hidden=z!=="other";if(z==="other"&&document.activeElement!==box&&c.time_zone!=="UTC"&&c.time_zone!=="browser")box.value=c.time_zone;}
function save(change){var body=cur();for(var k in change)body[k]=change[k];say.textContent="Saving...";
  fetch("/api/settings/display/save",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)}).then(function(r){return r.json().then(function(j){return[r.ok,j];});}).then(function(a){
    if(!a[0]){say.textContent=a[1].error||"Couldn't save.";return;}
    var s=a[1].display;R.dataset.clock=s.clock;R.dataset.datefmt=s.date_format;R.dataset.tz=s.time_zone;other=false;
    if(window.atlasTimes)window.atlasTimes();sync();say.textContent="Saved.";
    if(document.getElementById("ev-log"))location.reload();},function(){say.textContent="Couldn't reach Lanxang.";});}
document.addEventListener("click",function(e){var b=e.target.closest("[data-spref] button");if(!b)return;
  var k=b.parentNode.dataset.spref,v=b.dataset.v;
  if(k!=="zone")save(k==="clock"?{clock:v}:{date_format:v});
  else if(v==="other"){other=true;sync();box.focus();}
  else{other=false;save({time_zone:v});}});
box.addEventListener("change",function(){if(box.value.trim())save({time_zone:box.value.trim()});});
box.addEventListener("keydown",function(e){if(e.key==="Enter"){e.preventDefault();e.stopPropagation();if(box.value.trim())save({time_zone:box.value.trim()});}});
box.addEventListener("focus",function(){var l=document.getElementById("pref-zones");if(l.options.length||!Intl.supportedValuesOf)return;
  l.innerHTML=Intl.supportedValuesOf("timeZone").map(function(z){return '<option value="'+z+'">';}).join("");},{once:true});
sync();})();</script>"""


LOGO = ('<svg width="26" height="26" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10.4" stroke="#5ec2a4" stroke-width="1.8" fill="none"/><g transform="translate(4.8 4.8) scale(.6)"><g transform="translate(1.2 2.6) scale(.9)"><path d="M3 6.6C3 4.9 4.2 4 6 4h2.6v9.8C6.4 13.8 4.9 13.2 4 12.1 3.3 11.2 3 10 3 8.8z" fill="#5ec2a4"/><path d="M21 6.6C21 4.9 19.8 4 18 4h-2.6v9.8c2.2 0 3.7-.6 4.6-1.7.7-.9 1-2.1 1-3.3z" fill="#5ec2a4"/><path d="M8.2 5.2C9.3 3.9 10.6 3.3 12 3.3s2.7.6 3.8 1.9v8.1c0 1.3-.8 2.2-2 2.5l-.6 5.1c-.1.8-.6 1.2-1.2 1.2s-1.1-.4-1.2-1.2l-.6-5.1c-1.2-.3-2-1.2-2-2.5z" fill="#5ec2a4"/><circle cx="10.2" cy="8.6" r=".95" fill="#0e1a19"/><circle cx="13.8" cy="8.6" r=".95" fill="#0e1a19"/></g><g transform="translate(9 -.6) scale(.25)"><path d="M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z" fill="#e9b44c" transform="rotate(0 12 12)"/><path d="M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z" fill="#e9b44c" transform="rotate(72 12 12)"/><path d="M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z" fill="#e9b44c" transform="rotate(144 12 12)"/><path d="M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z" fill="#e9b44c" transform="rotate(216 12 12)"/><path d="M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z" fill="#e9b44c" transform="rotate(288 12 12)"/><circle cx="12" cy="12" r="2.6" fill="#e9b44c" stroke="#0e1a19" stroke-width=".7"/></g></g></svg>')



def logo(size=26, light=False):
    """The mark at any size; light: the favicon's darker jade and gold, for a light background."""

    svg = LOGO.replace('width="26" height="26"', f'width="{size}" height="{size}"')
    if light:
        svg = svg.replace("#5ec2a4", "#1e7f66").replace("#e9b44c", "#c9a227").replace("#0e1a19", "#f7fbf9")
    return svg


def _esc(value):
    return escape(str(value))


def _moment(value):
    """A stored time (naive UTC datetime, or its ISO text) as a datetime; None when there is none or it won't parse."""

    return parse(value)


def friendly_time(moment, now, clock=False, display=None):
    """The server's wording for a naive-UTC time, in the display: settings (DISPLAY by default): '5 min ago',
    'today 14:32 UTC', 'yesterday 2:32 PM EST', 'Mon 14:32 UTC', then the date ('2026-11-12', '11/12/2026').
    TIME_SCRIPT redoes the same in the viewer's zone (or the chosen one); this is what shows without it.
    clock: just the time and zone (rows already grouped by day); clock="day": 'Today', 'Yesterday', 'Mon 2026-11-16'."""

    display = display or DISPLAY
    here, zone = local(moment, display)
    days = (local(now, display)[0].date() - here.date()).days
    if clock == "day":
        return "Today" if days == 0 else "Yesterday" if days == 1 else f"{here:%a} {day(here, display)}"
    if clock:
        return f"{hhmm(here, display)} {zone}"
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 6 * 60:
        return f"{minutes // 60} h ago"
    if days == 0:
        return f"today {hhmm(here, display)} {zone}"
    if days == 1:
        return f"yesterday {hhmm(here, display)} {zone}"
    if days < 7:
        return f"{here:%a} {hhmm(here, display)} {zone}"
    return day(here, display)


def when(value, now=None, clock=False, never="-", text=None):
    """One time on any page: <time datetime="...Z"> with friendly_time() inside, which TIME_SCRIPT rewrites in the
    viewer's local time (or the chosen zone). never: what to show when there is no time; text: other server-side words."""

    moment = _moment(value)
    if moment is None:
        return _esc(value) if value else _esc(never)
    iso = moment.isoformat(timespec="seconds")
    mode = "day" if clock == "day" else "clock" if clock else "rel"
    shown = text if text is not None else friendly_time(moment, now or utcnow(), clock)
    return f'<time datetime="{iso}Z" data-when="{mode}" title="{_esc(stamp(moment, DISPLAY))}">{_esc(shown)}</time>'


# Last in <body>, so it runs at once. Turns every <time data-when> into the same words as friendly_time(), in the
# viewer's own time zone or the one chosen in Preferences (<html data-tz/data-clock/data-datefmt>); refreshes each minute.
TIME_SCRIPT = """<script>(function(){
var R=document.documentElement,D=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
var two=function(n){return (n<10?"0":"")+n;},fmt,tz;
function parts(d){if(!fmt)return{y:d.getFullYear(),m:d.getMonth()+1,d:d.getDate(),h:d.getHours(),i:d.getMinutes(),w:d.getDay()};
  var o={};fmt.formatToParts(d).forEach(function(p){o[p.type]=p.value;});
  return{y:+o.year,m:+o.month,d:+o.day,h:+o.hour%24,i:+o.minute,w:D.indexOf(o.weekday)};}
function hm(p){return R.dataset.clock==="12h"?((p.h%12)||12)+":"+two(p.i)+" "+(p.h<12?"AM":"PM"):two(p.h)+":"+two(p.i);}
function ymd(p){var f=R.dataset.datefmt;return f==="dmy"?two(p.d)+"/"+two(p.m)+"/"+p.y:f==="mdy"?two(p.m)+"/"+two(p.d)+"/"+p.y:p.y+"-"+two(p.m)+"-"+two(p.d);}
function say(d,now,mode){
  var p=parts(d),q=parts(now),days=Math.round((Date.UTC(q.y,q.m-1,q.d)-Date.UTC(p.y,p.m-1,p.d))/86400000),min=Math.floor((now-d)/60000);
  if(mode==="clock")return hm(p);
  if(mode==="day")return days===0?"Today":days===1?"Yesterday":D[p.w]+" "+ymd(p);
  if(min<1)return "just now";
  if(min<60)return min+" min ago";
  if(min<360)return Math.floor(min/60)+" h ago";
  if(days===0)return "today "+hm(p);
  if(days===1)return "yesterday "+hm(p);
  if(days<7)return D[p.w]+" "+hm(p);
  return ymd(p);
}
function run(){var now=new Date(),z=R.dataset.tz||"browser";
  if(z!==tz){tz=z;fmt=null;if(z!=="browser")try{fmt=new Intl.DateTimeFormat("en-US",{timeZone:z,year:"numeric",month:"numeric",
    day:"numeric",hour:"numeric",minute:"numeric",weekday:"short",hourCycle:"h23"});}catch(e){fmt=null;}}
  document.querySelectorAll("time[data-when]").forEach(function(t){
  var d=new Date(t.getAttribute("datetime"));if(isNaN(d))return;var p=parts(d);
  t.textContent=say(d,now,t.dataset.when);t.title=ymd(p)+" "+hm(p)+(fmt?" "+tz:"");});}
window.atlasTimes=run;
run();
setInterval(run,60000);})();</script>"""


NAV = [("/", "Home", "home"), ("/alerts", "Alerts", "alerts"), ("/devices", "Network", "network"),
       ("/overview", "Servers", "servers"), ("/posture", "Security", "security"), ("/settings", "Setup", "settings")]

# Each top tab's pages, shown as a strip under the title. A page names itself (render_page active=); the strip and
# the highlighted top tab follow from this table. Old addresses (/posture, /map, /history...) all still work.
SECTIONS = {
    "alerts": [("/alerts", "Alerts", "alerts"), ("/history", "Activity", "history")],
    "network": [("/devices", "Devices", "devices"), ("/triage", "Triage", "triage"), ("/coverage", "Coverage", "coverage"),
                ("/cabling", "Cabling", "cabling")],
    "servers": [("/overview", "Overview", "hosts"), ("/trends", "Trends", "trends"), ("/uptime", "Uptime", "uptime")],
    "security": [("/posture", "Exposure", "posture"), ("/map", "Services", "lan"), ("/access", "Visitors", "access")],
}
SECTION_OF = {page: section for section, pages in SECTIONS.items() for _, _, page in pages}


def section_tabs(page):
    """The sub-tab strip for a page: [(href, label, is_current)]."""

    return [(href, label, key == page) for href, label, key in SECTIONS.get(SECTION_OF.get(page), [])]

SIGN_OUT = False    # set by run_server when atlas does its own sign-in (web.auth: builtin)
AI_ON = True        # set per request by the server: no chat panel or "ask" chips while intelligence.provider is none
DISPLAY = None      # set per request by the server: the display: settings (clock, time zone, date format); None = defaults

def _hosts_tabs(current):

    return section_tabs("trends" if current == "/trends" else "hosts")


# The Lanxang mark (light variant) as the browser-tab icon, inline: no extra request, no 404 for /favicon.ico.
FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
           "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='10.4' stroke='%231e7f66' stroke-width='1.8' fill='none'/%3E%3Cg transform='translate(4.8 4.8) scale(.6)'%3E%3Cg transform='translate(1.2 2.6) scale(.9)'%3E%3Cpath d='M3 6.6C3 4.9 4.2 4 6 4h2.6v9.8C6.4 13.8 4.9 13.2 4 12.1 3.3 11.2 3 10 3 8.8z' fill='%231e7f66'/%3E%3Cpath d='M21 6.6C21 4.9 19.8 4 18 4h-2.6v9.8c2.2 0 3.7-.6 4.6-1.7.7-.9 1-2.1 1-3.3z' fill='%231e7f66'/%3E%3Cpath d='M8.2 5.2C9.3 3.9 10.6 3.3 12 3.3s2.7.6 3.8 1.9v8.1c0 1.3-.8 2.2-2 2.5l-.6 5.1c-.1.8-.6 1.2-1.2 1.2s-1.1-.4-1.2-1.2l-.6-5.1c-1.2-.3-2-1.2-2-2.5z' fill='%231e7f66'/%3E%3Ccircle cx='10.2' cy='8.6' r='.95' fill='%23f7fbf9'/%3E%3Ccircle cx='13.8' cy='8.6' r='.95' fill='%23f7fbf9'/%3E%3C/g%3E%3Cg transform='translate(9 -.6) scale(.25)'%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(0 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(72 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(144 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(216 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(288 12 12)'/%3E%3Ccircle cx='12' cy='12' r='2.6' fill='%23c9a227' stroke='%23f7fbf9' stroke-width='.7'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E\">")


def _choice(pref, label, options, hint="", default=None, attr="data-pref"):
    """One Preferences row: a .seg of buttons (aria-pressed) for pref; options are (value, text), default the first.
    attr: data-pref (this browser, PREFS_SCRIPT) or data-spref (saved on the server, TIME_PREFS_SCRIPT)."""

    default = default or options[0][0]
    buttons = "".join(f'<button type="button" data-v="{v}" aria-pressed="{str(v == default).lower()}">{_esc(text)}</button>'
                      for v, text in options)
    note = f'<p class="hint">{_esc(hint)}</p>' if hint else ""
    return (f'<div class="pref"><span id="pl-{pref}">{_esc(label)}</span>'
            f'<div class="seg" role="group" aria-labelledby="pl-{pref}" {attr}="{pref}">{buttons}</div>{note}</div>')


START_PAGES = (("home", "Home"), ("devices", "Devices"), ("alerts", "Alerts"), ("map", "Network map"),
               ("servers", "Servers"), ("security", "Security"))

PREFS_PANEL = (
    '<div id="prefs-back" class="prefs-back" hidden></div>'
    '<div id="prefs" class="prefs" role="dialog" aria-modal="true" aria-labelledby="prefs-title" tabindex="-1" hidden>'
    '<div class="prefs-head"><h2 id="prefs-title">Preferences</h2>'
    '<button type="button" class="sm" data-prefs-close>Close</button></div>'
    '<p class="muted" style="margin:6px 0 0;font-size:.8125rem">Saved in this browser only, except Time &amp; date. Changes apply at once.</p>'
    '<h3>Appearance</h3>'
    + _choice("theme", "Theme", (("light", "Light"), ("dark", "Dark"), ("system", "System")))
    + _choice("motion", "Reduced motion", (("system", "System"), ("on", "On"), ("off", "Off")),
              "System follows your device's setting.")
    + _choice("contrast", "High contrast", (("off", "Off"), ("on", "On")))
    + '<h3>Time &amp; date</h3>'
    '<p class="hint" style="margin:0;color:var(--muted);font-size:.8125rem">Saved for everyone, on every page and in '
    'alert messages and the weekly summary.</p>'
    + _choice("clock", "Clock", (("24h", "24-hour"), ("12h", "12-hour")), attr="data-spref")
    + _choice("date_format", "Date format", (("iso", "2026-11-19"), ("dmy", "19/11/2026"), ("mdy", "11/19/2026")),
              attr="data-spref")
    + _choice("zone", "Time zone", (("browser", "This browser"), ("UTC", "UTC"), ("other", "Other")),
              "This browser: each viewer sees their own time; alert messages then use UTC.", attr="data-spref")
    + '<div class="pref" id="pref-zone-row" hidden><label for="pref-zone">Zone name</label>'
    '<input id="pref-zone" list="pref-zones" placeholder="America/New_York" autocomplete="off" spellcheck="false">'
    '<datalist id="pref-zones"></datalist><p class="hint">An IANA name; press Enter to save.</p></div>'
    '<p id="pref-time-status" class="muted" role="status" aria-live="polite" style="font-size:.8125rem;min-height:1.2em;margin:6px 0 0"></p>'
    + '<h3>Size &amp; density</h3>'
    + _choice("text", "Text size", (("s", "S"), ("m", "M"), ("l", "L")), default="m")
    + _choice("density", "Density", (("comfortable", "Comfortable"), ("compact", "Compact")))
    + '<h3>Navigation</h3>'
    '<div class="pref"><label for="pref-start">Start page</label><select id="pref-start" data-pref="start">'
    + "".join(f'<option value="{v}">{_esc(t)}</option>' for v, t in START_PAGES)
    + '</select><p class="hint">Where Lanxang opens when you visit its address. The Home link still goes to Home.</p></div>'
    + _choice("sidebar", "Collapsed sidebar", (("off", "Off"), ("on", "On")), "Icons only, on wide screens.")
    + '<div class="pref"><span>Keyboard shortcuts — press <kbd>?</kbd></span>'
    '<p class="hint"><kbd>g</kbd> <kbd>h</kbd> Home, <kbd>g</kbd> <kbd>d</kbd> Devices, <kbd>g</kbd> <kbd>a</kbd> Alerts, '
    '<kbd>g</kbd> <kbd>s</kbd> Setup, <kbd>/</kbd> search.</p></div>'
    + '</div>'
)

# Keyboard shortcuts: (keys, what). The sheet (press ?) and KEYS_SCRIPT both follow this table.
SHORTCUTS = ((("g", "h"), "Home"), (("g", "d"), "Devices"), (("g", "a"), "Alerts"), (("g", "s"), "Setup"),
             (("/",), "Focus the search box (where there is one)"), (("?",), "Show this list"), (("Esc",), "Close it"))

KEYS_SHEET = (
    '<div id="keys-back" class="prefs-back" hidden></div>'
    '<div id="keys" class="keys" role="dialog" aria-modal="true" aria-labelledby="keys-title" tabindex="-1" hidden>'
    '<div class="prefs-head"><h2 id="keys-title">Keyboard shortcuts</h2>'
    '<button type="button" class="sm" data-keys-close>Close</button></div><dl>'
    + "".join(f'<dt>{" ".join(f"<kbd>{_esc(k)}</kbd>" for k in keys)}</dt><dd>{_esc(what)}</dd>' for keys, what in SHORTCUTS)
    + '</dl><p class="muted" style="margin:12px 0 0;font-size:.8125rem">Not while typing in a field.</p></div>'
)

# Last in <body>. g then a letter goes to a page, / focuses the page's search box, ? opens the sheet. Nothing fires
# while typing in a field, with Ctrl/Alt/Cmd held, or while Preferences is open.
KEYS_SCRIPT = """<script>(function(){
var GO={h:"/?home",d:"/devices",a:"/alerts",s:"/settings"},sheet=document.getElementById("keys"),
  back=document.getElementById("keys-back"),prefs=document.getElementById("prefs"),g=0,opener=null;
function typing(t){return !!t&&(t.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));}
function app(on){var a=document.querySelector(".app");if(a)a.inert=on;}
function open(){opener=document.activeElement;sheet.hidden=back.hidden=false;app(true);sheet.focus();}
function close(){sheet.hidden=back.hidden=true;app(false);if(opener&&opener.focus)opener.focus();}
document.addEventListener("click",function(e){if(e.target.closest("[data-keys-close]")||e.target===back)close();});
document.addEventListener("keydown",function(e){
  if(!sheet.hidden){if(e.key==="Escape"||e.key==="?"){e.preventDefault();close();}
    else if(e.key==="Tab"){e.preventDefault();sheet.querySelector("[data-keys-close]").focus();}return;}
  if(e.defaultPrevented||e.ctrlKey||e.metaKey||e.altKey||typing(e.target)||(prefs&&!prefs.hidden))return;
  var was=g;g=0;
  if(was&&Date.now()-was<1500&&GO[e.key]){e.preventDefault();location.href=GO[e.key];return;}
  if(e.key==="g"){g=Date.now();return;}
  if(e.key==="/"){var f=document.querySelector("main input[type=search]");if(f){e.preventDefault();f.focus();f.select();}return;}
  if(e.key==="?"){e.preventDefault();open();}});
})();</script>"""

NAV_ICONS = {"home": "home", "alerts": "alert", "network": "network", "servers": "server", "security": "shield",
             "settings": "tool"}

# Rendered twice (page header; phone top bar), so classes, not ids. The theme icon follows data-theme from CSS.
HEADER_BAR = (
    '<div class="hbar"><button type="button" class="icon-btn theme-cycle" onclick="atlasTheme()" '
    'aria-label="Theme: Light. Switch to Dark" title="Theme: Light">'
    f'<span class="t-light">{icon("sun")}</span><span class="t-dark">{icon("moon")}</span>'
    f'<span class="t-system">{icon("monitor")}</span></button>'
    '<button type="button" class="icon-btn prefs-open" aria-haspopup="dialog" aria-controls="prefs" '
    f'aria-label="Preferences" title="Preferences">{icon("gear")}</button></div>'
)


def _display_attrs():
    """The display: settings on <html>, read by TIME_SCRIPT and the Preferences panel."""

    clock, zone, dates = (DISPLAY.clock, DISPLAY.time_zone, DISPLAY.date_format) if DISPLAY else ("24h", "browser", "iso")
    return f' data-clock="{_esc(clock)}" data-datefmt="{_esc(dates)}" data-tz="{_esc(zone)}"'


def render_page(title, body_html, active="", tabs=None, drawer=True, heading=None):
    """heading: the visible headline when it should say more than the tab title (Home's verdict)."""

    drawer = drawer and AI_ON

    here = ' aria-current="page"'   # built outside the f-strings: backslashes in f-string expressions need 3.12
    tabs = tabs if tabs is not None else section_tabs(active)
    sub = ""
    if tabs:
        sub = '<ul class="tabs" aria-label="Section">' + "".join(
            f'<li><a href="{href}"{here if current else ""}>{_esc(label)}</a></li>' for href, label, current in tabs) + "</ul>"
    items = []
    for href, label, key in NAV:
        on = key in (active, SECTION_OF.get(active))
        href = "/?home" if href == "/" else href     # the Home link stays on Home; only a direct visit to / follows the start page
        items.append(f'<li><a href="{href}"{here if on else ""} title="{_esc(label)}">{icon(NAV_ICONS[key])}'
                     f'<span class="lbl">{_esc(label)}</span></a>{sub if on else ""}</li>')
    subnav = ""
    if tabs:   # the section's pages above the title, for when the collapsed sidebar hides them
        subnav = '<nav class="subnav" aria-label="Section"><div class="seg">' + "".join(
            f'<a href="{href}"{here if current else ""}>{_esc(label)}</a>' for href, label, current in tabs) + "</div></nav>"

    chat_label = f'{icon("chat")}<span class="lbl">Chat</span>'
    chat_link = (
        f'<button id="chat-toggle" class="chat-link" aria-controls="chat-drawer" title="Chat">{chat_label}</button>' if drawer
        else f'<a class="chat-link" href="/chat" title="Chat">{chat_label}</a>' if AI_ON else ""   # no AI: /chat says how to set it up
    )
    drawer_html = CHAT_STYLE + DRAWER_STYLE + DRAWER_HTML + CHAT_SCRIPT if drawer else ""

    return (
        "<!doctype html>\n"
        f"<html lang=\"en\"{_display_attrs()}><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Lanxang — {_esc(title)}</title>{FAVICON}{THEME_SCRIPT}"
        f"<style>{PAGE_STYLE}{BLOCKS_STYLE}</style></head><body><a class=\"skip\" href=\"#main\">Skip to content</a>"
        f"<div class=\"app\">{HEADER_BAR}"
        f"<aside class=\"side\"><a class=\"brand\" href=\"/?home\" title=\"Lanxang home\">{LOGO}<span class=\"name\">Lanxang<small lang=\"lo\">ລ້ານຊ້າງ</small></span></a>"
        f"<nav class=\"main\" aria-label=\"Main\"><ul>{''.join(items)}</ul></nav>"
        f"<div class=\"foot\">{chat_link}{HEADER_BAR}"
        + ('<form method="post" action="/logout"><button title="Sign out">' + icon("logout")
           + '<span class="lbl">Sign out</span></button></form>' if SIGN_OUT else "")
        + '<button type="button" class="side-toggle" aria-pressed="false" title="Collapse sidebar">'
        f'{icon("sidebar")}<span class="lbl">Collapse sidebar</span></button>'
        "</div></aside>"
        f"<div class=\"shell{' docked' if drawer else ''}\">"
        f"<main class=\"page\" id=\"main\" tabindex=\"-1\"><div class=\"page-head\"><h1>{_esc(heading or title)}</h1></div>{subnav}{body_html}</main>"
        f"{drawer_html}</div></div>{PREFS_PANEL}{KEYS_SHEET}{TIME_SCRIPT}{PREFS_SCRIPT}{TIME_PREFS_SCRIPT}{KEYS_SCRIPT}"
        "</body></html>"
    )


def ask_chips(questions):
    """
    One-click questions that fill the docked chat (window.atlasAsk), or open /chat when there is no panel.
    """

    if not AI_ON:
        return ""
    return '<div class="chips" aria-label="Ask Lanxang">' + "".join(
        f'<button data-ask="{_esc(q)}">{_esc(q)}</button>' for q in questions) + "</div>" + (
        # Delegated, so [data-ask] buttons rendered AFTER the chips (e.g. Access page "Investigate") work too.
        "<script>if (!window.atlasAskBound) { window.atlasAskBound = true;"
        " document.addEventListener('click', (e) => { const b = e.target.closest('[data-ask]'); if (!b) return;"
        " const q = b.dataset.ask; if (window.atlasAsk) window.atlasAsk(q); else location.href = '/chat?q=' +"
        " encodeURIComponent(q); }); }</script>")


def _kv_table(data):

    if not data:
        return "<p class=\"muted\">No data.</p>"

    rows = "".join(
        f"<tr><td>{_esc(key)}</td><td>{_esc(value)}</td></tr>"
        for key, value in data.items()
    )

    return f"<table><tbody>{rows}</tbody></table>"


def _list_of_dicts_table(items):

    if not items:
        return "<p class=\"muted\">None found.</p>"

    columns = []

    for item in items:
        for key in item.keys():
            if key not in columns:
                columns.append(key)

    header = "".join(f"<th>{_esc(column)}</th>" for column in columns)

    body_rows = "".join(
        "<tr>" + "".join(f"<td>{_esc(item.get(column, ''))}</td>" for column in columns) + "</tr>"
        for item in items
    )

    return f"<div class=\"table-wrap\"><table><thead><tr>{header}</tr></thead><tbody>{body_rows}</tbody></table></div>"


def render_overview_page(environment, analysis, summary=""):
    """
    environment is KnowledgeQueries().latest_environment()'s return
    value (or None if lanxang discover has never run); analysis is
    KnowledgeQueries().latest_analysis()'s (or None).
    """

    overview_tabs = _hosts_tabs("/overview")

    if environment is None:

        return render_page(
            "Overview",
            summary + "<p class=\"muted\">No inventory found. Run <code>lanxang discover</code> first.</p>",
            active="hosts", tabs=overview_tabs
        )

    sections = []

    for title, key in (
        ("System", "system"), ("Hardware", "hardware"),
        ("Storage", "storage"), ("Network", "network")
    ):

        data = environment.get(key) or {}

        # collect_storage() (atlas/discovery/storage.py) always returns a
        # list - one row per mounted filesystem - never a dict, unlike every
        # other category here. _kv_table() unconditionally called .items()
        # on whatever it was given, so this crashed the whole page with an
        # AttributeError on any real host with any storage at all (found by
        # actually running `lanxang discover` + `lanxang web` together, not by
        # a unit test - the existing render tests seed data without a real
        # `storage` key).
        table = _list_of_dicts_table(data) if isinstance(data, list) else _kv_table(data)

        sections.append(
            f"<div class=\"card\"><h2>{_esc(title)}</h2>{table}</div>"
        )

    # lanxang discover's containers/virtualization categories are each
    # keyed by plugin name (see lanxang.plugins.AtlasPlugin.category and
    # the per-category merge in lanxang.cli.main.discover()) - every
    # entry is {"available": bool, "containers"/"guests": [...]}, not
    # the resource itself. Flatten each plugin's list into rows,
    # tagging each with its source plugin.
    containers = environment.get("containers") or {}

    container_rows = [
        {"plugin": plugin_name, **container}
        for plugin_name, result in containers.items()
        if isinstance(result, dict)
        for container in result.get("containers", [])
    ]

    if container_rows:

        sections.append(
            f"<div class=\"card\"><h2>Containers</h2>{_list_of_dicts_table(container_rows)}</div>"
        )

    virtualization = environment.get("virtualization") or {}

    if isinstance(virtualization.get("guests"), list):

        # lanxang proxmox scan's shape - {"nodes": [...], "guests": [...]}
        # - not plugin-sourced, so no "plugin" column to add.
        guests = virtualization["guests"]

    else:

        guests = [
            {"plugin": plugin_name, **guest}
            for plugin_name, result in virtualization.items()
            if isinstance(result, dict)
            for guest in result.get("guests", [])
        ]

    if guests:

        sections.append(
            f"<div class=\"card\"><h2>Virtualization Guests</h2>{_list_of_dicts_table(guests)}</div>"
        )

    if analysis:

        recommendations = "".join(
            f"<li>{_esc(rec)}</li>" for rec in analysis.get("recommendations") or []
        )

        sections.append(
            "<div class=\"card\"><h2>Latest AI Analysis</h2>"
            f"<p class=\"muted\">{_esc(analysis.get('provider'))} / "
            f"{_esc(analysis.get('model'))} — {_esc(analysis.get('created_at'))}</p>"
            f"<p>{_esc(analysis.get('summary'))}</p>"
            f"<ul>{recommendations}</ul></div>"
        )

    timestamp = environment.get("timestamp")

    header = f"<p class=\"muted\">Latest snapshot: {_esc(timestamp)}</p>" if timestamp else ""

    # summary (hosts_page.render_hosts_summary) leads; the raw inventory tables fold underneath it
    raw = header + "".join(sections)
    if summary:
        raw = f'<details class="raw"><summary>Raw snapshot</summary>{raw}</details>'

    return render_page("Overview", summary + raw, active="hosts", tabs=overview_tabs)


def event_label(event_type):
    """'atlas.proxmox.changes_detected' -> 'proxmox changes detected'. Event types stay atlas.* (stored data)."""

    return event_type.removeprefix("atlas.").replace(".", " ").replace("_", " ")


HISTORY_CHIPS = ("Summarize what happened in the last 24 hours.", "Anything unusual in recent events?",
                 "What changed on Proxmox this week?", "Were any actions run, and did they work?")

# (category, icon, matcher) - first match wins; filter buttons use the category
EVENT_CATEGORIES = (("alert", icon("alert"), ("threshold", "alert", "down", "failed", "error", "warn")),
                    ("action", icon("tool"), ("atlas.action.", "restart", "stopped", "resized", "plan")),
                    ("change", icon("refresh"), ("changes_detected", "device.", ".new", "changed")),
                    ("chat", icon("chat"), ("chat",)),
                    ("scan", icon("search"), (".completed", ".loaded", "scan", "discover")))

HISTORY_STYLE = """
<style>
.filters { margin:0 0 14px; }
.day { margin:0 0 18px; } .day > h2 { font-size:.875rem; color:var(--muted); border:0; margin:0 0 6px; }
.ev { display:grid; grid-template-columns:76px 26px 1fr; gap:6px; align-items:start; padding:6px 0;
      border-top:1px solid var(--line); font-size:.875rem; }
.ev[hidden], .day[hidden] { display:none; }   /* display:grid would otherwise beat the hidden attribute */
.ev:first-of-type { border-top:0; } .ev .time { color:var(--muted); font-variant-numeric:tabular-nums; }
.ev .count { color:var(--muted); font-size:.75rem; } .ev .src { color:var(--muted); font-size:.75rem; }
.ev details > summary { cursor:pointer; list-style:none; } .ev details > summary::-webkit-details-marker { display:none; }
.ev pre { margin:6px 0 0; max-height:260px; overflow:auto; }
</style>
"""


# Activity with time zone "browser": the server grouped by UTC day; regroup the rows by the viewer's own day.
# ponytail: rows were folded per UTC day, so a fold near midnight can still count both days; fine for a log.
DAY_SCRIPT = """<script>(function(){var R=document.documentElement,log=document.getElementById("ev-log");
if(!log||(R.dataset.tz||"browser")!=="browser")return;
try{if(log.dataset.zone&&log.dataset.zone===Intl.DateTimeFormat().resolvedOptions().timeZone)return;}catch(e){}   // already grouped by this zone
var groups=[],by={},rows=log.querySelectorAll(".ev");
for(var i=0;i<rows.length;i++)if(!rows[i].querySelector("time[datetime]"))return;   // never drop a row: keep the server's days
rows.forEach(function(ev){var t=ev.querySelector("time[datetime]");
  var d=new Date(t.getAttribute("datetime")),k=d.getFullYear()+"-"+d.getMonth()+"-"+d.getDate();
  if(!by[k]){by[k]=[];groups.push([t.getAttribute("datetime"),by[k]]);}by[k].push(ev);});
if(!groups.length)return;
log.replaceChildren.apply(log,groups.map(function(g){var s=document.createElement("section"),h=document.createElement("h2"),
  t=document.createElement("time");s.className="day";t.setAttribute("datetime",g[0]);t.dataset.when="day";
  h.appendChild(t);s.appendChild(h);g[1].forEach(function(ev){s.appendChild(ev);});return s;}));})();</script>"""


def _event_category(event_type):

    lowered = event_type.lower()
    return next(((cat, icon) for cat, icon, keys in EVENT_CATEGORIES if any(k in lowered for k in keys)), ("other", icon("info")))


def render_history_page(events, today=None, changes="", viewer_zone=None):
    """
    events is KnowledgeQueries().recent_events()'s return value - a
    list of EventRecord ORM objects, same as `lanxang history` prints.
    A timeline: grouped by day, repeats of one event type folded, filterable.
    """

    if not events:

        return render_page(
            "Activity",
            changes + ask_chips(HISTORY_CHIPS) + "<p class=\"muted\">No historical events found.</p>",
            active="history"
        )

    from datetime import timedelta
    from lanxang.clock import _display
    # Day groups (and "x3 today") follow the display zone. With "browser", the zone the browser reported in its
    # lanxang-tz cookie; without one, UTC here and DAY_SCRIPT regroups by the viewer's own day.
    display, zone = _display(DISPLAY), ""
    if display.time_zone == "browser" and viewer_zone:
        display, zone = display.model_copy(update={"time_zone": viewer_zone}), viewer_zone
    zone_attr = f' data-zone="{_esc(zone)}"' if zone else ""
    today = today or local(utcnow(), display)[0].date()
    names = {today: "Today", today - timedelta(days=1): "Yesterday"}

    days = {}
    for event in events:   # newest first; one row per event type per day (newest kept, the rest counted)
        moment = _moment(event.created_at)
        items = days.setdefault(local(moment, display)[0].date() if moment else str(event.created_at)[:10], {})
        items.setdefault(event.event_type, [event, 0])[1] += 1

    sections = ""
    for day, items in days.items():
        rows = ""
        for event, count in items.values():
            cat, mark = _event_category(event.event_type)
            label = event_label(event.event_type)
            rows += (f'<div class="ev" data-cat="{cat}"{" hidden" if cat == "scan" else ""}><span class="time">{when(event.created_at, clock=True)}</span>'
                     f"<span>{mark}</span><details><summary>{_esc(label)}"
                     + (f' <span class="count">\u00d7{count} today, latest</span>' if count > 1 and names.get(day) == "Today"
                        else f' <span class="count">\u00d7{count}, latest</span>' if count > 1 else "")
                     + f' <span class="src">{_esc(event.source)}</span></summary><pre>{_esc(event.payload)}</pre></details></div>')
        newest = next(iter(items.values()))[0].created_at   # the heading follows the viewer's own day (TIME_SCRIPT)
        heading = when(newest, clock="day", text=names.get(day))
        sections += f'<section class="day"><h2>{heading}</h2>{rows}</section>'

    buttons = "".join(f'<button type="button" data-filter="{cat}" aria-pressed="{str(cat == "important").lower()}">{label}</button>'
                      for cat, label in (("important", "Important"), ("all", "All"), ("change", icon("refresh") + "Changes"), ("alert", icon("alert") + "Alerts"),
                                         ("action", icon("tool") + "Actions"), ("scan", icon("search") + "Scans"),
                                         ("chat", icon("chat") + "Chats"), ("other", "Other")))
    script = ("<script>document.querySelectorAll('[data-filter]').forEach((b) => b.addEventListener('click', () => {"
              " const f = b.dataset.filter;"
              " document.querySelectorAll('[data-filter]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));"
              " document.querySelectorAll('.ev').forEach((e) => { e.hidden = f === 'important' ? e.dataset.cat === 'scan'"
              " : f !== 'all' && e.dataset.cat !== f; });"
              " document.querySelectorAll('.day').forEach((d) => { d.hidden = !d.querySelector('.ev:not([hidden])'); });"
              " }));</script>")

    body = (HISTORY_STYLE + changes + ask_chips(HISTORY_CHIPS) + f'<div class="filters seg" role="group" aria-label="Show">{buttons}</div>'
            + '<p class="muted">Routine scans (every 15 min) are hidden under Important — pick All or Scans to see them.</p>'
            + f'<div id="ev-log"{zone_attr}>{sections}</div>' + DAY_SCRIPT + script + "<script>document.querySelectorAll('.day').forEach((d) => {"
              " d.hidden = !d.querySelector('.ev:not([hidden])'); });</script>")

    return render_page("Activity", body, active="history")

def plural(number, word, many=None):
    """'1 device', '3 devices'; many: the plural when it isn't word + 's' ('batteries')."""

    return f"{number} {word if number == 1 else many or word + 's'}"


def empty_state(icon_name, title, why, action=None, extra=""):
    """The shared "nothing here yet" block: an icon, a one-line title, one sentence on why, and an optional
    action (href, label) such as ("/settings#ai", "Turn on in Setup"). extra: trusted HTML after the action."""

    link = f'<a class="btn primary" href="{_esc(action[0])}">{_esc(action[1])} →</a>' if action else ""
    return (f'<div class="empty" role="status">{icon(icon_name)}<div><p class="empty-title">{_esc(title)}</p>'
            f'<p class="muted">{_esc(why)}</p>{link}{extra}</div></div>')


# One set of labels for the same window everywhere it can be picked.
WINDOW_LABELS = {"live": "This hour", "1h": "1 hour", "24h": "24 hours", "7d": "7 days", "30d": "30 days"}


def segmented(options, current, href, label="Time window"):
    """The shared .seg switch as links: options are keys (labelled from WINDOW_LABELS) or (key, text) pairs;
    href formats a key into its URL. The current one carries aria-current."""

    links = ""
    for option in options:
        key, text = option if isinstance(option, tuple) else (option, WINDOW_LABELS.get(option, option))
        here = ' aria-current="page"' if key == current else ""
        links += f'<a href="{_esc(href.format(key=key))}"{here}>{_esc(text)}</a>'
    return f'<div class="seg" role="group" aria-label="{_esc(label)}">{links}</div>'


def _status_color(ok):

    return {True: "var(--green)", False: "var(--red)"}.get(ok, "var(--muted)")


def _svg_box(x, y, width, height, title, subtitle, color, detail=""):

    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" style="fill:var(--surface);stroke:{color}" '
        f'stroke-width="2"/>'
        f'<text x="{x + width / 2}" y="{y + 22}" text-anchor="middle" style="fill:var(--text)" '
        f'font-size="14" font-weight="600">{_esc(title)[:24]}</text>'
        f'<text x="{x + width / 2}" y="{y + 40}" text-anchor="middle" style="fill:var(--muted)" '
        f'font-size="11">{_esc(subtitle)[:30]}</text>'
        + (f'<text x="{x + width / 2}" y="{y + 56}" text-anchor="middle" style="fill:{color}" '
           f'font-size="11">{_esc(detail)[:30]}</text>' if detail else "")
    )


def _posture_block(posture):

    items = {item["key"]: item for item in posture["strip"]}
    warn = next((item for item in posture["strip"] if item["state"] == "warn"), None)
    view = posture.get("internet") or {}
    ports = view.get("ports") or []
    unexpected = sum(not p["expected"] for p in ports)
    internet = (f"{unexpected} unexpected port{'s' * (unexpected != 1)}" if unexpected
                else f"{len(ports)} port{'s' * (len(ports) != 1)} open, all expected" if ports else "")
    if view.get("ok") and not ports:
        internet = "Shodan has no data for this IP" if view.get("known") is False else "No open ports seen"
    if view and view.get("ok") is False:
        internet = f"{internet} (last check failed)" if internet else "Last check failed"

    if warn:
        state, message = "warn", f"{warn['label']}: {warn['value']}"
    elif unexpected:
        state, message = "warn", f"Internet: {internet}"
    elif items["new"]["state"] == "review" and posture["review"]:
        first = posture["review"][0]
        org = first["org"] or first["asn_key"]
        cc = first["cc"] or "?"
        state, message = "review", f"{first['source']} reached {org} ({cc})"
    elif items["ingress"]["state"] == "unknown":
        state, message = "unknown", "No posture data yet"
    else:
        state, message = "ok", "All good"

    return {"state": state, "tunnel": items["ingress"]["value"], "vpn": items["vpn"]["value"],
            "routes": len(posture["exposure"]), "blocked": items["blocked"]["value"],
            "review_count": len(posture["review"]), "message": message, "internet": internet,
            "internet_unexpected": unexpected, "link": "/posture"}


def build_summary(topology, devices=(), posture=None):
    """
    One small JSON object for a dashboard tile (e.g. Homepage's customapi
    widget): counts from the latest saved network map and the device
    inventory, plus a single status word. Nothing is queried live.
    """

    counts = {
        "to_triage": sum(device["state"] == "new" or (device["state"] == "known" and device["status"] == "quiet")
                         for device in devices),
        "devices_quiet": sum(device["status"] == "quiet" and device["state"] != "ignored" for device in devices),
    }
    posture_extra = {"posture": _posture_block(posture)} if posture else {}

    if not topology:
        return {"status": "no map yet - run lanxang map", **counts, **posture_extra}

    containers = [c for members in ((topology.get("docker") or {}).get("networks") or {}).values() for c in members]
    guests = [g for g in (topology.get("proxmox") or {}).get("guests", []) if not g.get("template")]
    hosts = topology.get("lan", [])

    down_hosts = [h["name"] for h in hosts if not h["reachable"]]
    stopped = [c["name"] for c in containers if c["status"] != "running"]
    asleep = [c["name"] for c in containers if container_state(c) == "asleep"]
    unhealthy = [c["name"] for c in containers if c["health"] == "unhealthy"]
    brain = topology.get("brain") or {}

    return {
        "status": "degraded" if (down_hosts or unhealthy) else "ok",
        "generated_at": topology.get("generated_at"),
        "containers_running": len(containers) - len(stopped),
        "containers_total": len(containers),
        "containers_asleep": len(asleep),     # stopped on purpose (exit 0 / lanxang.on-demand): not down
        "containers_unhealthy": unhealthy,
        "guests_running": sum(g["status"] == "running" for g in guests),
        "guests_total": len(guests),
        "hosts_up": len(hosts) - len(down_hosts),
        "hosts_total": len(hosts),
        "hosts_down": down_hosts,
        "ai_reachable": brain.get("reachable"),
        **counts,
        **posture_extra,
    }
