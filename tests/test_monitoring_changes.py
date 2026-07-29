from atlas.monitoring.changes import diff_monitoring, format_change


THRESHOLDS = {"cpu_percent": 90.0, "memory_percent": 90.0}


def test_no_changes_when_no_previous_baseline():

    current = {"metrics": {"cpu_percent": 95.0}, "containers": {}}

    assert diff_monitoring(None, current, THRESHOLDS) == []
    assert diff_monitoring({}, current, THRESHOLDS) == []


def test_no_changes_when_nothing_differs():

    snapshot = {
        "metrics": {"cpu_percent": 95.0},
        "containers": {"plex": {"cpu_percent": 10.0}}
    }

    assert diff_monitoring(snapshot, snapshot, THRESHOLDS) == []


def test_host_metric_crossed():

    previous = {"metrics": {"cpu_percent": 50.0}, "containers": {}}
    current = {"metrics": {"cpu_percent": 95.0}, "containers": {}}

    assert diff_monitoring(previous, current, THRESHOLDS) == [
        {"type": "host_metric_crossed", "metric": "cpu_percent"}
    ]


def test_host_metric_recovered():

    previous = {"metrics": {"cpu_percent": 95.0}, "containers": {}}
    current = {"metrics": {"cpu_percent": 50.0}, "containers": {}}

    assert diff_monitoring(previous, current, THRESHOLDS) == [
        {"type": "host_metric_recovered", "metric": "cpu_percent"}
    ]


def test_container_metric_crossed():

    previous = {
        "metrics": {},
        "containers": {"plex": {"cpu_percent": 10.0}}
    }
    current = {
        "metrics": {},
        "containers": {"plex": {"cpu_percent": 95.0}}
    }

    assert diff_monitoring(previous, current, THRESHOLDS) == [
        {
            "type": "container_metric_crossed",
            "container": "plex",
            "metric": "cpu_percent"
        }
    ]


def test_container_metric_recovered():

    previous = {
        "metrics": {},
        "containers": {"plex": {"cpu_percent": 95.0}}
    }
    current = {
        "metrics": {},
        "containers": {"plex": {"cpu_percent": 10.0}}
    }

    assert diff_monitoring(previous, current, THRESHOLDS) == [
        {
            "type": "container_metric_recovered",
            "container": "plex",
            "metric": "cpu_percent"
        }
    ]


def test_new_container_with_metric_already_over_threshold_counts_as_crossed():
    """
    A container with no previous snapshot is treated as previously
    under threshold (was_exceeded defaults to False) - its first
    sighting over threshold is itself a crossing worth flagging.
    """

    previous = {"metrics": {}, "containers": {}}
    current = {
        "metrics": {},
        "containers": {"plex": {"cpu_percent": 95.0}}
    }

    assert diff_monitoring(previous, current, THRESHOLDS) == [
        {
            "type": "container_metric_crossed",
            "container": "plex",
            "metric": "cpu_percent"
        }
    ]


def test_metric_with_no_configured_threshold_is_ignored():

    previous = {"metrics": {"disk_percent": 10.0}, "containers": {}}
    current = {"metrics": {"disk_percent": 95.0}, "containers": {}}

    assert diff_monitoring(previous, current, {}) == []


def test_format_change_renders_each_type():

    assert format_change(
        {"type": "host_metric_crossed", "metric": "cpu_percent"}
    ) == "! Host cpu_percent crossed threshold"

    assert format_change(
        {"type": "host_metric_recovered", "metric": "cpu_percent"}
    ) == "✓ Host cpu_percent back under threshold"

    assert format_change(
        {
            "type": "container_metric_crossed",
            "container": "plex",
            "metric": "cpu_percent"
        }
    ) == "! Container 'plex' cpu_percent crossed threshold"

    assert format_change(
        {
            "type": "container_metric_recovered",
            "container": "plex",
            "metric": "cpu_percent"
        }
    ) == "✓ Container 'plex' cpu_percent back under threshold"

    assert format_change({"type": "unknown_type"}) == (
        "? Unknown change: {'type': 'unknown_type'}"
    )
