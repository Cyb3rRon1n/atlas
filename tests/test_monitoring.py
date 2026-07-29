from unittest.mock import MagicMock, patch

import pytest
import requests

from atlas.monitoring.client import (
    PrometheusUnavailableError,
    query_prometheus,
    query_prometheus_vector,
)
from atlas.monitoring.collector import (
    collect_container_metrics,
    collect_metrics,
    evaluate_thresholds,
)


def _fake_response(status="success", result=None):

    response = MagicMock()
    response.json.return_value = {
        "status": status,
        "data": {"result": result if result is not None else []}
    }

    return response


class TestQueryPrometheus:

    def test_returns_parsed_value_on_success(self):

        response = _fake_response(
            result=[{"metric": {}, "value": [1234567890, "12.34"]}]
        )

        with patch("requests.get", return_value=response):
            value = query_prometheus("http://localhost:9090", "up")

        assert value == 12.34

    def test_returns_none_when_result_is_empty(self):

        response = _fake_response(result=[])

        with patch("requests.get", return_value=response):
            value = query_prometheus("http://localhost:9090", "up")

        assert value is None

    def test_raises_when_connection_fails(self):

        with patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError()
        ):

            with pytest.raises(PrometheusUnavailableError):
                query_prometheus("http://localhost:9090", "up")

    def test_raises_when_status_is_not_success(self):

        response = _fake_response(status="error")

        with patch("requests.get", return_value=response):

            with pytest.raises(PrometheusUnavailableError):
                query_prometheus("http://localhost:9090", "up")

    def test_strips_trailing_slash_from_base_url(self):

        response = _fake_response(
            result=[{"value": [0, "1"]}]
        )

        with patch("requests.get", return_value=response) as mock_get:
            query_prometheus("http://localhost:9090/", "up")

        args, kwargs = mock_get.call_args
        assert args[0] == "http://localhost:9090/api/v1/query"


class TestQueryPrometheusVector:

    def test_parses_multiple_rows_keyed_by_label(self):

        response = _fake_response(
            result=[
                {"metric": {"name": "plex"}, "value": [0, "12.3"]},
                {"metric": {"name": "sonarr"}, "value": [0, "45.6"]},
            ]
        )

        with patch("requests.get", return_value=response):
            values = query_prometheus_vector(
                "http://localhost:9090", "up", label="name"
            )

        assert values == {"plex": 12.3, "sonarr": 45.6}

    def test_skips_rows_missing_the_label(self):

        response = _fake_response(
            result=[
                {"metric": {}, "value": [0, "12.3"]},
                {"metric": {"name": "sonarr"}, "value": [0, "45.6"]},
            ]
        )

        with patch("requests.get", return_value=response):
            values = query_prometheus_vector(
                "http://localhost:9090", "up", label="name"
            )

        assert values == {"sonarr": 45.6}

    def test_returns_empty_dict_when_result_is_empty(self):

        response = _fake_response(result=[])

        with patch("requests.get", return_value=response):
            values = query_prometheus_vector(
                "http://localhost:9090", "up", label="name"
            )

        assert values == {}

    def test_raises_when_connection_fails(self):

        with patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError()
        ):

            with pytest.raises(PrometheusUnavailableError):
                query_prometheus_vector(
                    "http://localhost:9090", "up", label="name"
                )


class TestCollectContainerMetrics:

    def test_available_false_when_prometheus_unreachable(self):

        with patch(
            "atlas.monitoring.collector.query_prometheus_vector",
            side_effect=PrometheusUnavailableError("connection refused")
        ):

            result = collect_container_metrics("http://localhost:9090")

        assert result == {"available": False, "containers": {}}

    def test_merges_cpu_and_memory_by_container_name(self):

        with patch(
            "atlas.monitoring.collector.query_prometheus_vector",
            side_effect=[
                {"plex": 12.3, "sonarr": 45.6},
                {"plex": 30.0, "sonarr": 10.0},
            ]
        ):

            result = collect_container_metrics("http://localhost:9090")

        assert result == {
            "available": True,
            "containers": {
                "plex": {"cpu_percent": 12.3, "memory_percent": 30.0},
                "sonarr": {"cpu_percent": 45.6, "memory_percent": 10.0},
            }
        }

    def test_container_present_in_only_one_query_gets_none_for_the_other(self):

        with patch(
            "atlas.monitoring.collector.query_prometheus_vector",
            side_effect=[
                {"plex": 12.3},
                {"sonarr": 10.0},
            ]
        ):

            result = collect_container_metrics("http://localhost:9090")

        assert result["containers"]["plex"] == {
            "cpu_percent": 12.3, "memory_percent": None
        }
        assert result["containers"]["sonarr"] == {
            "cpu_percent": None, "memory_percent": 10.0
        }


class TestCollectMetrics:

    def test_available_false_when_prometheus_unreachable(self):

        with patch(
            "atlas.monitoring.collector.query_prometheus",
            side_effect=PrometheusUnavailableError("connection refused")
        ):

            result = collect_metrics("http://localhost:9090")

        assert result == {"available": False, "metrics": {}}

    def test_available_true_with_all_metrics_present(self):

        with patch(
            "atlas.monitoring.collector.query_prometheus",
            side_effect=[12.3, 45.6, 78.9]
        ):

            result = collect_metrics("http://localhost:9090")

        assert result == {
            "available": True,
            "metrics": {
                "cpu_percent": 12.3,
                "memory_percent": 45.6,
                "disk_percent": 78.9
            }
        }

    def test_available_true_with_some_metrics_missing(self):
        """
        Prometheus reachable, but not every exporter is set up yet -
        a real scenario since node_exporter isn't guaranteed to be
        running just because Prometheus is.
        """

        with patch(
            "atlas.monitoring.collector.query_prometheus",
            side_effect=[12.3, None, None]
        ):

            result = collect_metrics("http://localhost:9090")

        assert result["available"] is True
        assert result["metrics"]["cpu_percent"] == 12.3
        assert result["metrics"]["memory_percent"] is None
        assert result["metrics"]["disk_percent"] is None


class TestEvaluateThresholds:

    def test_flags_metric_at_or_above_its_threshold(self):

        exceeded = evaluate_thresholds(
            {"cpu_percent": 92.0},
            {"cpu_percent": 90.0}
        )

        assert exceeded == {"cpu_percent": True}

    def test_does_not_flag_metric_below_its_threshold(self):

        exceeded = evaluate_thresholds(
            {"cpu_percent": 45.0},
            {"cpu_percent": 90.0}
        )

        assert exceeded == {"cpu_percent": False}

    def test_value_exactly_at_threshold_counts_as_exceeded(self):

        exceeded = evaluate_thresholds(
            {"cpu_percent": 90.0},
            {"cpu_percent": 90.0}
        )

        assert exceeded == {"cpu_percent": True}

    def test_none_value_is_left_out_rather_than_flagged(self):
        """
        Can't threshold-check a metric that has no data - that's a
        different kind of "unavailable" than "under the limit".
        """

        exceeded = evaluate_thresholds(
            {"cpu_percent": None},
            {"cpu_percent": 90.0}
        )

        assert exceeded == {}

    def test_metric_with_no_configured_threshold_is_left_out(self):

        exceeded = evaluate_thresholds(
            {"cpu_percent": 99.0},
            {}
        )

        assert exceeded == {}

    def test_evaluates_multiple_metrics_independently(self):

        exceeded = evaluate_thresholds(
            {"cpu_percent": 92.0, "memory_percent": 40.0, "disk_percent": None},
            {"cpu_percent": 90.0, "memory_percent": 90.0, "disk_percent": 90.0}
        )

        assert exceeded == {"cpu_percent": True, "memory_percent": False}
