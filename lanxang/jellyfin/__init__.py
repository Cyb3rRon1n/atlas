import json
import urllib.parse
import urllib.request


def _get(config, path, params=None):

    url = config.url.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")

    request = urllib.request.Request(url, headers={
        "Authorization": f'MediaBrowser Token="{config.api_key}"'
    })

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def get_sessions(config, active_minutes=60):
    """
    Who is watching what, and HOW: PlayMethod (DirectPlay / DirectStream =
    remux / Transcode), the transcode reasons, and where the client connects
    from - the first thing to check for "it stutters".
    """

    sessions = []

    for session in _get(config, "/Sessions", {"activeWithinSeconds": int(active_minutes) * 60}):

        item = session.get("NowPlayingItem") or {}
        transcode = session.get("TranscodingInfo") or {}

        sessions.append({
            "user": session.get("UserName"),
            "client": session.get("Client"),
            "client_version": session.get("ApplicationVersion"),
            "device": session.get("DeviceName"),
            "remote_endpoint": session.get("RemoteEndPoint"),
            "now_playing": item.get("Name"),
            "play_method": (session.get("PlayState") or {}).get("PlayMethod"),
            "transcode": {
                key: transcode.get(key)
                for key in ("VideoCodec", "AudioCodec", "IsVideoDirect", "IsAudioDirect",
                            "Bitrate", "TranscodeReasons", "HardwareAccelerationType")
            } if transcode else None,
            "last_activity": session.get("LastActivityDate")
        })

    return {"sessions": sessions}


def get_activity(config, limit=50, search=""):
    """Jellyfin's activity log (plays, stops, logins, plugin installs), newest first."""

    entries = _get(config, "/System/ActivityLog/Entries", {"limit": 2000 if search else int(limit)})["Items"]

    if search:
        needle = search.lower()
        entries = [entry for entry in entries if needle in (entry.get("Name") or "").lower()]

    return {
        "entries": [
            {"date": entry.get("Date"), "type": entry.get("Type"), "name": entry.get("Name")}
            for entry in entries[:int(limit)]
        ]
    }


def get_plugins(config):
    """Installed plugins with version, status and their live configuration."""

    plugins = []

    for plugin in _get(config, "/Plugins"):

        try:
            settings = _get(config, f"/Plugins/{plugin['Id']}/Configuration")

        except Exception:
            settings = None

        plugins.append({
            "name": plugin.get("Name"),
            "version": plugin.get("Version"),
            "status": plugin.get("Status"),
            "configuration": settings
        })

    return {"plugins": plugins}
