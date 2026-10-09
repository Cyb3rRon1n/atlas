import requests


class Response:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text
        self.content = text.encode()
    def json(self):
        return self._data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class Container:
    def __init__(self, name, cid, mode, networks):
        self.name, self.id = name, cid
        self.attrs = {"HostConfig": {"NetworkMode": mode},
                      "NetworkSettings": {"Networks": {n: {"IPAddress": ip} for n, ip in networks.items()}}}


class Client:
    def __init__(self, items):
        self.items = items
        outer = self
        class containers:
            @staticmethod
            def list():
                return outer.items
            @staticmethod
            def get(name):
                return next(c for c in outer.items if c.name == name)
        self.containers = containers


def make_client(extra=()):
    items = [
        Container("gluetun", "abc123", "stack_default", {"stack_default": "172.18.0.3"}),
        Container("qbittorrent", "q1", "container:abc123", {}),
        Container("sonarr", "s1", "stack_default", {"stack_default": "172.18.0.13", "other": ""}),
        Container("atlas-scan", "a1", "host", {"host": ""}),
        *extra,
    ]
    for item in items:
        item.labels = {}
    return Client(items)
