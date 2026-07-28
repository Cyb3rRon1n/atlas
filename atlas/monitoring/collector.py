from atlas.monitoring.client import PrometheusUnavailableError, query_prometheus


CPU_QUERY = (
    '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
)

MEMORY_QUERY = (
    "100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100)"
)

DISK_QUERY = (
    '100 - (node_filesystem_avail_bytes{mountpoint="/"} '
    '/ node_filesystem_size_bytes{mountpoint="/"} * 100)'
)


def collect_metrics(base_url: str):
    """
    Query a handful of standard node_exporter metrics. "available"
    reflects whether Prometheus itself was reachable; each metric is
    independently None if its own query had no data (e.g. node_exporter
    isn't actually running yet, or a different exporter setup is used).
    """

    queries = {
        "cpu_percent": CPU_QUERY,
        "memory_percent": MEMORY_QUERY,
        "disk_percent": DISK_QUERY,
    }

    metrics = {}

    try:

        for name, promql in queries.items():

            metrics[name] = query_prometheus(base_url, promql)

    except PrometheusUnavailableError:

        return {
            "available": False,
            "metrics": {}
        }

    return {
        "available": True,
        "metrics": metrics
    }


def evaluate_thresholds(metrics: dict, thresholds: dict) -> dict:
    """
    Returns {metric_name: bool} for whether each metric is at or above
    its configured threshold. A metric that's None (no data for that
    query) or has no configured threshold is left out entirely - can't
    flag what wasn't collected, and a metric without a threshold isn't
    "not exceeded", it's not evaluated.
    """

    exceeded = {}

    for name, value in metrics.items():

        threshold = thresholds.get(name)

        if value is not None and threshold is not None:
            exceeded[name] = value >= threshold

    return exceeded
