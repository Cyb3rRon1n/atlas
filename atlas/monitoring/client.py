import requests


class PrometheusUnavailableError(Exception):
    """
    Raised when Prometheus itself cannot be reached or returns an
    error - distinct from a query simply having no data (e.g. the
    relevant exporter isn't running), which is a normal None result.
    """


def query_prometheus(base_url: str, promql: str, timeout: int = 10):
    """
    Run a single PromQL instant query and return its scalar value,
    or None if the query has no data. Raises PrometheusUnavailableError
    if Prometheus itself couldn't be reached or errored - callers use
    that to distinguish "Prometheus is down" from "this metric has no
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

    result = payload.get("data", {}).get("result", [])

    if not result:
        return None

    try:
        return float(result[0]["value"][1])

    except (KeyError, IndexError, TypeError, ValueError):
        return None
