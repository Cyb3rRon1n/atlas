from atlas.services.catalog import SERVICES


def detect_services(containers):

    results = []

    for container in containers:

        name = container["name"].lower()

        detected = None

        for service, info in SERVICES.items():

            if service in name:

                detected = {
                    "name": service,
                    "category": info["category"],
                    "purpose": info["purpose"],
                    "container": container["name"],
                    "status": container["status"],
                }

                break


        if detected:
            results.append(detected)


    return results
