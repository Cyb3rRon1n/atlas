"""
Alerts to every channel set under notify: in the config file — Signal, ntfy,
webhooks (Discord / Slack / plain JSON), email, and Apprise URLs when the
apprise package is installed (it is in the Docker image).

Messages are written once in light Markdown: the first line is the
headline, **bold** marks names. Each channel gets the form it understands.
A channel that fails never stops the others; send() reports success when
at least one channel took the message, so callers mark it delivered once.
Secrets can come from the environment instead of the config file:
LANXANG_NTFY_TOKEN, LANXANG_SMTP_PASSWORD.
"""

import json
import os
import re
import smtplib
import urllib.request
from email.message import EmailMessage

from lanxang.config.local import config_name
from lanxang.devices.notify import send_signal


TIMEOUT = 15


def _plain(text):

    return text.replace("**", "")


def _title(text):

    return _plain(text.strip().splitlines()[0]).strip() if text.strip() else "Lanxang"


def _body(text):
    """Everything after the headline (which goes in the title), or the headline if that's all."""

    rest = text.strip().split("\n", 1)

    return (rest[1].strip() if len(rest) > 1 else "") or _title(text)


def _post_json(url, payload, headers=None):

    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
    urllib.request.urlopen(request, timeout=TIMEOUT)


def send_ntfy(config, text):

    token = config.token or os.environ.get("LANXANG_NTFY_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    _post_json(config.url.rstrip("/"), {"topic": config.topic, "title": _title(text), "message": _body(text),
                                        "markdown": True, "tags": ["atlas"]}, headers)


def webhook_payload(url, text):
    """Discord and Slack get their own shapes; anything else plain JSON."""

    if re.match(r"https://(\w+\.)?discord(app)?\.com/api/webhooks/", url):
        return {"content": text[:2000]}
    if url.startswith("https://hooks.slack.com/"):
        return {"text": text.replace("**", "*")}

    return {"title": _title(text), "text": _plain(text), "source": "atlas"}


def send_webhook(url, text):

    _post_json(url, webhook_payload(url, text))


def send_email(config, text):

    message = EmailMessage()
    message["Subject"] = f"Lanxang: {_title(text)}"
    message["From"] = config.sender or config.user
    message["To"] = ", ".join(config.to)
    message.set_content(_plain(text))
    password = config.password or os.environ.get("LANXANG_SMTP_PASSWORD", "")

    smtp = smtplib.SMTP_SSL if config.port == 465 else smtplib.SMTP
    with smtp(config.host, config.port, timeout=TIMEOUT) as server:
        if config.port != 465 and config.starttls:
            server.starttls()
        if config.user:
            server.login(config.user, password)
        server.send_message(message)


def send_apprise(urls, text):

    try:
        import apprise
    except ImportError:
        raise RuntimeError("apprise isn't installed (pip install apprise; the Docker image has it)")
    sender = apprise.Apprise()
    for url in urls:
        sender.add(url)
    if not sender.notify(title=_title(text), body=_body(text), body_format=apprise.NotifyFormat.MARKDOWN):
        raise RuntimeError("apprise couldn't deliver to any of its URLs")


def channels(config):
    """[(name, send(text) -> None, raising on failure)] for every configured channel."""

    found = []
    if config.signal.url:
        def signal(text):
            ok, error = send_signal(config.signal, text)
            if not ok:
                raise RuntimeError(error)
        found.append(("signal", signal))
    if config.ntfy.url and config.ntfy.topic:
        found.append(("ntfy", lambda text: send_ntfy(config.ntfy, text)))
    for url in config.webhooks:
        label = "discord" if "discord" in url else "slack" if "hooks.slack.com" in url else "webhook"
        found.append((label, lambda text, url=url: send_webhook(url, text)))
    if config.email.host and config.email.to:
        found.append(("email", lambda text: send_email(config.email, text)))
    if config.apprise:
        found.append(("apprise", lambda text: send_apprise(config.apprise, text)))

    return found


def configured(config):

    return bool(config) and bool(channels(config))


def send_each(config, text):
    """[(channel, ok, error)] - one try per channel."""

    results = []
    for name, deliver in channels(config):
        try:
            deliver(text)
            results.append((name, True, ""))
        except Exception as error:   # any channel failure is reported, never raised
            results.append((name, False, str(error)[:300] or type(error).__name__))

    return results


def send(config, text):
    """(ok, error) like send_signal: ok when at least one channel took it."""

    results = send_each(config, text)
    errors = [f"{name}: {error}" for name, ok, error in results if not ok]

    if not results:
        return False, f"no alert channels set (notify: in {config_name()})"

    return any(ok for _, ok, _ in results), "; ".join(errors)
