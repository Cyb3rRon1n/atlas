# Atlas is deliberately not a daemon (see CLAUDE.md's "no daemon, no
# scheduled mode" — every command is on-demand, run when you want fresh
# data). This image doesn't add one either: it just runs `atlas web`, the
# existing read-only dashboard, as a long-running foreground process — the
# same command you'd run on bare metal, containerized. Refreshing data
# (discover/monitor/proxmox scan) stays a separate, explicit command you
# run yourself — see README for the docker exec + optional host-cron recipe.
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/Cyb3rRon1n/atlas" \
      org.opencontainers.image.description="Atlas - network map, inventory and ops assistant for self-hosted infrastructure" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# conntrack lists the kernel connection table for the posture page. The file
# capability lets the non-root atlas user use NET_ADMIN (granted only to the
# atlas-scan service via cap_add) without running as root.
RUN apt-get update \
    && apt-get install -y --no-install-recommends conntrack libcap2-bin \
    && setcap cap_net_admin+ep /usr/sbin/conntrack \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY atlas/ atlas/
RUN pip install .

RUN useradd --create-home --uid 10001 atlas \
    && mkdir -p /data/inventory \
    && chown -R atlas /data
USER atlas
WORKDIR /data

EXPOSE 8420
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8420/', timeout=2)"

CMD ["atlas", "web", "--host", "0.0.0.0"]
