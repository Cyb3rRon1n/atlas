def host_metric_trend(records, metric_name):
    """
    records is KnowledgeQueries.environment_history()'s most-recent-
    first result. Returns chronological (oldest-first) (created_at,
    value) pairs, skipping any row with no monitoring data at all
    (e.g. a discover- or proxmox-scan-only row, since each atlas
    invocation only saves whatever it itself discovered) or where
    this metric is None.
    """

    points = []

    for record in records:

        monitoring = record["data"].get("monitoring") or {}
        value = monitoring.get("metrics", {}).get(metric_name)

        if value is not None:
            points.append((record["created_at"], value))

    return list(reversed(points))


def container_metric_trend(records, container_name, metric_name):

    points = []

    for record in records:

        monitoring = record["data"].get("monitoring") or {}
        container = monitoring.get("containers", {}).get(container_name, {})
        value = container.get(metric_name)

        if value is not None:
            points.append((record["created_at"], value))

    return list(reversed(points))


def known_container_names(records):
    """
    Every container name that appears in any snapshot's monitoring
    data, so the CLI can list per-container trends without a
    separate lookup of which containers currently exist.
    """

    names = set()

    for record in records:

        monitoring = record["data"].get("monitoring") or {}
        names.update(monitoring.get("containers", {}).keys())

    return sorted(names)
