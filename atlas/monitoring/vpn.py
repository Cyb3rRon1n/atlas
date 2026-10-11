"""
Torrent VPN watch (atlas vpn check). Each qBittorrent runs inside gluetun
(network_mode: service:gluetun), so its Web API answers only while the tunnel
container is up, and it reports whether peers can reach it. A client is a
problem when it is unreachable, disconnected, or firewalled while torrents are
active (the VPN port forward was lost - torrents stall at "downloading
metadata"). Two bad checks in a row -> one Signal message; another on recovery.
"""

import json

import requests

FAILS_TO_ALERT = 2
STATE_KEY = "vpn_watch"


def probe(client, session=None):
    """'' when healthy, otherwise a short reason."""

    s = session or requests.Session()
    base = client.url.rstrip("/")

    try:
        if client.username:
            login = s.post(base + "/api/v2/auth/login", timeout=15,
                           data={"username": client.username, "password": client.password})
            if login.text.strip() != "Ok.":
                return "qBittorrent login failed"

        info = s.get(base + "/api/v2/transfer/info", timeout=15)
        info.raise_for_status()
        status = info.json().get("connection_status")

        if status == "disconnected":
            return "qBittorrent has no connection - the VPN tunnel looks down"

        if status == "firewalled":
            active = s.get(base + "/api/v2/torrents/info", params={"filter": "active"}, timeout=15).json()
            if active:
                return f"firewalled with {len(active)} active torrent(s) - the VPN port forward looks lost"

        return ""

    except (requests.RequestException, ValueError) as error:
        return f"unreachable ({type(error).__name__}) - gluetun or qBittorrent is down"


def check(clients, store, send=None, session=None):
    """Probe every client, alert on new outages and recoveries. Returns {name: problem or ''}."""

    state = json.loads(store.get_state(STATE_KEY, "{}") or "{}")
    results, down, back = {}, [], []

    for client in clients:
        problem = results[client.name] = probe(client, session)
        st = state.setdefault(client.name, {"fails": 0, "down": False})

        if problem:
            st["fails"] += 1
            if st["fails"] >= FAILS_TO_ALERT and not st["down"]:
                down.append((client.name, problem))
        else:
            st["fails"] = 0
            if st["down"]:
                back.append(client.name)

    if down or back:
        lines = []
        if down:
            lines += ["**🔴 Torrent VPN problem**"] + [f"• {name}: {problem}" for name, problem in down]
        if back:
            lines += ([""] if down else []) + ["**🟢 Torrent VPN working again**"] + [f"• {name}" for name in back]

        ok = send("\n".join(lines))[0] if send else True
        if ok:   # unsent alerts retry next run
            for name, _ in down:
                state[name]["down"] = True
            for name in back:
                state[name]["down"] = False

    store.set_state(STATE_KEY, json.dumps(state))

    return results
