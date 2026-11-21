import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from lanxang.web.auth import MAX_FAILS, SESSION_SECONDS, Auth, check_password, hash_password
from lanxang.web.server import AtlasWebHandler, safe_next


def test_password_hash_round_trip_and_salted():

    stored = hash_password("correct horse")

    assert check_password("correct horse", stored)
    assert not check_password("wrong horse", stored)
    assert hash_password("correct horse") != stored
    assert not check_password("x", "") and not check_password("x", "md5$aa$bb")


def test_auth_file_is_private_and_setup_code_is_one_time(tmp_path):

    auth = Auth(tmp_path / "inventory" / "auth.json")
    code = auth.setup_code()

    assert not auth.configured()
    assert auth.setup_code() == code
    assert oct(os.stat(auth.path).st_mode & 0o777) == "0o600"
    assert auth.check_setup_code(code.upper()) and not auth.check_setup_code("nope")

    with pytest.raises(ValueError):
        auth.set_password("short")
    auth.set_password("long enough")

    assert auth.configured() and not auth.check_setup_code(code)


def test_sessions_expire_and_end_on_password_change(tmp_path):

    auth = Auth(tmp_path / "auth.json")
    auth.set_password("first password")
    session = auth.session(now=1000)

    assert auth.valid_session(session, now=1001)
    assert not auth.valid_session(session, now=1000 + SESSION_SECONDS + 1)
    assert not auth.valid_session(session.replace(".", ".0"), now=1001)
    assert not auth.valid_session("garbage", now=1001)

    auth.set_password("second password")
    assert not auth.valid_session(session, now=1001)


def test_login_rate_limit_per_client(tmp_path):

    auth = Auth(tmp_path / "auth.json")
    auth.set_password("the password")

    for _ in range(MAX_FAILS):
        assert auth.login("bad", "10.0.0.9", now=50) is None
    assert auth.login("the password", "10.0.0.9", now=60) == "limited"
    assert auth.login("the password", "10.0.0.8", now=60) not in (None, "limited")
    assert auth.login("the password", "10.0.0.9", now=60 + 301) not in (None, "limited")


def test_token(tmp_path):

    auth = Auth(tmp_path / "auth.json")
    token = auth.token()

    assert auth.valid_token(token) and not auth.valid_token("") and not auth.valid_token(token + "x")
    assert auth.token(new=True) != token and not auth.valid_token(token)


def test_safe_next_blocks_open_redirects():

    assert safe_next("/devices?x=1") == "/devices?x=1"
    for bad in ("//evil.example", "https://evil.example", "/\\evil.example", "", None):
        assert safe_next(bad) == "/"


class _NoRedirect(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(_NoRedirect)


def _call(url, data=None, headers=None):

    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with OPENER.open(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, dict(error.headers), error.read().decode()


@pytest.fixture
def secured(temp_db, tmp_path):

    auth = Auth(tmp_path / "auth.json")
    handler = type("Handler", (AtlasWebHandler,), {"auth": auth})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{httpd.server_port}", auth
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()


def _form(base, path, fields, cookie=""):

    headers = {"Origin": base, "Content-Type": "application/x-www-form-urlencoded"}
    if cookie:
        headers["Cookie"] = cookie
    return _call(base + path, urllib.parse.urlencode(fields).encode(), headers)


def test_first_run_needs_the_setup_code(secured):

    base, auth = secured

    assert _call(base + "/healthz")[0] == 200
    status, headers, _ = _call(base + "/devices")
    assert status == 303 and headers["Location"] == "/setup"
    assert _call(base + "/api/summary")[0] == 401
    assert "Setup code" in _call(base + "/setup")[2]

    status, _, body = _form(base, "/setup", {"code": "wrong", "password": "a good password", "confirm": "a good password"})
    assert status == 403 and not auth.configured()

    code = auth.setup_code()
    assert _form(base, "/setup", {"code": code, "password": "a good password", "confirm": "different"})[0] == 400

    status, headers, _ = _form(base, "/setup", {"code": code, "password": "a good password", "confirm": "a good password"})
    assert status == 303 and auth.configured()
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Lax" in headers["Set-Cookie"]
    cookie = headers["Set-Cookie"].split(";")[0]
    assert _call(base + "/devices", headers={"Cookie": cookie})[0] == 200


def test_sign_in_sign_out_and_api_token(secured):

    base, auth = secured
    auth.set_password("a good password")

    status, headers, _ = _call(base + "/devices?x=1")
    assert status == 303 and headers["Location"] == "/login?next=/devices%3Fx%3D1"
    assert _call(base + "/static/elk.bundled.js")[0] == 200

    assert _form(base, "/login", {"password": "nope", "next": "/devices"})[0] == 401
    status, headers, _ = _form(base, "/login", {"password": "a good password", "next": "//evil.example"})
    assert status == 303 and headers["Location"] == "/"
    cookie = headers["Set-Cookie"].split(";")[0]

    assert _call(base + "/", headers={"Cookie": cookie})[0] == 200

    # JSON writes need the session, not the token
    token = auth.token()
    assert _call(base + "/api/summary", headers={"Authorization": f"Bearer {token}"})[0] == 200
    assert _call(base + "/api/summary", headers={"X-API-Key": token})[0] == 200
    assert _call(base + "/api/summary", headers={"Authorization": "Bearer wrong"})[0] == 401
    post = {"Origin": base, "Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    assert _call(base + "/api/wiring/refresh", b"{}", post)[0] == 401
    assert _call(base + "/api/wiring/refresh", b"{}", {**post, "Cookie": cookie})[0] in (400, 409)

    status, headers, _ = _form(base, "/logout", {}, cookie)
    assert status == 303 and "Max-Age=0" in headers["Set-Cookie"]
    # a copy of the old cookie no longer works after Sign out
    assert _call(base + "/", headers={"Cookie": cookie})[0] in (302, 303, 401)


def test_behind_a_proxy_wrong_passwords_count_per_visitor(secured):

    base, auth = secured
    auth.set_password("a good password")

    def login(password, visitor):
        fields = urllib.parse.urlencode({"password": password}).encode()
        return _call(base + "/login", fields, {"Origin": base, "X-Forwarded-For": f"203.0.113.9, {visitor}",
                                               "Content-Type": "application/x-www-form-urlencoded"})[0]

    assert [login("nope", "198.51.100.7") for _ in range(6)][-1] == 429     # the guesser is limited ...
    assert login("a good password", "192.0.2.20") == 303                    # ... the owner behind the same proxy isn't
    assert login("a good password", "not an address") == 303                # junk header: counted as the proxy itself


def test_proxy_mode_is_unchanged(running_server_open):

    status, _, body = _call(running_server_open + "/api/summary")

    assert status == 200 and json.loads(body)


@pytest.fixture
def running_server_open(temp_db):

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), AtlasWebHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()


def test_sign_out_button_only_with_builtin_auth(monkeypatch):

    from lanxang.web import render

    monkeypatch.setattr(render, "SIGN_OUT", False)
    assert "Sign out" not in render.render_page("T", "")
    monkeypatch.setattr(render, "SIGN_OUT", True)
    assert 'action="/logout"' in render.render_page("T", "")


def test_vendored_fonts_are_served_and_the_allow_list_holds(secured):

    base, auth = secured
    auth.set_password("a good password")

    for name in ("Lexend.woff2", "NotoSansLao-Medium.woff2"):
        with OPENER.open(base + "/static/fonts/" + name, timeout=5) as response:    # no sign-in needed
            assert response.status == 200 and response.headers["Content-Type"] == "font/woff2" and response.read()

    assert _call(base + "/static/fonts/../server.py")[0] == 404
    assert _call(base + "/static/fonts/x.woff2")[0] == 404


def test_sign_in_and_setup_pages_carry_the_brand():
    from lanxang.web.login_page import render_login_page, render_setup_page
    for page in (render_login_page(), render_setup_page()):
        assert 'class="brand"' in page and "Lanxang<small" in page and "ລ້ານຊ້າງ" in page and page.count("<svg") == 2
        assert '<svg width="44" height="44" aria-hidden="true"' in page                  # the text names it


def test_old_failures_are_forgotten(tmp_path):

    auth = Auth(tmp_path / "auth.json")
    auth.set_password("the password")
    for i in range(50):
        auth.login("bad", f"10.0.0.{i}", now=100)
    auth.login("bad", "10.0.1.1", now=100 + 301)
    assert list(auth._fails) == ["10.0.1.1"]


def test_pages_cannot_be_framed(secured):

    base, _ = secured
    with OPENER.open(base + "/static/fonts/Lexend.woff2", timeout=5) as response:
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Content-Security-Policy"] == "frame-ancestors 'none'"
