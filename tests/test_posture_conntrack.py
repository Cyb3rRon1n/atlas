import subprocess
from pathlib import Path

import pytest

from atlas.posture.collectors.conntrack import Flow, parse_conntrack, read_conntrack


SAMPLE = (Path(__file__).parent / "fixtures" / "posture" / "conntrack.txt").read_text()


def test_parses_tcp_tuple_bytes_and_id():
    flows = parse_conntrack(SAMPLE)
    first = flows[0]
    assert first == Flow(id=1001, proto="tcp", state="ESTABLISHED", src="100.64.0.10", dst="192.168.10.157",
                         sport=62456, dport=443, reply_src="172.18.0.9", reply_dst="100.64.0.10",
                         bytes_out=2048, bytes_in=8192)


def test_udp_has_no_state_and_unknown_proto_has_no_ports():
    flows = parse_conntrack(SAMPLE)
    udp = next(f for f in flows if f.id == 1004)
    assert (udp.proto, udp.state, udp.dport) == ("udp", "", 53)
    other = next(f for f in flows if f.id == 1007)
    assert (other.proto, other.sport, other.dport) == ("unknown", None, None)


def test_missing_accounting_means_zero_bytes():
    line = ("ipv4     2 tcp      6 10 ESTABLISHED src=10.0.0.1 dst=203.0.113.1 sport=1 dport=443 "
            "src=203.0.113.1 dst=10.0.0.1 sport=443 dport=1 [ASSURED] mark=0 use=1")
    (flow,) = parse_conntrack(line)
    assert (flow.bytes_out, flow.bytes_in, flow.id) == (0, 0, None)


def test_skips_summary_and_garbage_lines():
    text = SAMPLE + "conntrack v1.4.7 (conntrack-tools): 7 flow entries have been shown.\n\nnot a flow\n"
    assert len(parse_conntrack(text)) == 7


def test_read_conntrack_runs_extended_id_listing():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=SAMPLE, stderr="7 flow entries")

    assert len(read_conntrack(run=fake_run)) == 7
    assert calls == [["conntrack", "-L", "-o", "extended,id"]]


def test_read_conntrack_raises_with_stderr_on_failure():

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="Operation not permitted")

    with pytest.raises(RuntimeError, match="Operation not permitted"):
        read_conntrack(run=fake_run)
