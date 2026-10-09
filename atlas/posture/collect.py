"""
One posture poll: read the connection table, account deltas into hourly
buckets, refresh routes/tunnel/inbound counts, and query gluetun, CrowdSec and
the public-IP echo. Each source's outcome lands in posture_status, so the page
can grey out exactly the part that is stale; nothing here raises.
"""

from datetime import timedelta
from pathlib import Path

import requests

from atlas.posture.aggregate import Accountant, inbound_counts, tunnel_connections
from atlas.posture.collectors.asn import AsnTable, load_table, refresh
from atlas.posture.collectors.conntrack import read_conntrack
from atlas.posture.collectors.services import (container_ip, container_ips, crowdsec_bans, gluetun_status,
                                               public_ip, vpn_members)
from atlas.posture.collectors.traefik import collect_routes


PUBLIC_IP_EVERY = timedelta(minutes=10)
ASN_CHECK_EVERY = timedelta(hours=24)
PRUNE_EVERY = timedelta(hours=1)


class Collector:

    def __init__(self, settings, store, client, read_flows=read_conntrack, get=requests.get, asn_table=None):
        self.settings, self.store, self.client = settings, store, client
        self.read_flows, self.get = read_flows, get
        self.accountant = Accountant()
        self.asn_table = asn_table
        self.last_public_ip = None
        self.last_asn_check = None
        self.last_prune = None

    def _status(self, source, result, now):
        ok = bool(result.get("ok"))
        self.store.set_status(source, ok, {k: v for k, v in result.items() if k != "ok"}, now)
        return ok

    def _asn(self, now):
        self.last_asn_check = now
        try:
            if refresh(Path(self.settings.asn_path), self.settings.asn_url, now, get=self.get) or not self.asn_table:
                self.asn_table = load_table(self.settings.asn_path)
            self._status("asn", {"ok": len(self.asn_table) > 0, "ranges": len(self.asn_table)}, now)
        except Exception as error:
            if not self.asn_table:
                try:
                    self.asn_table = load_table(self.settings.asn_path)
                except Exception:
                    self.asn_table = AsnTable([])
            self._status("asn", {"ok": False, "error": str(error)[:300]}, now)

    def _service(self, source, container, port, key_field, call, now):
        key = getattr(self.settings, key_field)
        if not key:
            return self._status(source, {"ok": False, "error": f"not configured (posture.{key_field})"}, now)
        try:
            ip = container_ip(self.client, container)
            if not ip:
                return self._status(source, {"ok": False, "error": f"container {container} not found"}, now)
            return self._status(source, call(f"http://{ip}:{port}", key, get=self.get), now)
        except Exception as error:
            return self._status(source, {"ok": False, "error": str(error)[:300]}, now)

    def run_once(self, now):

        s = self.settings

        if self.last_asn_check is None and self.asn_table is not None:
            # A table handed in (tests, or a caller that loaded it) is used as-is until the next daily check.
            self.last_asn_check = now
            self._status("asn", {"ok": len(self.asn_table) > 0, "ranges": len(self.asn_table)}, now)
        elif self.last_asn_check is None or now - self.last_asn_check >= ASN_CHECK_EVERY:
            self._asn(now)

        try:
            sources = container_ips(self.client)
            cloudflared_ip = container_ip(self.client, s.cloudflared_container)
            traefik_ip = container_ip(self.client, s.traefik_container)
            vpn = {s.gluetun_container, *vpn_members(self.client, s.gluetun_container)}
        except Exception:
            sources, cloudflared_ip, traefik_ip, vpn = {}, None, None, {s.gluetun_container}

        result = {"flows": 0, "deltas": 0, "new": []}

        try:
            flows = self.read_flows()
            self._status("conntrack", {"ok": True, "flows": len(flows)}, now)
        except Exception as error:
            flows = []
            self._status("conntrack", {"ok": False, "error": str(error)[:300]}, now)

        if flows:
            deltas = self.accountant.deltas(flows, sources, s.host_ip, vpn, self.asn_table)
            result.update(flows=len(flows), deltas=len(deltas))
            try:
                result["new"] = self.store.record_flows(deltas, now, track_seen=bool(self.asn_table))
            except Exception as error:
                self._status("conntrack", {"ok": True, "flows": len(flows), "store_error": str(error)[:300]}, now)

        tunnel = tunnel_connections(flows, cloudflared_ip)
        self._status("tunnel", {"ok": tunnel > 0, "connections": tunnel}, now)
        self._status("inbound", {"ok": bool(flows), **inbound_counts(flows, s.host_ip, traefik_ip)}, now)

        try:
            routes = collect_routes(self.client, s.traefik_dynamic_dir, s.auth_middleware)
            self.store.save_routes(routes, now)
            self._status("routes", {"ok": True, "count": len(routes)}, now)
        except Exception as error:
            self._status("routes", {"ok": False, "error": str(error)[:300]}, now)

        self._service("gluetun", s.gluetun_container, s.gluetun_port, "gluetun_api_key", gluetun_status, now)
        self._service("crowdsec", s.crowdsec_container, s.crowdsec_port, "crowdsec_api_key", crowdsec_bans, now)

        if self.last_public_ip is None or now - self.last_public_ip >= PUBLIC_IP_EVERY:
            self.last_public_ip = now
            try:
                self._status("public_ip", public_ip(s.ip_echo_url, get=self.get), now)
            except Exception as error:
                self._status("public_ip", {"ok": False, "error": str(error)[:300]}, now)

        if self.last_prune is None or now - self.last_prune >= PRUNE_EVERY:
            self.last_prune = now
            self.store.prune(now - timedelta(days=s.retention_days))

        return result
