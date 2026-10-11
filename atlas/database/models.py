from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class Base(DeclarativeBase):
    pass


class EventRecord(Base):

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    event_type: Mapped[str]

    source: Mapped[str]

    payload: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow
    )


class EnvironmentRecord(Base):

    __tablename__ = "environment"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    data: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow
    )


class AnalysisRecord(Base):

    __tablename__ = "analysis"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    summary: Mapped[str]

    recommendations: Mapped[str]

    provider: Mapped[str]

    model: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow
    )


class DeviceRecord(Base):
    """One real device as the operator knows it; sightings point at it."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str]

    kind: Mapped[str] = mapped_column(default="other")

    tags: Mapped[str] = mapped_column(default="[]")

    notes: Mapped[str] = mapped_column(default="")

    important: Mapped[bool] = mapped_column(default=False)

    # new / known / ignored
    state: Mapped[str] = mapped_column(default="new")

    # Fields the operator set by hand - automation never overwrites these.
    locked_fields: Mapped[str] = mapped_column(default="[]")

    # A name match is only ever a suggestion, never an automatic merge.
    suggested_merge_id: Mapped[int | None] = mapped_column(default=None)

    # unknown / wired / wireless - "unknown" lets atlas.devices.wiring guess
    # without overwriting what the operator actually knows.
    connection: Mapped[str] = mapped_column(default="unknown")

    # The device this one's switch port/AP uplinks through, for drawing the
    # wired map. Self-referential: another row in this same table.
    uplink_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), default=None)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class SightingRecord(Base):
    """What one source saw, keyed by that source's own id (MAC, pve:<vmid>, address)."""

    __tablename__ = "sightings"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[str]

    external_id: Mapped[str]

    ip: Mapped[str | None] = mapped_column(default=None)

    mac: Mapped[str | None] = mapped_column(default=None)

    hostname: Mapped[str | None] = mapped_column(default=None)

    detail: Mapped[str] = mapped_column(default="{}")

    first_seen: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    last_seen: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), default=None)


class SourceRunRecord(Base):
    """One run of one source - a failed run never makes a device look quiet."""

    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[str]

    started_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    ok: Mapped[bool] = mapped_column(default=True)

    error: Mapped[str] = mapped_column(default="")

    seen_count: Mapped[int] = mapped_column(default=0)


class NotificationRecord(Base):
    """Queued alert (kind new/offline); sent_at stays null until delivered."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))

    kind: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    sent_at: Mapped[datetime | None] = mapped_column(default=None)


class PostureFlowRecord(Base):
    """Bytes/connections per hour per (source container, destination ip:port/proto)."""

    __tablename__ = "posture_flows"
    __table_args__ = (UniqueConstraint("hour", "source", "dest_ip", "dest_port", "proto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hour: Mapped[datetime]
    source: Mapped[str]
    band: Mapped[str]
    dest_ip: Mapped[str]
    dest_port: Mapped[int]
    proto: Mapped[str]
    asn: Mapped[int] = mapped_column(default=0)
    org: Mapped[str] = mapped_column(default="")
    cc: Mapped[str] = mapped_column(default="")
    bytes_out: Mapped[int] = mapped_column(default=0)
    bytes_in: Mapped[int] = mapped_column(default=0)
    conns: Mapped[int] = mapped_column(default=0)


class PostureSeenRecord(Base):
    """First/last time a source talked to a network (ASN, or the bare IP when unknown)."""

    __tablename__ = "posture_seen"
    __table_args__ = (UniqueConstraint("source", "asn_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    asn_key: Mapped[str]
    org: Mapped[str] = mapped_column(default="")
    cc: Mapped[str] = mapped_column(default="")
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]


class PostureKnownRecord(Base):
    """Operator said this source->network pair is expected (Mark as expected)."""

    __tablename__ = "posture_known"
    __table_args__ = (UniqueConstraint("source", "asn_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    asn_key: Mapped[str]
    note: Mapped[str] = mapped_column(default="")
    marked_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class PostureRouteRecord(Base):
    """Snapshot of public routes; a new snapshot is written only when the set changes."""

    __tablename__ = "posture_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_at: Mapped[datetime]
    routes: Mapped[str]


class PostureStatusRecord(Base):
    """Last result per collector source - drives greying out stale bands."""

    __tablename__ = "posture_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(unique=True)
    ok: Mapped[bool]
    detail: Mapped[str] = mapped_column(default="{}")
    updated_at: Mapped[datetime]


class AccessHitRecord(Base):
    """Requests per hour per (visitor IP, public service) from the Traefik access log."""

    __tablename__ = "access_hits"
    __table_args__ = (UniqueConstraint("hour", "ip", "service"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hour: Mapped[datetime] = mapped_column(index=True)
    ip: Mapped[str] = mapped_column(index=True)
    service: Mapped[str]
    requests: Mapped[int] = mapped_column(default=0)
    denied: Mapped[int] = mapped_column(default=0)     # 401/403/429 - login wall, CrowdSec, rate limit
    errors: Mapped[int] = mapped_column(default=0)     # 5xx


class AccessIpRecord(Base):
    """One row per visitor IP: where it is (DB-IP, ASN table) and when it was first/last seen."""

    __tablename__ = "access_ips"

    ip: Mapped[str] = mapped_column(primary_key=True)
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]
    cc: Mapped[str] = mapped_column(default="")
    country: Mapped[str] = mapped_column(default="")
    region: Mapped[str] = mapped_column(default="")
    city: Mapped[str] = mapped_column(default="")
    lat: Mapped[float | None] = mapped_column(default=None)
    lon: Mapped[float | None] = mapped_column(default=None)
    asn: Mapped[int | None] = mapped_column(default=None)
    org: Mapped[str] = mapped_column(default="")


class AccessLoginRecord(Base):
    """A sign-in (or failed attempt) to an app with its own accounts, e.g. Jellyfin's activity log."""

    __tablename__ = "access_logins"
    __table_args__ = (UniqueConstraint("app", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    app: Mapped[str]
    external_id: Mapped[str]                           # the app's own event id - makes re-reads idempotent
    time: Mapped[datetime] = mapped_column(index=True)
    user: Mapped[str]
    ip: Mapped[str]
    ok: Mapped[bool]
    client: Mapped[str] = mapped_column(default="")


class AccessStateRecord(Base):
    """Collector bookmarks (log byte offset, last app event id)."""

    __tablename__ = "access_state"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]


class AccessPlaceRecord(Base):
    """A (user, place) pair - place = country + provider. learned (first 14 days), confirmed by you, or review."""

    __tablename__ = "access_places"
    __table_args__ = (UniqueConstraint("user", "place_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(index=True)
    place_key: Mapped[str]
    label: Mapped[str]
    status: Mapped[str]                                 # learned | confirmed | review
    first_seen: Mapped[datetime]
    last_seen: Mapped[datetime]
    ip: Mapped[str] = mapped_column(default="")
    app: Mapped[str] = mapped_column(default="")
    alerted: Mapped[bool] = mapped_column(default=False)
