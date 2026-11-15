from typing import Literal
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
    # Host health alerts (atlas sample, every atlas-scan pass): once per new problem and once when it clears.
    alerts: bool = True
    temp_margin_c: float = 5.0      # alert this close to a sensor's own "high" limit (two samples in a row)
    memory_percent: float = 90.0
    disk_percent: float = 90.0      # root disk and every storage_paths entry


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


class NtfyNotifyConfig(BaseModel):
    # e.g. https://ntfy.sh or your own server; the phone app subscribes to topic.
    url: str = ""
    topic: str = ""
    token: str = ""        # or ATLAS_NTFY_TOKEN in the environment


class EmailNotifyConfig(BaseModel):
    host: str = ""
    port: int = 587        # 465 = implicit TLS, otherwise STARTTLS when starttls is on
    starttls: bool = True
    user: str = ""
    password: str = ""     # or ATLAS_SMTP_PASSWORD in the environment
    sender: str = ""       # From: address, defaults to user
    to: list[str] = []


class NotifyConfig(BaseModel):
    # Every channel that is set gets each alert; see docs: Configuration > Alerts.
    signal: SignalNotifyConfig = SignalNotifyConfig()
    ntfy: NtfyNotifyConfig = NtfyNotifyConfig()
    webhooks: list[str] = []   # Discord / Slack webhook URLs, or any URL that takes JSON
    email: EmailNotifyConfig = EmailNotifyConfig()
    apprise: list[str] = []    # Apprise URLs (tgram://, pover://, matrix://, ...) - needs the apprise package


class AccessConfig(BaseModel):
    """Who reaches the public services, from where (atlas access collect -> web /access). Off unless enabled."""
    enabled: bool = False
    traefik_log: str = "/traefik-logs/access.log"
    geo_path: str = "inventory/dbip-city-lite.mmdb"
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""
    ignore_ips: list[str] = []          # e.g. this host's own WAN IP hitting its public URLs (health checks)
    home_ips: list[str] = []            # shown as "home" on the map instead of a foreign dot
    retention_days: int = 30


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


class TorrentClientConfig(BaseModel):
    name: str                           # shown in alerts, e.g. "pve-host"
    url: str                            # qBittorrent Web UI as published by its gluetun container
    username: str = ""                  # empty when local auth is bypassed
    password: str = ""


class VpnWatchConfig(BaseModel):
    """qBittorrent instances that must stay behind gluetun (atlas vpn check). Empty = off."""
    clients: list[TorrentClientConfig] = []


class WiringSwitch(BaseModel):
    # SNMPv3 authPriv only; passphrases come from env ATLAS_SNMP_<NAME>_AUTH / _PRIV.
    name: str
    host: str
    snmp_user: str = "atlas"
    priv: Literal["aes", "des"] = "aes"   # des: older gear (e.g. Cisco Sx300) offers nothing else


class WiringUnifi(BaseModel):
    # Optional: a local read-only UniFi account, from env ATLAS_UNIFI_USER / ATLAS_UNIFI_PASS.
    enabled: bool = False
    url: str = ""
    site: str = "default"
    verify_ssl: bool = False   # UniFi consoles ship a self-signed cert


class WiringConfig(BaseModel):
    """Port-level wired map (atlas wiring scan -> web /cabling). Off unless enabled."""
    enabled: bool = False
    timeout: int = 10
    keep_snapshots: int = 30
    switches: list[WiringSwitch] = []
    unifi: WiringUnifi = WiringUnifi()
    cabling_file: str = "cabling.yaml"


class SecurityConfig(BaseModel):
    """LAN watch (atlas lan check -> Posture page): rogue DHCP servers and gateway ARP spoofing."""
    dhcp_probe: bool = True          # one DHCP discover per run; never takes an address
    dhcp_timeout: float = 3.0
    dhcp_servers: list[str] = []     # DHCP servers besides the default gateway (Pi-hole, a second router)


class WebConfig(BaseModel):
    # builtin: atlas asks for its own admin password (atlas.web.auth).
    # proxy: an auth proxy (Authelia, Authentik, ...) in front of atlas does it - atlas checks nothing.
    auth: Literal["builtin", "proxy"] = "builtin"


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
    access: AccessConfig = AccessConfig()
    vpn: VpnWatchConfig = VpnWatchConfig()
    web: WebConfig = WebConfig()
    security: SecurityConfig = SecurityConfig()
    wiring: WiringConfig = WiringConfig()
