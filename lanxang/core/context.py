from dataclasses import dataclass, field


@dataclass
class AtlasContext:
    """
    Shared runtime context for Atlas.
    Every subsystem contributes information here.
    """

    config: dict = field(default_factory=dict)

    inventory: dict = field(default_factory=dict)

    docker: dict = field(default_factory=dict)

    proxmox: dict = field(default_factory=dict)

    services: dict = field(default_factory=dict)

    health: dict = field(default_factory=dict)
