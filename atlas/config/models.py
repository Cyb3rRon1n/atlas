from pydantic import BaseModel


class DiscoveryConfig(BaseModel):
    hardware: bool = True
    storage: bool = True
    network: bool = True


class InventoryConfig(BaseModel):
    directory: str = "inventory/generated"


class ProxmoxConfig(BaseModel):
    enabled: bool = False
    host: str = ""
    user: str = ""
    password: str = ""
    verify_ssl: bool = False


class AtlasConfig(BaseModel):
    name: str = "atlas-node"
    discovery: DiscoveryConfig = DiscoveryConfig()
    inventory: InventoryConfig = InventoryConfig()
    proxmox: ProxmoxConfig = ProxmoxConfig()
