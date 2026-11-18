"""Lanxang brand files from one definition: python tools/brand.py docs/images/brand"""
import pathlib, sys

EARL = "M3 6.6C3 4.9 4.2 4 6 4h2.6v9.8C6.4 13.8 4.9 13.2 4 12.1 3.3 11.2 3 10 3 8.8z"
EARR = "M21 6.6C21 4.9 19.8 4 18 4h-2.6v9.8c2.2 0 3.7-.6 4.6-1.7.7-.9 1-2.1 1-3.3z"
HEAD = ("M8.2 5.2C9.3 3.9 10.6 3.3 12 3.3s2.7.6 3.8 1.9v8.1c0 1.3-.8 2.2-2 2.5l-.6 5.1c-.1.8-.6 1.2-1.2 1.2"
        "s-1.1-.4-1.2-1.2l-.6-5.1c-1.2-.3-2-1.2-2-2.5z")
PETAL = "M12 12C9.4 9.8 8.2 6.4 9.6 4 10.6 2.4 13.4 2.4 14.4 4 15.8 6.4 14.6 9.8 12 12z"
DARK = dict(bg="#0e1a19", main="#5ec2a4", gold="#e9b44c")
LIGHT = dict(bg="#f7fbf9", main="#1e7f66", gold="#c9a227")


def mark(main, gold, hole):
    face = (f'<path d="{EARL}" fill="{main}"/><path d="{EARR}" fill="{main}"/><path d="{HEAD}" fill="{main}"/>'
            f'<circle cx="10.2" cy="8.6" r=".95" fill="{hole}"/><circle cx="13.8" cy="8.6" r=".95" fill="{hole}"/>')
    flower = "".join(f'<path d="{PETAL}" fill="{gold}" transform="rotate({k * 72} 12 12)"/>' for k in range(5))
    flower += f'<circle cx="12" cy="12" r="2.6" fill="{gold}" stroke="{hole}" stroke-width=".7"/>'
    inner = (f'<g transform="translate(1.2 2.6) scale(.9)">{face}</g>'
             f'<g transform="translate(9 -.6) scale(.25)">{flower}</g>')
    return (f'<circle cx="12" cy="12" r="10.4" stroke="{main}" stroke-width="1.8" fill="none"/>'
            f'<g transform="translate(4.8 4.8) scale(.6)">{inner}</g>')


def svg(body, w=24, h=24):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{body}</svg>\n'


def logo(c):   # mark + wordmark + Lao name, 120x32 units; text as <text> using the vendored fonts' family names
    return svg(f'<g transform="scale(1.333)">{mark(c["main"], c["gold"], c["bg"])}</g>'
               f'<text x="38" y="19" font-family="Lexend, sans-serif" font-weight="600" font-size="17" fill="{c["main"]}">Lanxang</text>'
               f'<text x="38.5" y="28.5" font-family="Noto Sans Lao, sans-serif" font-weight="500" font-size="7" fill="{c["gold"]}">ລ້ານຊ້າງ</text>', 120, 32)


def social(c=DARK):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640" width="1280" height="640">'
            f'<rect width="1280" height="640" fill="{c["bg"]}"/>'
            f'<g transform="translate(110 170) scale(12.5)">{mark(c["main"], c["gold"], c["bg"])}</g>'
            f'<text x="470" y="310" font-family="Lexend, sans-serif" font-weight="600" font-size="120" fill="{c["main"]}">Lanxang</text>'
            f'<text x="474" y="390" font-family="Noto Sans Lao, sans-serif" font-weight="500" font-size="56" fill="{c["gold"]}">ລ້ານຊ້າງ</text>'
            f'<text x="474" y="470" font-family="Lexend, sans-serif" font-weight="400" font-size="30" fill="#9fb5ae">Every device on your home network, watched over.</text>'
            f'</svg>\n')


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    files = {
        "mark-dark.svg": svg(mark(DARK["main"], DARK["gold"], DARK["bg"])),
        "mark-light.svg": svg(mark(LIGHT["main"], LIGHT["gold"], LIGHT["bg"])),
        "logo-dark.svg": logo(DARK), "logo-light.svg": logo(LIGHT),
        "favicon.svg": svg(mark(LIGHT["main"], LIGHT["gold"], "#ffffff")),
        "social-preview.svg": social(),
    }
    files["mark.svg"] = files["mark-light.svg"]
    for name, text in files.items():
        (out / name).write_text(text)
    print("wrote", ", ".join(sorted(files)))
