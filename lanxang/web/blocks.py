"""
Shared page building blocks: pure functions that return HTML strings (a status hero, trend tiles with a small line,
seven-day strips, checklist rows, a timeline and a bar chart with a readable scale). BLOCKS_STYLE is rendered once by
render_page. Colours are the theme's CSS variables only, so light, dark and high contrast follow; every chart, line
and strip carries its numbers as text (<title> or aria-label), so nothing is colour-only.

render.py imports this module, so it escapes with its own html.escape wrapper instead of render._esc.
"""

from html import escape
from math import floor, log10

from lanxang import clock
from lanxang.web.icons import icon


def _esc(value):

    return escape(str(value))


def _num(value):
    """A number for people: 12.5, 0.25, 25 (never 25.0 or 1e+06)."""

    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def nice_top(peak):
    """The smallest of 1, 2, 2.5 or 5 x 10^k that is at least peak: a chart's top line; 1 when there is no peak."""

    if peak <= 0:
        return 1
    scale = 10 ** floor(log10(peak))
    for step in (1, 2, 2.5, 5, 10):
        top = step * scale
        if top >= peak * (1 - 1e-9):        # 3 * 0.1 is 0.30000000000000004: compare with a little give
            return round(top, 12)


def sparkline(points, label, width=100, height=22):
    """A small line with no axes; None points are skipped and long series thinned to 30 points. "" for fewer than 2."""

    values = [value for value in points if value is not None]
    if len(values) < 2:
        return ""
    if len(values) > 30:
        values = [values[round(i * (len(values) - 1) / 29)] for i in range(30)]   # keeps the first and the last

    low, high = min(values), max(values)
    span = high - low
    step = width / (len(values) - 1)
    line = " ".join(
        f"{i * step:.1f},{(height - 2 - (value - low) / span * (height - 4)) if span else height / 2:.1f}"
        for i, value in enumerate(values))
    tip = f"{label}: min {_num(low)}, max {_num(high)}, now {_num(values[-1])}"

    return (f'<svg class="sparkline" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{_esc(tip)}"><title>{_esc(tip)}</title><polyline points="{line}"/></svg>')


def status_hero(count, title, subtitle, state):
    """A page's top line: a ring (a check when ok, the count when something needs a look, "?" when unknown), the
    title and a muted subtitle. Any other state reads as unknown, never as healthy."""

    state = state if state in ("ok", "attention") else "unknown"
    ring = {"ok": icon("check"), "attention": _esc(count), "unknown": "?"}[state]
    sub = f'<p class="muted">{_esc(subtitle)}</p>' if subtitle else ""

    return (f'<section class="hero {state}"><span class="ring">{ring}</span>'
            f'<div><p class="hero-title">{_esc(title)}</p>{sub}</div></section>')


def trend_tile(label, value, unit="", points=None, state="ok", href=None, note="", strip=""):
    """A small tile: label, big value, then a day_strip() result or a trend line (nothing when there are no points),
    and an optional note. A link when href is given. state: ok, attention or unknown; the note says why in words."""

    state = state if state in ("ok", "attention") else "unknown"
    mark = icon("alert") if state == "attention" else ""
    small = f"<small>{_esc(unit)}</small>" if unit else ""
    tail = f'<span class="note">{_esc(note)}</span>' if note else ""
    body = (f'<span class="lbl">{mark}{_esc(label)}</span><span class="val">{_esc(value)}{small}</span>'
            f'{strip or sparkline(points or [], label)}{tail}')

    if href:
        return f'<a class="trend {state}" href="{_esc(href)}">{body}</a>'
    return f'<div class="trend {state}">{body}</div>'


def day_strip(days):
    """One square per day, oldest first, each "ok", "bad" or "none" (no data); its label counts the ok days."""

    days = [d if d in ("ok", "bad") else "none" for d in days]
    with_data = sum(d != "none" for d in days)
    text = f"{days.count('ok')} of {with_data} days ok" if with_data else "no data"
    squares = "".join(f'<span class="d {d}"></span>' for d in days)

    return f'<span class="daystrip" role="img" aria-label="{text}" title="{text}">{squares}</span>'


def check_row(icon_name, title, detail="", action=None, state="todo"):
    """A checklist row: todo (gold), done (jade, with a check) or info; action is (label, href), shown as a button."""

    state = state if state in ("done", "info") else "todo"
    mark = icon("check") if state == "done" else icon(icon_name)
    more = f'<p class="muted">{_esc(detail)}</p>' if detail else ""
    button = f'<a class="btn sm" href="{_esc(action[1])}">{_esc(action[0])}</a>' if action else ""

    return (f'<div class="checkrow {state}"><span class="mark">{mark}</span>'
            f'<div class="what"><p class="title">{_esc(title)}</p>{more}</div>{button}</div>')


def timeline(items):
    """A vertical list of (when, title, text, state); when is naive UTC, shown as a time in the display zone with the
    date too when it isn't today. state: ok, attention or info (the dot's colour; the title says what happened)."""

    if not items:
        return ""
    from lanxang.web import render       # the display settings live there; imported here, render imports this module

    display = render.DISPLAY
    today = clock.local(clock.utcnow(), display)[0].date()
    rows = []
    for when, title, text, state in items:
        here = clock.local(when, display)[0]
        shown = clock.hhmm(here, display) if here.date() == today else f"{clock.day(here, display)} {clock.hhmm(here, display)}"
        state = state if state in ("ok", "attention") else "info"
        more = f' <span class="muted">{_esc(text)}</span>' if text else ""
        rows.append(f'<li class="{state}"><time datetime="{when.replace(microsecond=0).isoformat()}Z">{_esc(shown)}</time> '
                    f'<b>{_esc(title)}</b>{more}</li>')

    return f'<ol class="timeline">{"".join(rows)}</ol>'


def bar_chart(values, labels, x_ticks, unit="", fmt=None, height=110, label=""):
    """
    Bars with a readable scale: gridlines and y values at 0, half and a nice top, x_ticks ({bar index: text}) under
    the bars, each bar's tooltip from labels. The axis text is HTML around the SVG, so it never stretches; only the
    bars' SVG scales. fmt(v) formats a y value (default: the number plus unit). The label states peak and total.
    """

    if not values:
        return ""
    fmt = fmt or (lambda v: f"{_num(v)}{unit}")
    top = nice_top(max(values))
    width = len(values) * 10

    grid = "".join(f'<line x1="0" x2="{width}" y1="{y}" y2="{y}" vector-effect="non-scaling-stroke"/>' for y in (0, 50, 100))
    bars = "".join(
        f'<rect x="{i * 10 + 1.5}" y="{100 - h:.2f}" width="7" height="{h:.2f}">'
        f'<title>{_esc(labels[i] if i < len(labels) else fmt(v))}</title></rect>'
        for i, v in enumerate(values) for h in [max(v, 0) / top * 100])
    y_axis = "".join(f'<span style="bottom:{pos}%">{_esc(fmt(v))}</span>' for pos, v in ((0, 0), (50, top / 2), (100, top)))
    x_axis = "".join(f'<span style="left:{(i + 0.5) / len(values) * 100:.2f}%">{_esc(text)}</span>'
                     for i, text in sorted(x_ticks.items()) if 0 <= i < len(values))
    summary = f"{label + ': ' if label else ''}peak {fmt(max(values))}, total {fmt(sum(values))}"

    return (f'<div class="bars" role="img" aria-label="{_esc(summary)}" title="{_esc(summary)}">'
            f'<div class="y" style="height:{height}px">{y_axis}</div>'
            f'<div class="plot" style="height:{height}px"><svg viewBox="0 0 {width} 100" preserveAspectRatio="none">'
            f'{grid}{bars}</svg></div><div></div><div class="x">{x_axis}</div></div>')


BLOCKS_STYLE = """
  /* blocks */
  :is(.hero, .trend, .timeline li).ok { color:var(--text); }   /* the chat panel's global .ok would turn them green */
  .hero { display:flex; align-items:center; gap:14px; padding:14px 16px; margin:0 0 16px; border-radius:12px;
          border:1px solid var(--line); background:linear-gradient(90deg, color-mix(in srgb, var(--accent) 12%, var(--surface)), var(--surface)); }
  .hero .ring { width:44px; height:44px; flex:none; box-sizing:border-box; border-radius:50%; border:5px solid var(--green);
          display:flex; align-items:center; justify-content:center; font-weight:600; font-size:1.0625rem; color:var(--green); }
  .hero .ring .ic { width:20px; height:20px; }
  .hero.attention { border-color:var(--warn-line); background:linear-gradient(90deg, var(--warn-bg), var(--surface)); }
  .hero.attention .ring { border-color:var(--orange); color:var(--orange); }
  .hero.unknown { background:var(--surface); }
  .hero.unknown .ring { border-color:var(--line2); border-style:dashed; color:var(--muted); }
  .hero p { margin:0; } .hero .hero-title { font-size:1.125rem; font-weight:600; }
  .trend { display:flex; flex-direction:column; gap:2px; min-width:110px; padding:10px 12px; box-sizing:border-box;
           background:var(--surface); border:1px solid var(--line); border-radius:10px; color:var(--text); }
  a.trend:hover { border-color:var(--accent); text-decoration:none; }
  .trend .lbl { display:flex; align-items:center; gap:4px; font-size:.75rem; color:var(--muted); }
  .trend .lbl .ic { width:14px; height:14px; color:var(--orange); }
  .trend .val { font-size:1.25rem; font-weight:600; } .trend .val small { font-size:.8125rem; font-weight:500; color:var(--muted); margin-left:2px; }
  .trend.attention { border-color:var(--warn-line); } .trend.unknown .val { color:var(--muted); }
  .trend .note { font-size:.75rem; color:var(--muted); }
  .sparkline { display:block; max-width:100%; margin-top:4px; overflow:visible; }
  .sparkline polyline { fill:none; stroke:var(--accent); stroke-width:1.5; stroke-linejoin:round; stroke-linecap:round; }
  .trend.attention .sparkline polyline { stroke:var(--orange); }
  .daystrip { display:inline-flex; gap:3px; margin-top:6px; }
  .daystrip .d { width:11px; height:11px; box-sizing:border-box; border-radius:2px; background:var(--green); }
  .daystrip .d.bad { background:var(--red); } .daystrip .d.none { background:none; border:1px dashed var(--line2); }
  .checkrow { display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--line); }
  .checkrow:last-child { border-bottom:0; }
  .checkrow .mark { width:28px; height:28px; flex:none; border-radius:7px; display:flex; align-items:center; justify-content:center;
           color:var(--gold-text); background:color-mix(in srgb, var(--gold) 18%, var(--surface)); }
  .checkrow .mark .ic { width:16px; height:16px; }
  .checkrow.done .mark { color:var(--green); background:color-mix(in srgb, var(--green) 14%, var(--surface)); }
  .checkrow.info .mark { color:var(--muted); background:var(--surface2); }
  .checkrow .what { flex:1; min-width:0; } .checkrow p { margin:0; } .checkrow .title { font-weight:500; }
  .checkrow .muted { font-size:.8125rem; }
  .timeline { list-style:none; margin:0; padding:0 0 0 14px; border-left:2px solid var(--line); }
  .timeline li { position:relative; padding:4px 0; }
  .timeline li::before { content:""; position:absolute; left:-20px; top:10px; width:10px; height:10px; border-radius:50%; background:var(--accent); }
  .timeline li.attention::before { background:var(--gold); } .timeline li.info::before { background:var(--line2); }
  .timeline time { color:var(--muted); font-size:.8125rem; margin-right:4px; font-variant-numeric:tabular-nums; }
  .bars { display:grid; grid-template-columns:auto 1fr; column-gap:6px; font-size:.6875rem; color:var(--muted); }
  .bars .y { position:relative; min-width:2.5em; }
  .bars .y span { position:absolute; right:0; transform:translateY(50%); white-space:nowrap; font-variant-numeric:tabular-nums; }
  .bars .plot svg { display:block; width:100%; height:100%; overflow:visible; }
  .bars line { stroke:var(--line); stroke-width:1; } .bars rect { fill:var(--accent); }
  .bars .x { position:relative; height:1.4em; margin-top:2px; }
  .bars .x span { position:absolute; top:0; transform:translateX(-50%); white-space:nowrap; }
"""
