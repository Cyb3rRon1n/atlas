#!/usr/bin/env bash
# Lanxang installer: sets up ~/lanxang (compose file, .env, lanxang.yaml) and starts it.
# An existing ~/atlas install is upgraded in place and keeps working.
#
#   curl -fsSL https://raw.githubusercontent.com/Cyb3rRon1n/lanxang/main/install.sh | bash
#
# Rather read it first?
#   curl -fsSLO https://raw.githubusercontent.com/Cyb3rRon1n/lanxang/main/install.sh
#   less install.sh && bash install.sh
#
# Run it again to upgrade (keeps your .env and config file). Options:
#   --uninstall   stop Lanxang and remove it (asks before deleting data)
#   --yes         no questions: defaults, or the LANXANG_* values below
# Settings (environment): LANXANG_DIR (~/lanxang, or ~/atlas if that is already installed), LANXANG_PORT
# (8420), LANXANG_BIND (127.0.0.1 = this machine, 0.0.0.0 = whole LAN), LANXANG_AI (none|ollama|anthropic),
# LANXANG_OLLAMA_URL, ANTHROPIC_API_KEY, LANXANG_REF (release tag or branch to install), LANXANG_TAG (image
# tag, normally derived from LANXANG_REF).

set -euo pipefail

# Everything runs from main(), called on the last line: under `curl | bash` bash reads this script from
# stdin, so the whole file must be read before any docker command (which inherits stdin) can swallow the rest.
main() {

REPO="Cyb3rRon1n/lanxang"
DIR="${LANXANG_DIR:-}"
if [ -z "$DIR" ]; then
    DIR="$HOME/lanxang"
    [ -f "$HOME/atlas/docker-compose.yml" ] && DIR="$HOME/atlas"   # upgrade an old install in place
fi
SOURCE="${LANXANG_SOURCE:-}"
YES=0
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Questions read the terminal, not stdin: under `curl | bash` stdin is this script.
ask() {
    local prompt="$1" default="$2" reply=""
    if [ "$YES" = 1 ] || ! { : </dev/tty; } 2>/dev/null; then
        printf '%s\n' "$default"
        return
    fi
    read -r -p "$prompt [$default]: " reply </dev/tty || true
    printf '%s\n' "${reply:-$default}"
}

compose() { (cd "$DIR" && docker compose "$@"); }

# --- requirements -----------------------------------------------------------

command -v docker >/dev/null || die "Docker is not installed - see https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing (the 'docker compose' plugin)"
docker info >/dev/null 2>&1 || die "can't talk to Docker - is it running, and is $(id -un) in the docker group?"

# --- uninstall --------------------------------------------------------------

if [ "$UNINSTALL" = 1 ]; then
    [ -f "$DIR/docker-compose.yml" ] || die "no Lanxang install in $DIR"
    if [ "$(ask "Also delete Lanxang's data (inventory, history, password)? y/N" n)" = y ]; then
        compose down -v
        rm -rf "$DIR"
        say "Lanxang and its data are gone."
    else
        compose down
        say "Lanxang stopped. Your data and settings are kept in $DIR - run this installer again to bring it back."
    fi
    exit 0
fi

# --- what to install --------------------------------------------------------

fetch() {   # fetch <path in repo> <destination>
    if [ -n "$SOURCE" ]; then    # a local checkout (tests, offline installs)
        cp "$SOURCE/$1" "$2"
    else
        curl -fsSL "https://raw.githubusercontent.com/$REPO/$REF/$1" -o "$2"
    fi
}

if [ -n "${LANXANG_REF:-}" ]; then
    REF="$LANXANG_REF"
elif [ -n "$SOURCE" ]; then
    REF="main"
else
    REF=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
          | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1)
    REF="${REF:-main}"
fi
# image tags drop the v (v0.5.0 -> 0.5.0); a branch install runs :latest
case "$REF" in v[0-9]*) TAG="${REF#v}" ;; *) TAG="latest" ;; esac
TAG="${LANXANG_TAG:-$TAG}"

mkdir -p "$DIR"
UPGRADE=0
[ -f "$DIR/.env" ] && UPGRADE=1

say "Installing Lanxang $REF into $DIR"
[ -f "$DIR/docker-compose.yml" ] && cp "$DIR/docker-compose.yml" "$DIR/docker-compose.yml.bak"
fetch docker-compose.yml "$DIR/docker-compose.yml"
fetch lanxang.yaml.example "$DIR/lanxang.yaml.example"
fetch cabling.example.yaml "$DIR/cabling.example.yaml"

set_env() {   # set_env KEY VALUE - replace or append one line in .env
    local file="$DIR/.env"
    grep -v "^$1=" "$file" > "$file.tmp" || true
    printf '%s=%s\n' "$1" "$2" >> "$file.tmp"
    mv "$file.tmp" "$file"
    chmod 600 "$file"
}

if [ "$UPGRADE" = 1 ]; then
    say "Upgrade: keeping your .env and config file"
    # since 1.3 only the Lanxang names are read: move an older install's atlas.yaml and ATLAS_* settings over
    if [ -f "$DIR/atlas.yaml" ] && [ ! -f "$DIR/lanxang.yaml" ]; then
        mv "$DIR/atlas.yaml" "$DIR/lanxang.yaml"
        say "Renamed atlas.yaml to lanxang.yaml"
    fi
    if grep -q '[$]{ATLAS_' "$DIR/lanxang.yaml" 2>/dev/null; then
        cp -p "$DIR/lanxang.yaml" "$DIR/lanxang.yaml.before-1.3"
        sed 's/[$]{ATLAS_/${LANXANG_/g' "$DIR/lanxang.yaml.before-1.3" > "$DIR/lanxang.yaml"
        say "Renamed the \${ATLAS_...} references in lanxang.yaml (the old file is lanxang.yaml.before-1.3)"
    fi
    if [ -f "$DIR/.env" ] && grep -q '^ATLAS_' "$DIR/.env"; then
        cp -p "$DIR/.env" "$DIR/.env.before-1.3"
        sed -e 's/^ATLAS_/LANXANG_/' -e '/^LANXANG_CONFIG=/d' "$DIR/.env.before-1.3" > "$DIR/.env"
        say "Renamed the ATLAS_ settings in .env to LANXANG_ (the old file is .env.before-1.3)"
    fi
    set_env LANXANG_TAG "$TAG"
else
    port=$(ask "Port for the web page" "${LANXANG_PORT:-8420}")
    case "$port" in ''|*[!0-9]*) die "port must be a number" ;; esac
    access=$(ask "Who can open it? 1 = this machine only, 2 = anyone on your LAN (password protected)" \
                 "$([ "${LANXANG_BIND:-127.0.0.1}" = 0.0.0.0 ] && echo 2 || echo 1)")
    bind=127.0.0.1
    [ "$access" = 2 ] && bind=0.0.0.0
    ai=$(ask "AI assistant: none, ollama (your own server) or anthropic (API key)" "${LANXANG_AI:-none}")

    : > "$DIR/.env"   # set_env keeps it chmod 600; lanxang.yaml holds no secrets and must stay readable by the container
    set_env LANXANG_TAG "$TAG"
    set_env LANXANG_PORT "$port"
    set_env LANXANG_BIND "$bind"
    set_env LANXANG_CONFIG lanxang.yaml

    provider=none model="" ollama=http://localhost:11434
    case "$ai" in
        ollama)
            provider=ollama model=qwen3:8b
            # Lanxang runs in a container, so "localhost" would be the container itself
            lan_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
            ollama=$(ask "Ollama URL (as seen from Docker, not localhost)" \
                         "${LANXANG_OLLAMA_URL:-http://${lan_ip:-192.168.1.10}:11434}") ;;
        anthropic)
            provider=anthropic model=claude-opus-5
            key="${ANTHROPIC_API_KEY:-}"
            if [ -z "$key" ] && [ "$YES" = 0 ] && { : </dev/tty; } 2>/dev/null; then
                read -r -s -p "Anthropic API key (hidden): " key </dev/tty || true
                echo
            fi
            [ -n "$key" ] && set_env ANTHROPIC_API_KEY "$key" ;;
        none) ;;
        *) die "AI must be none, ollama or anthropic" ;;
    esac

    if [ ! -f "$DIR/lanxang.yaml" ]; then
        cat > "$DIR/lanxang.yaml" <<EOF
# Written by install.sh - lanxang.yaml.example shows every option. Alerts, the AI model and
# more can also be set on the web page's Setup tab; anything set here wins over it.
name: $(hostname -s 2>/dev/null || echo lanxang-node)
discovery:
  hardware: true
  storage: true
  network: true
$([ "$provider" = none ] || printf "intelligence:\n  provider: %s\n  model: '%s'\n  ollama_host: %s\n" "$provider" "$model" "$ollama")
web:
  auth: builtin        # proxy = an auth proxy in front of Lanxang signs people in instead
EOF
        chmod 644 "$DIR/lanxang.yaml"
    fi
fi

envval() {   # envval PORT - the LANXANG_ value from .env
    sed -n "s/^LANXANG_$1=//p" "$DIR/.env" | head -n1
}

# --- start ------------------------------------------------------------------

say "Pulling and starting Lanxang"
compose pull --quiet || say "Couldn't pull the image - starting with the copy already on this machine, if any"
compose up -d

port=$(envval PORT)
port="${port:-8420}"
for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$port/healthz" >/dev/null 2>&1 && break
    sleep 2
done
curl -fsS "http://127.0.0.1:$port/healthz" >/dev/null 2>&1 \
    || die "Lanxang didn't come up - see: cd $DIR && docker compose logs atlas"

if grep -q 'auth: *proxy' "$DIR/lanxang.yaml" 2>/dev/null; then
    :
elif compose exec -T atlas lanxang auth setup-code 2>/dev/null | grep -q 'already set'; then
    :
elif [ "$YES" = 0 ] && { : </dev/tty; } 2>/dev/null; then
    say "Choose the admin password for the web page"
    compose exec atlas lanxang auth password </dev/tty || say "Skipped - the page will ask for it with a setup code."
fi

code=$(compose exec -T atlas lanxang auth setup-code 2>/dev/null | tail -n1 || true)

echo
host=localhost
if [ "$(envval BIND)" = 0.0.0.0 ]; then
    host=$(hostname -I 2>/dev/null | awk '{print $1}')
    host="${host:-localhost}"
fi
say "Lanxang is running: http://$host:$port"
case "$code" in
    *already*|"") ;;
    *) echo "    First visit asks for this setup code: $code" ;;
esac
echo "    Settings: $DIR/lanxang.yaml (then: cd $DIR && docker compose up -d)"
echo "    Upgrade: run this installer again. Remove: bash install.sh --uninstall"
}

main "$@"
