import requests


class PrometheusUnavailableError(Exception):
    """
    Raised when Prometheus itself cannot be reached or returns an
    error - distinct from a query simply having no data (e.g. the
    relevant exporter isn't running), which is a normal None result.
    """


def _query(base_url: str, promql: str, timeout: int = 10):
    """
    Run a single PromQL instant query and return its raw result list
    (one entry per series). Raises PrometheusUnavailableError if
    Prometheus itself couldn't be reached or errored - callers use
    that to distinguish "Prometheus is down" from "this query has no
    data yet" (e.g. an exporter that isn't running).
    """

    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/api/v1/query",
            params={"query": promql},
            timeout=timeout
        )

        response.raise_for_status()

    except requests.exceptions.RequestException as error:
        raise PrometheusUnavailableError(str(error)) from error

    payload = response.json()

    if payload.get("status") != "success":
        raise PrometheusUnavailableError(
            f"Prometheus returned status: {payload.get('status')}"
        )

    return payload.get("data", {}).get("result", [])


def query_prometheus(base_url: str, promql: str, timeout: int = 10):
    """
    Run a single PromQL instant query and return its scalar value,
    or None if the query has no data.
    """

    result = _query(base_url, promql, timeout)

    if not result:
        return None

    try:
        return float(result[0]["value"][1])

    except (KeyError, IndexError, TypeError, ValueError):
        return None


def query_prometheus_vector(base_url: str, promql: str, label: str, timeout: int = 10):
    """
    Run a PromQL instant query and return {label_value: value} for
    every series in the result, keyed by the given Prometheus label
    (e.g. "name" for cAdvisor's per-container label) - used for
    queries that return one row per container rather than a single
    scalar. A row missing the label or with an unparseable value is
    skipped rather than raising, same as query_prometheus's handling
    of a single bad row.
    """

    result = _query(base_url, promql, timeout)

    values = {}

    for row in result:

        key = row.get("metric", {}).get(label)

        if key is None:
            continue

        try:
            values[key] = float(row["value"][1])

        except (KeyError, IndexError, TypeError, ValueError):
            continue

    return values
