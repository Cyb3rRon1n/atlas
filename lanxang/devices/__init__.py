from dataclasses import dataclass, field


@dataclass
class Sighting:
    """
    One observation from one source, before it's stored: source is lan /
    proxmox / manual, external_id is that source's own stable key (a MAC,
    pve:<vmid>, a configured address).
    """

    source: str
    external_id: str
    ip: str | None = None
    mac: str | None = None
    hostname: str | None = None
    detail: dict = field(default_factory=dict)
