import socket


def collect_network():

    hostname = socket.gethostname()

    addresses = socket.gethostbyname_ex(hostname)

    return {
        "hostname": hostname,
        "addresses": addresses[2],
    }
