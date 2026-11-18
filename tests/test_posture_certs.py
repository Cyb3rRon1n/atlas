import socket
import ssl
import threading
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from lanxang.config.models import AtlasConfig
from lanxang.posture.certs import assess, due, fetch, hosts, level, run
from lanxang.posture.model import build_posture
from lanxang.posture.store import PostureStore
from lanxang.web.posture_page import render_posture_page

NOW = datetime(2026, 11, 15, 12, 0)
UTC = NOW.replace(tzinfo=timezone.utc)


def result(days, error=""):
    return {"expires": UTC + timedelta(days=days), "issuer": "Test CA", "error": error}


def test_hosts_from_routes_plus_extra_skip_wildcards():
    routes = [{"hosts": ["Media.example.org", "*.example.org"]}, {"hosts": ["{sub:[a-z]+}.example.org"]},
              {"hosts": ["media.example.org"]}]
    assert hosts(routes, ["mail.example.org ", ""]) == ["mail.example.org", "media.example.org"]


def test_levels():
    assert level(result(60), UTC, 14, 3) == ("ok", 60)
    assert level(result(10), UTC, 14, 3) == ("soon", 10)
    assert level(result(2), UTC, 14, 3) == ("urgent", 2)
    assert level(result(-1), UTC, 14, 3) == ("urgent", -1)
    assert level(result(60, "invalid: hostname mismatch"), UTC, 14, 3) == ("invalid", 60)
    assert level(result(1, "invalid: self-signed"), UTC, 14, 3)[0] == "urgent"     # expiring beats untrusted
    unreachable = {"expires": None, "issuer": "", "error": "unreachable: timed out"}
    assert level(unreachable, UTC, 14, 3) == ("unreachable", None)


def test_alert_once_per_worse_level_then_resolve():
    texts, state = assess({}, {"a.example.org": result(60)}, UTC, 14, 3)
    assert texts == []
    texts, state = assess(state, {"a.example.org": result(13)}, UTC, 14, 3)
    assert len(texts) == 1 and "expires in 13 days: a.example.org" in texts[0] and "Test CA" in texts[0]
    texts, state = assess(state, {"a.example.org": result(12)}, UTC, 14, 3)
    assert texts == []                                             # same level: quiet
    texts, state = assess(state, {"a.example.org": result(0)}, UTC, 14, 3)
    assert len(texts) == 1 and "expires today" in texts[0] and "🔴" in texts[0]
    texts, state = assess(state, {"a.example.org": {"expires": None, "issuer": "", "error": "unreachable: x"}},
                          UTC, 14, 3)
    assert texts == [] and state["a.example.org"]["alerted"] == "urgent"      # outage: no alert, memory kept
    texts, state = assess(state, {"a.example.org": result(89)}, UTC, 14, 3)
    assert texts == ["**✅ Resolved: certificate for a.example.org**\n• valid for 89 more days"]
    assert state["a.example.org"]["alerted"] is None


def test_untrusted_cert_alerts():
    texts, _ = assess({}, {"b.example.org": result(80, "invalid: Hostname mismatch")}, UTC, 14, 3)
    assert len(texts) == 1 and "not trusted: b.example.org" in texts[0] and "Hostname mismatch" in texts[0]


def test_due_once_a_day():
    assert due({}, NOW)
    assert not due({"checked_at": (NOW - timedelta(hours=23)).isoformat()}, NOW)
    assert due({"checked_at": (NOW - timedelta(hours=24)).isoformat()}, NOW)


def self_signed(tmp_path, days):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Atlas Test")])
    start = datetime.now(timezone.utc) - timedelta(days=1)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(start)
            .not_valid_after(start + timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_path, key_path, cert.not_valid_after_utc


def test_fetch_reads_expiry_of_a_real_untrusted_cert(tmp_path):
    cert_path, key_path, expires = self_signed(tmp_path, 30)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    def serve():
        for _ in range(2):                         # verified attempt, then the loose re-read
            conn, _ = listener.accept()
            try:
                with context.wrap_socket(conn, server_side=True):
                    pass
            except (ssl.SSLError, OSError):
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    got = fetch("localhost", port, timeout=5)
    thread.join(5)
    listener.close()
    assert got["error"].startswith("invalid:") and got["expires"] == expires and got["issuer"] == "Atlas Test"
    assert fetch("localhost", port, timeout=1)["error"].startswith("unreachable:")


def test_run_daily_alerts_and_posture_payload(temp_db):
    store, sent = PostureStore(temp_db), []
    store.save_routes([{"name": "media", "hosts": ["media.example.org"], "entrypoints": [],
                        "protection": "authelia", "provider": "docker"}], NOW)
    settings = AtlasConfig(security={"cert_hosts": ["mail.example.org"]})
    answers = {"media.example.org": result(5), "mail.example.org": result(200)}
    get = lambda host, timeout: answers[host]
    texts, detail = run(settings, store, NOW, get=get, send=sent.append)
    assert len(sent) == 1 and "media.example.org" in sent[0] and set(detail["hosts"]) == set(answers)
    assert run(settings, store, NOW + timedelta(hours=2), get=get, send=sent.append) == ([], detail)  # not due
    assert build_posture(store, NOW)["certs"]["media.example.org"]["level"] == "soon"
    assert "certNote" in render_posture_page()


def test_cert_watch_settings():
    security = AtlasConfig(security={"cert_watch": False, "cert_warn_days": 30}).security
    assert security.cert_watch is False and security.cert_warn_days == 30 and security.cert_urgent_days == 3
