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
from lanxang.clock import utcnow
from lanxang.web.chat_assets import CHAT_SCRIPT, CHAT_STYLE, DRAWER_HTML, DRAWER_STYLE


# Colours are tokens: light by default, dark when the system asks for it or the viewer picks it (the sidebar's
# Theme button, kept in localStorage). Pages use var(--...) only, never a raw colour.
LIGHT = """--bg:#f7fbf9; --surface:#ffffff; --surface2:#eef5f2; --deep:#e6efeb; --line:#dde8e3; --line2:#c4d4cd;
  --text:#10201c; --muted:#4f5f5a; --blue:#1e7f66; --accent:#1e7f66; --gold:#c9a227; --on-accent:#ffffff;
  --green:#15803d; --orange:#b45309; --red:#c42b2b; --purple:#7c3aed; --teal:#0f766e; --yellow:#a16207;
  --ok-text:#166534; --ok-line:#86d6a4; --warn-text:#92400e; --warn-line:#f2c97a; --warn-bg:#fff7eb;
  --bad-text:#991b1b; --bad-line:#f3a8a8; --bad-bg:#fef2f2; --lane:#a9d6c7;
  --nav-bg:#0e1a19; --nav-text:#cfe3dc; --nav-muted:#8fb0a6; --nav-on:#16302c; color-scheme:light;"""
DARK = """--bg:#0e1a19; --surface:#13231f; --surface2:#182c27; --deep:#0b1513; --line:#1f3631; --line2:#2a4740;
  --text:#e6f0ec; --muted:#9fb8af; --blue:#5ec2a4; --accent:#5ec2a4; --gold:#e9b44c; --on-accent:#0e1a19;
  --green:#43c08f; --orange:#f0a23a; --red:#f47a5c; --purple:#b48cf2; --teal:#3ccfb4; --yellow:#d9b44a;
  --ok-text:#7fdcb5; --ok-line:#2f6b55; --warn-text:#ffd08a; --warn-line:#6b5530; --warn-bg:#1d1810;
  --bad-text:#ffb4a2; --bad-line:#6b3030; --bad-bg:#2a1d1a; --lane:#2a5248;
  --nav-bg:#08110f; --nav-text:#cfe3dc; --nav-muted:#8fb0a6; --nav-on:#16302c; color-scheme:dark;"""

PAGE_STYLE = f"""
:root {{ {LIGHT} }}
:root[data-theme="dark"] {{ {DARK} }}
""" + """
  @font-face { font-family:"Lexend"; src:url("/static/fonts/Lexend.woff2") format("woff2"); font-weight:100 900; font-display:swap; }
  @font-face { font-family:"Noto Sans Lao"; src:url("/static/fonts/NotoSansLao-Medium.woff2") format("woff2"); font-weight:500; font-display:swap; }
  body { font-family: Lexend, system-ui, -apple-system, "Segoe UI", sans-serif; background:var(--bg);
         color:var(--text); margin:0; line-height:1.5; }
  a { color:var(--blue); text-decoration:none; }
  a:hover { text-decoration:underline; }
  h1 { margin:0 0 16px; font-size:24px; font-weight:600; }
  h2 { font-size:17px; font-weight:600; border-bottom:1px solid var(--line); padding-bottom:0.3rem; }
  table { border-collapse:collapse; width:100%; margin:0.75rem 0 1.5rem; }
  th, td { text-align:left; padding:0.5rem 0.8rem; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em;
       background:var(--surface2); }
  .muted { color:var(--muted); }
  .card { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:1rem 1.5rem;
          margin-bottom:1.5rem; }
  code, pre { font-family: ui-monospace, "IBM Plex Mono", Menlo, monospace; background:var(--deep);
              border:1px solid var(--line); border-radius:4px; padding:0.15rem 0.4rem; font-size:0.85rem; }
  pre { padding:0.75rem; overflow-x:auto; white-space:pre-wrap; word-break:break-word; }
  button { background:var(--surface); color:var(--text); border:1px solid var(--line2); border-radius:6px;
           padding:0.3rem 0.75rem; margin:0 0.25rem 0.25rem 0; cursor:pointer; font:inherit; }
  button:hover { border-color:var(--blue); }
  button.primary { background:var(--accent); border-color:var(--accent); color:var(--on-accent); }
  input, select, textarea { background:var(--surface); color:var(--text); border:1px solid var(--line2);
           border-radius:6px; padding:0.3rem 0.5rem; font:inherit; }
  textarea { width:100%; min-height:4rem; box-sizing:border-box; }
  label { display:block; margin:0.5rem 0 0.2rem; color:var(--muted); font-size:0.85rem; }
  .ic { width:1.1em; height:1.1em; vertical-align:-0.2em; margin-right:.4em; flex:none; }
  :focus-visible { outline:2px solid var(--blue); outline-offset:2px; }
  .status-seen { color:var(--green); } .status-quiet { color:var(--orange); } .status-invisible { color:var(--muted); }
  time[data-when] { white-space:nowrap; }
  #msg { color:var(--red); min-height:1.2rem; } #msg:empty { display:none; }
  .table-wrap { overflow-x:auto; max-width:100%; } .table-wrap > table { margin-top:0; }
  input.wide { width:100%; max-width:26rem; box-sizing:border-box; }
"""

SHELL_STYLE = """
.app { display:flex; min-height:100vh; }
.side { flex:0 0 224px; box-sizing:border-box; background:var(--nav-bg); padding:18px 12px; display:flex;
        flex-direction:column; gap:2px; }
.side a, .side button { display:block; width:100%; box-sizing:border-box; text-align:left; padding:8px 14px; margin:0;
        border:0; border-radius:6px; background:none; color:var(--nav-text); font:inherit; font-size:14px;
        text-decoration:none; cursor:pointer; }
.side a:hover, .side button:hover { background:var(--nav-on); text-decoration:none; }
.side .brand { display:flex; align-items:center; gap:10px; padding:4px 14px 18px; color:#fff; font-weight:700;
        font-size:17px; }
.side .brand:hover { background:none; }
.side .brand .name { display:flex; flex-direction:column; line-height:1.1; }
.side .brand small { font:500 11px "Noto Sans Lao", sans-serif; color:var(--gold); }
.side ul { list-style:none; margin:0; padding:0; }
.side nav.main > ul > li > a[aria-current="page"] { background:var(--nav-on); color:#fff; font-weight:600; }
.side .tabs a { padding:6px 14px 6px 30px; font-size:13px; color:var(--nav-muted); }
.side .tabs a[aria-current="page"] { color:#fff; font-weight:600; box-shadow:inset 2px 0 0 var(--accent); background:none; }
.side .foot { margin-top:auto; padding-top:16px; }
.theme-btn .to-light { display:none; }
:root[data-theme="dark"] .theme-btn .to-light { display:inline; } :root[data-theme="dark"] .theme-btn .to-dark { display:none; }
.side .foot form { margin:0; }
.page { padding:24px 32px 40px; min-width:0; }
.shell { flex:1; min-width:0; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 16px; }
.chips button { font:inherit; font-size:13px; padding:6px 12px; border-radius:999px; margin:0; }
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
  .side .foot { margin:0 0 0 auto; padding:0; display:flex; order:2; }
  .page { padding:16px; }
}
"""

PAGE_STYLE += SHELL_STYLE

# Light is the default whatever the OS prefers; runs before first paint so a chosen theme never flashes.
THEME_SCRIPT = """<script>try{var t=localStorage.getItem("atlas-theme");if(t)document.documentElement.dataset.theme=t;}catch(e){}
function atlasTheme(){var d=document.documentElement;d.dataset.theme=d.dataset.theme==="dark"?"light":"dark";
try{localStorage.setItem("atlas-theme",d.dataset.theme);}catch(e){}}</script>"""

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

    try:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def friendly_time(moment, now, clock=False):
    """The server's wording for a naive-UTC time: '5 min ago', 'today 14:32 UTC', 'yesterday 14:32 UTC', 'Mon 14:32 UTC',
    '12 Nov', '12 Nov 2025'. TIME_SCRIPT redoes the same in the viewer's own time zone; this is what shows without it.
    clock: just 'HH:MM UTC' (rows already grouped by day); clock="day": 'Today', 'Yesterday', 'Mon 16 Nov'."""

    if clock == "day":
        days = (now.date() - moment.date()).days
        return "Today" if days == 0 else "Yesterday" if days == 1 else f"{moment:%a} {moment.day} {moment:%b}"
    if clock:
        return moment.strftime("%H:%M UTC")
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 6 * 60:
        return f"{minutes // 60} h ago"
    days = (now.date() - moment.date()).days
    hhmm = moment.strftime("%H:%M")
    if days == 0:
        return f"today {hhmm} UTC"
    if days == 1:
        return f"yesterday {hhmm} UTC"
    if days < 7:
        return f"{moment:%a} {hhmm} UTC"
    return f"{moment.day} {moment:%b}" + ("" if moment.year == now.year else f" {moment.year}")


def when(value, now=None, clock=False, never="-", text=None):
    """One time on any page: <time datetime="...Z"> with friendly_time() inside, which TIME_SCRIPT rewrites in the
    viewer's local time. never: what to show when there is no time; text: other server-side words."""

    moment = _moment(value)
    if moment is None:
        return _esc(value) if value else _esc(never)
    stamp = moment.isoformat(timespec="seconds")
    mode = "day" if clock == "day" else "clock" if clock else "rel"
    shown = text if text is not None else friendly_time(moment, now or utcnow(), clock)
    return (f'<time datetime="{stamp}Z" data-when="{mode}" title="{stamp[:16].replace("T", " ")} UTC">{_esc(shown)}</time>')


# Last in <body>, so it runs at once. Turns every <time data-when> into the viewer's local time, in the same words as friendly_time(); refreshes each minute.
TIME_SCRIPT = """<script>(function(){
var two=function(n){return (n<10?"0":"")+n;};
var hm=function(d){return two(d.getHours())+":"+two(d.getMinutes());};
var M=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],D=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
function say(d,now,mode){
  if(mode==="clock")return hm(d);
  var a=new Date(d.getFullYear(),d.getMonth(),d.getDate()),b=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  var days=Math.round((b-a)/86400000),min=Math.floor((now-d)/60000);
  if(mode==="day")return days===0?"Today":days===1?"Yesterday":D[d.getDay()]+" "+d.getDate()+" "+M[d.getMonth()];
  if(min<1)return "just now";
  if(min<60)return min+" min ago";
  if(min<360)return Math.floor(min/60)+" h ago";
  if(days===0)return "today "+hm(d);
  if(days===1)return "yesterday "+hm(d);
  if(days<7)return D[d.getDay()]+" "+hm(d);
  return d.getDate()+" "+M[d.getMonth()]+(d.getFullYear()===now.getFullYear()?"":" "+d.getFullYear());
}
function run(){var now=new Date();document.querySelectorAll("time[data-when]").forEach(function(t){
  var d=new Date(t.getAttribute("datetime"));if(isNaN(d))return;
  t.textContent=say(d,now,t.dataset.when);t.title=d.toLocaleString();});}
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

def _hosts_tabs(current):

    return section_tabs("trends" if current == "/trends" else "hosts")


# The Lanxang mark (light variant) as the browser-tab icon, inline: no extra request, no 404 for /favicon.ico.
FAVICON = ('<link rel="icon" href="data:image/svg+xml,'
           "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='10.4' stroke='%231e7f66' stroke-width='1.8' fill='none'/%3E%3Cg transform='translate(4.8 4.8) scale(.6)'%3E%3Cg transform='translate(1.2 2.6) scale(.9)'%3E%3Cpath d='M3 6.6C3 4.9 4.2 4 6 4h2.6v9.8C6.4 13.8 4.9 13.2 4 12.1 3.3 11.2 3 10 3 8.8z' fill='%231e7f66'/%3E%3Cpath d='M21 6.6C21 4.9 19.8 4 18 4h-2.6v9.8c2.2 0 3.7-.6 4.6-1.7.7-.9 1-2.1 1-3.3z' fill='%231e7f66'/%3E%3Cpath d='M8.2 5.2C9.3 3.9 10.6 3.3 12 3.3s2.7.6 3.8 1.9v8.1c0 1.3-.8 2.2-2 2.5l-.6 5.1c-.1.8-.6 1.2-1.2 1.2s-1.1-.4-1.2-1.2l-.6-5.1c-1.2-.3-2-1.2-2-2.5z' fill='%231e7f66'/%3E%3Ccircle cx='10.2' cy='8.6' r='.95' fill='%23f7fbf9'/%3E%3Ccircle cx='13.8' cy='8.6' r='.95' fill='%23f7fbf9'/%3E%3C/g%3E%3Cg transform='translate(9 -.6) scale(.25)'%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(0 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(72 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(144 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(216 12 12)'/%3E%3Cpath d='M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z' fill='%23c9a227' transform='rotate(288 12 12)'/%3E%3Ccircle cx='12' cy='12' r='2.6' fill='%23c9a227' stroke='%23f7fbf9' stroke-width='.7'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E\">")


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
        items.append(f'<li><a href="{href}"{here if on else ""}>{_esc(label)}</a>{sub if on else ""}</li>')

    chat_link = (
        '<button id="chat-toggle" class="chat-link" aria-controls="chat-drawer">Chat</button>' if drawer
        else "<a class=\"chat-link\" href=\"/chat\">Chat</a>"
    )
    drawer_html = CHAT_STYLE + DRAWER_STYLE + DRAWER_HTML + CHAT_SCRIPT if drawer else ""

    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Lanxang — {_esc(title)}</title>{FAVICON}{THEME_SCRIPT}"
        f"<style>{PAGE_STYLE}</style></head><body><div class=\"app\">"
        f"<aside class=\"side\"><a class=\"brand\" href=\"/\">{LOGO}<span class=\"name\">Lanxang<small lang=\"lo\">ລ້ານຊ້າງ</small></span></a>"
        f"<nav class=\"main\" aria-label=\"Main\"><ul>{''.join(items)}</ul></nav>"
        f"<div class=\"foot\">{chat_link}"
        "<button type=\"button\" class=\"theme-btn\" onclick=\"atlasTheme()\" aria-label=\"Switch between light and dark\">"
        f"<span class=\"to-dark\">{icon('moon')}Dark mode</span><span class=\"to-light\">{icon('sun')}Light mode</span></button>"
        + ('<form method="post" action="/logout"><button>Sign out</button></form>' if SIGN_OUT else "") +
        "</div></aside>"
        f"<div class=\"shell{' docked' if drawer else ''}\">"
        f"<main class=\"page\"><h1>{_esc(heading or title)}</h1>{body_html}</main>"
        f"{drawer_html}</div></div>{TIME_SCRIPT}"
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
        raw = f'<details class="raw"><summary>Details — full inventory snapshot</summary>{raw}</details>'

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
.filters { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 14px; }
.filters button[aria-pressed="true"] { background:var(--blue); border-color:var(--blue); color:var(--on-accent); }
.day { margin:0 0 18px; } .day > h2 { font-size:14px; color:var(--muted); border:0; margin:0 0 6px; }
.ev { display:grid; grid-template-columns:76px 26px 1fr; gap:6px; align-items:start; padding:6px 0;
      border-top:1px solid var(--line); font-size:14px; }
.ev[hidden], .day[hidden] { display:none; }   /* display:grid would otherwise beat the hidden attribute */
.ev:first-of-type { border-top:0; } .ev .time { color:var(--muted); font-variant-numeric:tabular-nums; }
.ev .count { color:var(--muted); font-size:12px; } .ev .src { color:var(--muted); font-size:12px; }
.ev details > summary { cursor:pointer; list-style:none; } .ev details > summary::-webkit-details-marker { display:none; }
.ev pre { margin:6px 0 0; max-height:260px; overflow:auto; }
</style>
"""


def _event_category(event_type):

    lowered = event_type.lower()
    return next(((cat, icon) for cat, icon, keys in EVENT_CATEGORIES if any(k in lowered for k in keys)), ("other", icon("info")))


def render_history_page(events, today=None, changes=""):
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

    from datetime import date, timedelta
    today = today or utcnow().date()                     # stored times are UTC days
    names = {today.isoformat(): "Today", (today - timedelta(days=1)).isoformat(): "Yesterday"}

    days = {}
    for event in events:   # newest first; one row per event type per day (newest kept, the rest counted)
        items = days.setdefault(str(event.created_at)[:10], {})
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
        heading = when(newest, clock="day", text=names.get(day, day))
        sections += f'<section class="day"><h2>{heading}</h2>{rows}</section>'

    buttons = "".join(f'<button data-filter="{cat}" aria-pressed="{str(cat == "important").lower()}">{label}</button>'
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

    body = (HISTORY_STYLE + changes + ask_chips(HISTORY_CHIPS) + f'<div class="filters">{buttons}</div>'
            + '<p class="muted">Routine scans (every 15 min) are hidden under Important — pick All or Scans to see them.</p>'
            + sections + script + "<script>document.querySelectorAll('.day').forEach((d) => {"
              " d.hidden = !d.querySelector('.ev:not([hidden])'); });</script>")

    return render_page("Activity", body, active="history")

def plural(number, word, many=None):
    """'1 device', '3 devices'; many: the plural when it isn't word + 's' ('batteries')."""

    return f"{number} {word if number == 1 else many or word + 's'}"


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

    if warn:
        state, message = "warn", f"{warn['label']}: {warn['value']}"
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
            "review_count": len(posture["review"]), "message": message, "link": "/posture"}


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
