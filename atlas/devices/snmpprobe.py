"""
SNMPv3 engine discovery: the first message every SNMPv3 manager sends before it signs in (RFC 3414 4).
It carries no user name and no password, so it is not a failed login. A device running an SNMPv3 agent
answers with a Report holding its engine ID, whose first bytes name the maker (an IANA enterprise number).
One UDP packet per device; a device that doesn't answer simply has no SNMP agent, or filters it.
"""

import os
import select
import socket
import time

VENDORS = {     # IANA enterprise numbers of common switch/router/NAS makers
    9: "Cisco", 11: "HPE", 43: "3Com", 171: "D-Link", 674: "Dell", 1916: "Extreme", 2011: "Huawei",
    2636: "Juniper", 4526: "Netgear", 6486: "Alcatel-Lucent", 6574: "Synology", 6876: "VMware",
    8072: "net-snmp (Linux)", 11863: "TP-Link", 12356: "Fortinet", 14823: "Aruba", 14988: "MikroTik",
    24681: "QNAP", 25506: "H3C", 30065: "Arista", 41112: "Ubiquiti", 52642: "FS",
}


def _tlv(tag, body):

    n = len(body)
    length = bytes([n]) if n < 0x80 else bytes([0x80 | len(n.to_bytes((n.bit_length() + 7) // 8, "big"))]) \
        + n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([tag]) + length + body


def _int(value):

    return _tlv(0x02, value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big", signed=True))


def _octets(value):

    return _tlv(0x04, value)


def discovery_packet(message_id):
    """An SNMPv3 GetRequest with an empty user and engine ID, flagged reportable (noAuthNoPriv)."""

    usm = _tlv(0x30, _octets(b"") + _int(0) + _int(0) + _octets(b"") + _octets(b"") + _octets(b""))
    pdu = _tlv(0xA0, _int(message_id) + _int(0) + _int(0) + _tlv(0x30, b""))
    scoped = _tlv(0x30, _octets(b"") + _octets(b"") + pdu)
    header = _tlv(0x30, _int(message_id) + _int(65507) + _octets(b"\x04") + _int(3))

    return _tlv(0x30, _int(3) + header + _octets(usm) + scoped)


def _read(data, at):
    """(tag, value, next offset) of the BER element at data[at]."""

    tag, length, at = data[at], data[at + 1], at + 2
    if length & 0x80:
        size = length & 0x7F
        length, at = int.from_bytes(data[at:at + size], "big"), at + size
    if at + length > len(data):
        raise ValueError("truncated")

    return tag, data[at:at + length], at + length


def _children(body):

    at, out = 0, []
    while at < len(body):
        tag, value, at = _read(body, at)
        out.append((tag, value))

    return out


def engine_id(reply):
    """The authoritative engine ID from an SNMPv3 reply, or None when it isn't one."""

    try:
        tag, message, _ = _read(reply, 0)
        parts = _children(message) if tag == 0x30 else []
        if len(parts) < 3 or parts[0] != (0x02, b"\x03") or parts[2][0] != 0x04:
            return None
        tag, usm, _ = _read(parts[2][1], 0)
        fields = _children(usm) if tag == 0x30 else []
        return fields[0][1] if fields and fields[0][0] == 0x04 and fields[0][1] else None
    except (IndexError, ValueError):
        return None


def vendor(engine):
    """The maker named by an engine ID (RFC 3411 format: high bit set + enterprise number), or ""."""

    if not engine or len(engine) < 4 or not engine[0] & 0x80:
        return ""
    number = int.from_bytes(engine[:4], "big") & 0x7FFFFFFF

    return VENDORS.get(number, f"enterprise {number}")


def discover(ips, timeout=2.0, port=161, sock=None):
    """{ip: {"engine": hex, "vendor": name}} for each address whose SNMPv3 agent answered."""

    ips = list(dict.fromkeys(ips))
    if not ips:
        return {}
    own = sock is None
    sock = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    found = {}
    try:
        sock.setblocking(False)
        ids = {}
        for ip in ips:
            message_id = int.from_bytes(os.urandom(3), "big")
            ids[ip] = message_id
            try:
                sock.sendto(discovery_packet(message_id), (ip, port))
            except OSError:
                continue
        deadline = time.monotonic() + timeout
        while len(found) < len(ips):
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([sock], [], [], left)[0]:
                break
            try:
                reply, (ip, _) = sock.recvfrom(4096)
            except OSError:
                continue
            engine = engine_id(reply) if ip in ids else None
            if engine:
                found[ip] = {"engine": engine.hex(), "vendor": vendor(engine)}
    finally:
        if own:
            sock.close()

    return found
