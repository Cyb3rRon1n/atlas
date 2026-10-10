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
    token_name: str = ""
    token_value: str = ""
    verify_ssl: bool = False


class IntelligenceConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-opus-5"
    ollama_host: str = "http://localhost:11434"
    # Ollama-only: thinking models (e.g. qwen3) reason silently before
    # answering, which is much slower - False keeps replies fast enough for
    # Cloudflare's 100s limit. None omits the field for an Ollama/model
    # combination that rejects it outright.
    think: bool | None = False
    # Optional separate model for `atlas analyze` (the daily check-up), e.g. Claude while chat stays on a
    # local model. Falls back to provider/model above if it fails (missing key, outage).
    analyze_provider: str | None = None
    analyze_model: str | None = None


class MonitoringConfig(BaseModel):
    enabled: bool = False
    prometheus_url: str = "http://localhost:9090"
    cpu_threshold: float = 90.0
    memory_threshold: float = 90.0
    disk_threshold: float = 90.0
    cpu_allocation_threshold: float = 90.0
    memory_allocation_threshold: float = 90.0


class FleetNode(BaseModel):
    name: str
    host: str
    user: str = "atlas"
    port: int = 22
    identity_file: str = ""


class FleetConfig(BaseModel):
    nodes: list[FleetNode] = []


class KnowledgeConfig(BaseModel):
    # Folders of Markdown/text notes (runbooks, restore guides, incident notes)
    # the search_notes chat tool searches. Empty = tool not offered.
    notes_paths: list[str] = []
    # Short files (host/IP map, conventions) prepended to every chat question.
    pinned_paths: list[str] = []
    # Top note sections automatically attached to every chat question (0 = off).
    auto_context: int = 3


class JellyfinConfig(BaseModel):
    enabled: bool = False
    url: str = "http://jellyfin:8096"
    api_key: str = ""


class HealthConfig(BaseModel):
    # name -> URL of a JSON status feed get_host_health also reads (e.g. a RAID watchdog)
    status_urls: dict[str, str] = {}
    # label -> path inside the container whose usage the home page's storage card shows (e.g. a ro media mount)
    storage_paths: dict[str, str] = {}


class MapHost(BaseModel):
    name: str
    address: str
    role: str = ""
    ports: list[int] = [22]


class MapConfig(BaseModel):
    # Other machines on the LAN to show on the network map (reachability only).
    hosts: list[MapHost] = []


class ScanConfig(BaseModel):
    # Whole-LAN device discovery (atlas scan). Empty subnets = the default-route interface's network.
    # How often atlas-scan re-runs (docker-compose.yml) is ATLAS_SCAN_MINUTES, an env
    # var read by the compose loop itself - not a config field here.
    enabled: bool = True
    subnets: list[str] = []
    timeout: float = 0.5


class SignalNotifyConfig(BaseModel):
    # signal-cli-rest-api, e.g. http://signal-cli:8080. Empty url = no alerts.
    url: str = ""
    number: str = ""
    recipients: list[str] = []


class NotifyConfig(BaseModel):
    signal: SignalNotifyConfig = SignalNotifyConfig()


class PostureConfig(BaseModel):
    """Egress/posture collector (atlas posture watch). Off unless enabled."""
    enabled: bool = False
    interval: int = 30
    retention_days: int = 30
    host_ip: str = ""
    gluetun_container: str = "gluetun"
    gluetun_port: int = 8000
    gluetun_api_key: str = ""
    crowdsec_container: str = "crowdsec"
    crowdsec_port: int = 8080
    crowdsec_api_key: str = ""
    cloudflared_container: str = "cloudflared"
    traefik_container: str = "traefik"
    traefik_dynamic_dir: str = ""
    auth_middleware: str = "authelia"
    ip_echo_url: str = "https://api.ipify.org"
    asn_url: str = "https://iptoasn.com/data/ip2asn-v4.tsv.gz"
    asn_path: str = "inventory/ip2asn-v4.tsv.gz"


class AtlasConfig(BaseModel):
    name: str = "atlas-node"
    discovery: DiscoveryConfig = DiscoveryConfig()
    inventory: InventoryConfig = InventoryConfig()
    proxmox: ProxmoxConfig = ProxmoxConfig()
    intelligence: IntelligenceConfig = IntelligenceConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    fleet: FleetConfig = FleetConfig()
    knowledge: KnowledgeConfig = KnowledgeConfig()
    jellyfin: JellyfinConfig = JellyfinConfig()
    health: HealthConfig = HealthConfig()
    map: MapConfig = MapConfig()
    scan: ScanConfig = ScanConfig()
    notify: NotifyConfig = NotifyConfig()
    posture: PostureConfig = PostureConfig()
