from pydantic import BaseModel


class ProxmoxNode(BaseModel):
    name: str
    status: str
    cpu: float | None = None
    memory: int | None = None


class ProxmoxGuest(BaseModel):
    """
    A Proxmox-managed VM (qemu) or container (lxc).
    """

    vmid: int
    name: str
    node: str
    type: str
    status: str
    cpu: float | None = None
    maxcpu: float | None = None
    mem: int | None = None
    maxmem: int | None = None
    disk: int | None = None
    maxdisk: int | None = None
    uptime: int | None = None
