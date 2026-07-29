from datetime import datetime

from atlas.monitoring.trends import (
    container_metric_trend,
    host_metric_trend,
    known_container_names,
)


def _record(created_at, data):

    return {"created_at": created_at, "data": data}


T1 = datetime(2026, 1, 1, 0, 0, 0)
T2 = datetime(2026, 1, 1, 0, 5, 0)
T3 = datetime(2026, 1, 1, 0, 10, 0)


def test_host_metric_trend_returns_chronological_points():

    records = [
        _record(T3, {"monitoring": {"metrics": {"cpu_percent": 30.0}}}),
        _record(T2, {"monitoring": {"metrics": {"cpu_percent": 20.0}}}),
        _record(T1, {"monitoring": {"metrics": {"cpu_percent": 10.0}}}),
    ]

    assert host_metric_trend(records, "cpu_percent") == [
        (T1, 10.0), (T2, 20.0), (T3, 30.0)
    ]


def test_host_metric_trend_skips_rows_with_no_monitoring_data():

    records = [
        _record(T2, {"monitoring": {"metrics": {"cpu_percent": 20.0}}}),
        _record(T1, {"system": {"hostname": "sentinel"}}),
    ]

    assert host_metric_trend(records, "cpu_percent") == [(T2, 20.0)]


def test_host_metric_trend_skips_none_values():

    records = [
        _record(T2, {"monitoring": {"metrics": {"cpu_percent": 20.0}}}),
        _record(T1, {"monitoring": {"metrics": {"cpu_percent": None}}}),
    ]

    assert host_metric_trend(records, "cpu_percent") == [(T2, 20.0)]


def test_container_metric_trend_returns_chronological_points():

    records = [
        _record(
            T2,
            {"monitoring": {"containers": {"plex": {"cpu_percent": 15.0}}}}
        ),
        _record(
            T1,
            {"monitoring": {"containers": {"plex": {"cpu_percent": 5.0}}}}
        ),
    ]

    assert container_metric_trend(records, "plex", "cpu_percent") == [
        (T1, 5.0), (T2, 15.0)
    ]


def test_container_metric_trend_skips_containers_missing_from_a_row():

    records = [
        _record(
            T2,
            {"monitoring": {"containers": {"plex": {"cpu_percent": 15.0}}}}
        ),
        _record(
            T1,
            {"monitoring": {"containers": {"sonarr": {"cpu_percent": 5.0}}}}
        ),
    ]

    assert container_metric_trend(records, "plex", "cpu_percent") == [
        (T2, 15.0)
    ]


def test_known_container_names_unions_across_rows_without_duplicates():

    records = [
        _record(
            T2,
            {"monitoring": {"containers": {
                "plex": {}, "sonarr": {}
            }}}
        ),
        _record(
            T1,
            {"monitoring": {"containers": {"plex": {}}}}
        ),
    ]

    assert known_container_names(records) == ["plex", "sonarr"]


def test_known_container_names_empty_when_no_monitoring_data():

    records = [_record(T1, {"system": {"hostname": "sentinel"}})]

    assert known_container_names(records) == []
