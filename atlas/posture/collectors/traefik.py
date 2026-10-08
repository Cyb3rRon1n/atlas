"""
Public routes as Traefik sees them, without needing Traefik's API: docker-label
routers (traefik.enable=true containers) plus file-provider routers from the
dynamic config directory (mounted read-only). A route whose middlewares include
the auth middleware (default "authelia") is "authelia"; anything else is
"public" (the app's own login, if any, is all that stands in front of it).
"""

import re
from pathlib import Path

import yaml


HOST = re.compile(r"Host\(([^)]*)\)")
ROUTER_LABEL = re.compile(r"^traefik\.http\.routers\.([^.]+)\.(rule|entrypoints|middlewares)$")


def _hosts(rule):
    return [host for group in HOST.findall(rule or "") for host in re.findall(r"`([^`]+)`", group)]


def _split(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _route(name, rule, entrypoints, middlewares, auth_middleware, provider):
    protected = any(m.split("@")[0].startswith(auth_middleware) for m in middlewares)
    return {"name": name, "hosts": _hosts(rule), "entrypoints": entrypoints,
            "protection": "authelia" if protected else "public", "provider": provider}


def routes_from_labels(containers, auth_middleware):

    routes = []

    for container in containers:
        labels = container.get("labels") or {}
        if labels.get("traefik.enable") != "true":
            continue
        routers = {}
        for key, value in labels.items():
            match = ROUTER_LABEL.match(key)
            if match:
                routers.setdefault(match.group(1), {})[match.group(2)] = value
        for name, fields in sorted(routers.items()):
            if "rule" not in fields:
                continue
            routes.append(_route(name, fields["rule"], _split(fields.get("entrypoints")),
                                 _split(fields.get("middlewares")), auth_middleware, "docker"))

    return routes


def routes_from_files(directory, auth_middleware):

    if not directory or not Path(directory).is_dir():
        return []

    routes = []

    for path in sorted(Path(directory).iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except (yaml.YAMLError, OSError):
            continue
        routers = ((data.get("http") or {}).get("routers") or {}) if isinstance(data, dict) else {}
        for name, fields in routers.items():
            if not isinstance(fields, dict) or "rule" not in fields:
                continue
            routes.append(_route(name, fields["rule"], _split(fields.get("entryPoints")),
                                 _split(fields.get("middlewares")), auth_middleware, "file"))

    return sorted(routes, key=lambda r: r["name"])


def collect_routes(client, directory, auth_middleware):
    containers = [{"name": c.name, "labels": c.labels or {}} for c in client.containers.list()]
    routes = routes_from_labels(containers, auth_middleware) + routes_from_files(directory, auth_middleware)
    return sorted(routes, key=lambda r: r["name"])
