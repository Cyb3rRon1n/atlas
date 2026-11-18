import socket
import time


DEFAULT_PORTS = [22, 80, 443]

MAX_PORTS = 10


def check_host(host, ports=None, timeout=2.0):
    """
    Read-only LAN diagnosis: does the name resolve, and which TCP ports
    accept a connection (with how long the handshake took). TCP rather
    than ICMP ping - no raw-socket privilege needed, works in a slim
    container, and "is the service port answering" is the real question.
    """

    ports = [int(port) for port in (ports or DEFAULT_PORTS)][:MAX_PORTS]

    try:
        address = socket.gethostbyname(host)

    except (socket.gaierror, UnicodeError) as error:
        return {"host": host, "resolved": False, "error": f"DNS lookup failed: {error}"}

    results = []

    for port in ports:

        started = time.monotonic()

        try:
            with socket.create_connection((address, port), timeout=timeout):
                pass

            results.append({"port": port, "open": True, "ms": round((time.monotonic() - started) * 1000, 1)})

        except OSError as error:
            results.append({"port": port, "open": False, "error": str(error) or type(error).__name__})

    return {
        "host": host,
        "resolved": True,
        "address": address,
        "ports": results,
        "reachable": any(result["open"] for result in results)
    }
