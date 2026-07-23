def discover_nodes(client):

    if not client:
        return []


    nodes = []

    result = (
        client.nodes.get()
    )


    for node in result:

        nodes.append(
            {
                "name": node["node"],
                "status": node["status"]
            }
        )


    return nodes
