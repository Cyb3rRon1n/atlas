"""
The operator's patch-panel file. LLDP and MAC tables can't see a passive patch
panel or a wall jack, so this small YAML file is the only manual part of the
cabling map. Lives in the config dir (never the repo); a bad file never blanks
the page - discovery still renders and the error is shown.
"""

from pathlib import Path

import yaml


def load_cabling(path):

    empty = {"panels": [], "ports": {}, "error": None}
    path = Path(path)

    if not path.exists():
        return empty

    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark else "line ?"
        return {**empty, "error": f"cabling.yaml {where}: {getattr(error, 'problem', error)}"}

    errors, panels, ports = [], [], {}

    for panel in data.get("panels") or []:
        name = str((panel or {}).get("name") or "?")
        for number, entry in ((panel or {}).get("ports") or {}).items():
            entry = entry or {}
            if not isinstance(number, int) or not entry.get("switch") or not entry.get("port"):
                errors.append(f"{name} port {number}: needs a number, switch and port")
                continue
            panels.append({"panel": name, "port": number, "switch": str(entry["switch"]),
                           "switch_port": str(entry["port"]), "label": str(entry.get("label") or ""),
                           "color": str(entry.get("color") or "")})

    for key, entry in (data.get("ports") or {}).items():
        entry = entry or {}
        ports[str(key)] = {"label": str(entry.get("label") or ""), "color": str(entry.get("color") or "")}

    return {"panels": panels, "ports": ports, "error": "; ".join(errors) or None}