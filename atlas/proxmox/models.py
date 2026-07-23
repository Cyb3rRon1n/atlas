from pydantic import BaseModel


class ProxmoxNode(BaseModel):
    name: str
    status: str
    cpu: float | None = None
    memory: int | None = None


class VirtualMachine(BaseModel):
    vmid: int
    name: str
    status: str
    type: str
