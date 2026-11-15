from atlas.wiring.health import alerts, assess


def counters(**values):
    base = {"in_errors": 0, "out_errors": 0, "fcs": 0, "align": 0, "late": 0, "packets": 1_000_000,
            "duplex": "full", "last_change": 100}
    return {**base, **values}


def scan(port="gi5", up=True, speed=1000, **values):
    return {"switches": {"core-switch": {"name": "core-switch", "ports": {
        port: {"index": 5, "up": up, "speed": speed, "counters": counters(**values)}}}}, "unifi": None}


def kinds(issues):
    return {(i["kind"], i["level"]) for i in issues}


def test_healthy_port_and_first_scan_are_quiet():
    assert assess(scan(), []) == []
    assert assess(scan(packets=2_000_000), [scan()]) == []


def test_growing_crc_errors_mean_a_bad_cable():
    before = scan(fcs=10, packets=1_000_000)
    issues = assess(scan(fcs=510, align=20, packets=1_100_000), [before])
    assert kinds(issues) == {("crc", "bad")}
    assert "520 CRC errors" in issues[0]["detail"] and "0.52%" in issues[0]["detail"]


def test_a_trickle_of_crc_errors_is_only_watch_or_nothing():
    before = scan(packets=1_000_000)
    assert kinds(assess(scan(fcs=50, packets=1_200_000), [before])) == {("crc", "watch")}   # 0.025%
    assert assess(scan(fcs=5, packets=1_200_000), [before]) == []                            # below CRC_MIN
    assert assess(scan(fcs=20, packets=100_000_000), [before]) == []                         # 0.00002%


def test_no_etherlike_counters_falls_back_to_input_errors():
    before = scan(fcs=None, align=None, in_errors=0)
    issues = assess(scan(fcs=None, align=None, in_errors=900, packets=1_100_000), [before])
    assert kinds(issues) == {("crc", "bad")}


def test_counter_reset_after_a_switch_reboot_is_not_an_error():
    before = scan(fcs=5000, packets=9_000_000, last_change=900)
    assert assess(scan(fcs=3, packets=10_000, last_change=50), [before]) == []


def test_duplex_mismatch():
    assert kinds(assess(scan(duplex="half"), [])) == {("duplex", "bad")}
    assert kinds(assess(scan(late=12), [scan()])) == {("duplex", "bad")}
    assert kinds(assess(scan(duplex="half", late=12), [scan(duplex="half")])) == {("duplex", "bad")}


def test_speed_drop_against_history_and_flap_are_watch_only():
    history = [scan(speed=100), scan(speed=1000)]
    issues = assess(scan(speed=100), history)
    assert kinds(issues) == {("speed", "watch")} and "ran at 1 Gbit/s" in issues[0]["detail"]
    assert kinds(assess(scan(last_change=777), [scan(last_change=100)])) == {("flap", "watch")}


def test_down_ports_and_stale_sources_are_skipped():
    assert assess(scan(up=False, duplex="half"), []) == []
    assert assess(scan(duplex="half"), [], stale={"core-switch"}) == []


def test_unifi_ports_are_checked_too():
    def unifi(errors):
        return {"switches": {}, "unifi": {"devices": [{"name": "gateway", "ports": {"Port 2": {
            "up": True, "speed": 2500, "counters": counters(fcs=None, align=None, in_errors=errors)}}}]}}
    issues = assess(unifi(5000), [unifi(0)])
    assert issues[0]["device"] == "gateway" and issues[0]["port"] == "Port 2" and issues[0]["kind"] == "crc"


def test_alerts_once_per_problem_and_on_recovery():
    bad = assess(scan(duplex="half"), [])
    watch = assess(scan(speed=100), [scan(speed=1000)])
    assert alerts([], watch) == []                               # watch never alerts
    first = alerts([], bad)
    assert len(first) == 1 and "Duplex mismatch: core-switch gi5" in first[0]
    assert alerts(bad, bad) == []                                # still bad: no repeat
    assert "healthy again" in alerts(bad, [])[0]
