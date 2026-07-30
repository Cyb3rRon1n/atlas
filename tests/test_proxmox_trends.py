from datetime import datetime

from atlas.proxmox.trends import guest_metric_trend, known_guests


def _record(created_at, data):

    return {"created_at": created_at, "data": data}


T1 = datetime(2026, 1, 1, 0, 0, 0)
T2 = datetime(2026, 1, 1, 0, 5, 0)
T3 = datetime(2026, 1, 1, 0, 10, 0)


def _guest(vmid, name="plex", cpu=0.1, maxcpu=4, mem=1_000_000, maxmem=4_000_000):

    return {
        "vmid": vmid, "name": name, "cpu": cpu, "maxcpu": maxcpu,
        "mem": mem, "maxmem": maxmem
    }


def test_guest_metric_trend_normalizes_cpu_to_percent_of_one_core():

    records = [
        _record(T1, {"virtualization": {"guests": [_guest(100, cpu=0.25)]}}),
    ]

    assert guest_metric_trend(records, 100, "cpu_percent") == [(T1, 25.0)]


def test_guest_metric_trend_normalizes_memory_to_percent_of_own_allocation():

    records = [
        _record(
            T1,
            {"virtualization": {"guests": [
                _guest(100, mem=1_000_000, maxmem=4_000_000)
            ]}}
        ),
    ]

    assert guest_metric_trend(records, 100, "memory_percent") == [(T1, 25.0)]


def test_guest_metric_trend_handles_missing_maxmem_without_raising():

    records = [
        _record(
            T1,
            {"virtualization": {"guests": [
                {"vmid": 100, "name": "plex", "cpu": 0.1, "mem": 1000, "maxmem": 0}
            ]}}
        ),
    ]

    assert guest_metric_trend(records, 100, "memory_percent") == []


def test_guest_metric_trend_returns_chronological_points():

    records = [
        _record(T3, {"virtualization": {"guests": [_guest(100, cpu=0.30)]}}),
        _record(T2, {"virtualization": {"guests": [_guest(100, cpu=0.20)]}}),
        _record(T1, {"virtualization": {"guests": [_guest(100, cpu=0.10)]}}),
    ]

    assert guest_metric_trend(records, 100, "cpu_percent") == [
        (T1, 10.0), (T2, 20.0), (T3, 30.0)
    ]


def test_guest_metric_trend_skips_rows_with_no_virtualization_data():

    records = [
        _record(T2, {"virtualization": {"guests": [_guest(100, cpu=0.2)]}}),
        _record(T1, {"monitoring": {"metrics": {"cpu_percent": 50.0}}}),
    ]

    assert guest_metric_trend(records, 100, "cpu_percent") == [(T2, 20.0)]


def test_guest_metric_trend_skips_guests_missing_from_a_row():

    records = [
        _record(T2, {"virtualization": {"guests": [_guest(100, cpu=0.2)]}}),
        _record(T1, {"virtualization": {"guests": [_guest(101, cpu=0.5)]}}),
    ]

    assert guest_metric_trend(records, 100, "cpu_percent") == [(T2, 20.0)]


def test_guest_metric_trend_matches_by_vmid_not_name():

    records = [
        _record(
            T1,
            {"virtualization": {"guests": [_guest(100, name="renamed", cpu=0.4)]}}
        ),
    ]

    assert guest_metric_trend(records, 100, "cpu_percent") == [(T1, 40.0)]
    assert guest_metric_trend(records, "100", "cpu_percent") == [(T1, 40.0)]


def test_known_guests_unions_across_rows_without_duplicates():

    records = [
        _record(
            T2,
            {"virtualization": {"guests": [
                _guest(100, name="plex"), _guest(101, name="sonarr")
            ]}}
        ),
        _record(
            T1,
            {"virtualization": {"guests": [_guest(100, name="plex")]}}
        ),
    ]

    assert known_guests(records) == {"100": "plex", "101": "sonarr"}


def test_known_guests_sorted_numerically_by_vmid():

    records = [
        _record(
            T1,
            {"virtualization": {"guests": [
                _guest(101, name="sonarr"), _guest(2, name="plex")
            ]}}
        ),
    ]

    assert list(known_guests(records).keys()) == ["2", "101"]


def test_known_guests_empty_when_no_virtualization_data():

    records = [_record(T1, {"system": {"hostname": "sentinel"}})]

    assert known_guests(records) == {}
