from proxmoxer import ProxmoxAPI



def connect(
    host,
    user,
    password="",
    token_name="",
    token_value="",
    verify_ssl=False
):

    try:

        if token_name and token_value:

            return ProxmoxAPI(
                host,
                user=user,
                token_name=token_name,
                token_value=token_value,
                verify_ssl=verify_ssl
            )

        return ProxmoxAPI(
            host,
            user=user,
            password=password,
            verify_ssl=verify_ssl
        )

    except Exception:

        return None
