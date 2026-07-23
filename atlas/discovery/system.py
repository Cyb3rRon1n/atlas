import platform
import socket


def collect_system():
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "distribution": platform.platform(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
    }
