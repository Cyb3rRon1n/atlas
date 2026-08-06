from atlas.knowledge.queries import KnowledgeQueries
from atlas.monitoring.trends import container_metric_trend, host_metric_trend, known_container_names
from atlas.proxmox.trends import guest_metric_trend, known_guests


def _trend_summary(points):

    values = [value for _, value in points]

    return {
        "latest": values[-1],
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "samples": len(values)
    }


def build_trends_payload(limit=20):
    """
    Pure function returning the exact {"host", "containers", "guests"}
    shape `atlas trends --json` already prints - single source of
    truth for both the CLI's --json path and the read-only web view,
    so the two can never compute different numbers from the same
    underlying history. Metric iteration order is fixed (same tuples
    the CLI always used) so dict insertion order matches the CLI's
    existing printed order exactly.
    """

    records = KnowledgeQueries().environment_history(limit)

    if not any(
        record["data"].get("monitoring") or record["data"].get("virtualization")
        for record in records
    ):
        return {"host": {}, "containers": {}, "guests": {}}

    host_payload = {}

    for metric_name in ("cpu_percent", "memory_percent", "disk_percent"):

        points = host_metric_trend(records, metric_name)

        if points:
            host_payload[metric_name] = _trend_summary(points)

    containers_payload = {}

    for container_name in known_container_names(records):

        container_payload = {}

        for metric_name in (
            "cpu_percent", "memory_percent",
            "cpu_percent_of_limit", "memory_percent_of_limit"
        ):

            points = container_metric_trend(records, container_name, metric_name)

            if points:
                container_payload[metric_name] = _trend_summary(points)

        containers_payload[container_name] = container_payload

    guests_payload = {}

    for vmid, name in known_guests(records).items():

        guest_payload = {"name": name}

        for metric_name in ("cpu_percent", "memory_percent"):

            points = guest_metric_trend(records, vmid, metric_name)

            if points:
                guest_payload[metric_name] = _trend_summary(points)

        guests_payload[vmid] = guest_payload

    return {
        "host": host_payload,
        "containers": containers_payload,
        "guests": guests_payload
    }
