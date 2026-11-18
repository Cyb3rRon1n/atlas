# Lanxang is deliberately not a daemon (see docs/development/design-notes.md's "no daemon, no
# scheduled mode" — every command is on-demand, run when you want fresh
# data). This image doesn't add one either: it just runs `lanxang web`, the
# existing read-only dashboard, as a long-running foreground process — the
# same command you'd run on bare metal, containerized. Refreshing data
# (discover/monitor/proxmox scan) stays a separate, explicit command you
# run yourself — see README for the docker exec + optional host-cron recipe.
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/Cyb3rRon1n/lanxang" \
      org.opencontainers.image.description="Lanxang - self-hosted watchdog for your home network" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# conntrack lists the kernel connection table for the posture page. The file
# capability lets the non-root lanxang user use NET_ADMIN (granted only to the
# atlas-scan service via cap_add) without running as root. lanxang-dhcp-python is
# a copy of the interpreter holding only cap_net_bind_service, used solely by
# `lanxang lan check` to hear DHCP offers on UDP port 68.
RUN apt-get update \
    && apt-get install -y --no-install-recommends conntrack libcap2-bin snmp \
    && setcap cap_net_admin+ep /usr/sbin/conntrack \
    && cp "$(readlink -f /usr/local/bin/python3)" /usr/local/bin/lanxang-dhcp-python \
    && setcap cap_net_bind_service+ep /usr/local/bin/lanxang-dhcp-python \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY lanxang/ lanxang/
RUN pip install ".[alerts]"   # alerts = Apprise (100+ notification services)

RUN useradd --create-home --uid 10001 lanxang \
    && mkdir -p /data/inventory \
    && chown -R lanxang /data
USER lanxang
WORKDIR /data

EXPOSE 8420
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8420/healthz', timeout=2)"

CMD ["lanxang", "web", "--host", "0.0.0.0"]
