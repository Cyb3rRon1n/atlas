"""
Built-in sign-in for lanxang web (web.auth: builtin, the default). One admin
password, hashed with scrypt; a signed, expiring session cookie (no session
store, so a restart keeps people signed in and a password change signs
everyone out); a read-only API token for dashboards such as Homepage; and a
one-time setup code so the first person to open the page can't claim it
without access to the host. Stdlib only.

web.auth: proxy turns all of this off for installs behind Authelia, Authentik
or similar - the proxy is then the auth boundary, as before.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path


AUTH_FILE = Path("inventory/auth.json")    # next to atlas.db, in the data volume

COOKIE = "atlas_session"

SESSION_SECONDS = 30 * 24 * 3600

MIN_PASSWORD = 8

MAX_FAILS = 5            # failed sign-ins per client ...

FAIL_WINDOW = 300        # ... per 5 minutes, then 429 until the window passes


def hash_password(password, salt=None):

    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1)

    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password, stored):

    try:
        scheme, salt, _ = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)
    except ValueError:
        return False


class Auth:

    def __init__(self, path=AUTH_FILE):

        self.path = Path(path)
        self._fails = {}
        self._lock = threading.Lock()

    def _load(self):

        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, data):

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle)
        os.replace(temp, self.path)

    def configured(self):

        return bool(self._load().get("password"))

    def setup_code(self):
        """The one-time code /setup asks for; printed in the log and by `lanxang auth setup-code`."""

        with self._lock:
            data = self._load()
            if not data.get("setup_code"):
                data["setup_code"] = secrets.token_hex(4)
                self._save(data)
            return data["setup_code"]

    def check_setup_code(self, code):

        expected = self._load().get("setup_code") or ""

        return bool(expected) and hmac.compare_digest(expected, (code or "").strip().lower())

    def set_password(self, password):
        """New hash and a new signing secret, so every existing session ends."""

        if len(password or "") < MIN_PASSWORD:
            raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
        with self._lock:
            data = self._load()
            data.update(password=hash_password(password), secret=secrets.token_hex(32))
            data.pop("setup_code", None)
            data.setdefault("token", secrets.token_urlsafe(32))
            self._save(data)

    def end_sessions(self):
        """A new signing secret: every session cookie, copied or not, stops working (Sign out)."""

        with self._lock:
            data = self._load()
            if data.get("secret"):
                data["secret"] = secrets.token_hex(32)
                self._save(data)

    def token(self, new=False):

        with self._lock:
            data = self._load()
            if new or not data.get("token"):
                data["token"] = secrets.token_urlsafe(32)
                self._save(data)
            return data["token"]

    def valid_token(self, value):

        token = self._load().get("token") or ""

        return bool(token and value) and hmac.compare_digest(token, value)

    def _sign(self, secret, expiry):

        return hmac.new(secret.encode(), str(expiry).encode(), hashlib.sha256).hexdigest()

    def session(self, now=None):

        expiry = int(now if now is not None else time.time()) + SESSION_SECONDS

        return f"{expiry}.{self._sign(self._load()['secret'], expiry)}"

    def valid_session(self, value, now=None):

        secret = self._load().get("secret")
        expiry, _, signature = (value or "").partition(".")
        if not secret or not expiry.isdigit():
            return False

        return (int(expiry) > (now if now is not None else time.time())
                and hmac.compare_digest(self._sign(secret, int(expiry)), signature))

    def limited(self, client, now=None):

        now = now if now is not None else time.time()
        with self._lock:
            recent = [t for t in self._fails.get(client, []) if now - t < FAIL_WINDOW]
            self._fails[client] = recent
            return len(recent) >= MAX_FAILS

    def login(self, password, client, now=None):
        """A session cookie value, None for a wrong password, or "limited" after too many failures."""

        now = now if now is not None else time.time()
        if self.limited(client, now):
            return "limited"
        if check_password(password or "", self._load().get("password")):
            with self._lock:
                self._fails.pop(client, None)
            return self.session(now)
        with self._lock:
            # drop clients whose failures have all aged out, so a stream of guesses from many addresses can't grow this
            self._fails = {c: times for c, times in self._fails.items() if times and now - times[-1] < FAIL_WINDOW}
            self._fails.setdefault(client, []).append(now)
        return None
