from proxmoxer import ProxmoxAPI



def connect(
    host,
    user,
    password,
    verify_ssl=False
):

    try:

        return ProxmoxAPI(
            host,
            user=user,
            password=password,
            verify_ssl=verify_ssl
        )

    except Exception:

        return None
