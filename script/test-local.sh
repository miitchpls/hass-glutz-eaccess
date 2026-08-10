#!/usr/bin/env bash
# Reproduce the GitHub Actions test pipeline locally.
#
# If HA_CORE_DIR is not set, clones HA core at the pinned ref into a temp
# directory, runs the tests, then removes it on exit.
#
# Usage:
#   script/test-local.sh                          # quiet setup, show only test output
#   script/test-local.sh -v                       # verbose setup output
#   HA_CORE_DIR=~/Workspace/core script/test-local.sh  # use existing clone
#   script/test-local.sh -- -x                    # pass extra flags to pytest

set -euo pipefail

INTEGRATION="glutz_eaccess"
HA_CORE_REF="2026.2.3"
VERBOSE=0
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        --) shift; PYTEST_ARGS+=("$@"); break ;;
        *) PYTEST_ARGS+=("$1"); shift ;;
    esac
done

log() { [[ $VERBOSE -eq 1 ]] && echo "==> $*" || true; }

spin() {
    local msg="$1"; shift
    if [[ $VERBOSE -eq 1 ]]; then
        "$@"
        return
    fi
    "$@" &>/dev/null &
    local pid=$!
    local i=0
    local spinner='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local gray='\033[90m' green='\033[32m' reset='\033[0m'
    while kill -0 "$pid" 2>/dev/null; do
        echo -ne "\r${gray}${spinner:$((i % ${#spinner})):1}  $msg${reset}"
        (( i++ )) || true
        sleep 0.08
    done
    wait "$pid"
    echo -ne "\r\033[K"
    echo -e "${gray}$msg ... ${green}done${reset}"
}

run() { [[ $VERBOSE -eq 1 ]] && "$@" || "$@" &>/dev/null; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_TEMP_CORE_DIR=""

if ! command -v uv &>/dev/null; then
    log "Installing uv"
    spin "Installing uv" bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
    source "$HOME/.local/bin/env"
fi

_install_ha_core() {
    uv venv --python 3.13 "${HA_CORE_DIR}/.venv"
    cd "${HA_CORE_DIR}"
    source .venv/bin/activate
    UV_CONSTRAINT=homeassistant/package_constraints.txt uv pip install -r requirements.txt
    grep -v '^mypy-dev' requirements_test.txt > requirements_test_filtered.txt
    UV_CONSTRAINT=homeassistant/package_constraints.txt uv pip install -r requirements_test_filtered.txt
    UV_CONSTRAINT=homeassistant/package_constraints.txt uv pip install -e . --no-deps
    UV_CONSTRAINT=homeassistant/package_constraints.txt uv pip install "pyglutz-eaccess==0.2.3"
}

if [[ -z "${HA_CORE_DIR:-}" ]]; then
    _TEMP_CORE_DIR="$(mktemp -d)"
    HA_CORE_DIR="${_TEMP_CORE_DIR}/ha_core"
    cleanup() { rm -rf "${_TEMP_CORE_DIR}"; }
    trap cleanup EXIT

    log "Cloning HA core ${HA_CORE_REF} into temp dir"
    spin "Cloning HA core ${HA_CORE_REF}" \
        git clone --depth 1 --branch "${HA_CORE_REF}" \
        https://github.com/home-assistant/core.git "${HA_CORE_DIR}"

    log "Installing HA core + test requirements"
    spin "Installing dependencies (this may take a few minutes)" \
        bash -c "$(declare -f _install_ha_core); HA_CORE_DIR='${HA_CORE_DIR}' _install_ha_core"
else
    if [[ ! -d "${HA_CORE_DIR}/homeassistant/components" ]]; then
        echo "Error: ${HA_CORE_DIR} doesn't look like a Home Assistant core checkout." >&2
        exit 1
    fi
fi

_sync_and_compile() {
    rsync -a --delete \
        --exclude '__pycache__' --exclude 'brand' \
        --exclude 'glutz_eaccess' --exclude 'translations' \
        "${REPO_ROOT}/homeassistant/components/${INTEGRATION}/" \
        "${HA_CORE_DIR}/homeassistant/components/${INTEGRATION}/"
    mkdir -p "${HA_CORE_DIR}/tests/components/${INTEGRATION}"
    rsync -a --delete --exclude '__pycache__' \
        "${REPO_ROOT}/tests/components/${INTEGRATION}/" \
        "${HA_CORE_DIR}/tests/components/${INTEGRATION}/"
    cd "${HA_CORE_DIR}"
    source .venv/bin/activate
    python -m script.translations develop --all
}

log "Syncing files and compiling translations"
spin "Preparing" \
    bash -c "$(declare -f _sync_and_compile); REPO_ROOT='${REPO_ROOT}' HA_CORE_DIR='${HA_CORE_DIR}' INTEGRATION='${INTEGRATION}' _sync_and_compile"

( cd "${HA_CORE_DIR}" && source .venv/bin/activate && pytest "tests/components/${INTEGRATION}/" -q --durations=10 "${PYTEST_ARGS[@]}" )

# Copy updated snapshots back to the repo if --snapshot-update was passed
for arg in "${PYTEST_ARGS[@]:-}"; do
    if [[ "$arg" == "--snapshot-update" ]]; then
        rsync -a \
            "${HA_CORE_DIR}/tests/components/${INTEGRATION}/snapshots/" \
            "${REPO_ROOT}/tests/components/${INTEGRATION}/snapshots/"
        echo "Snapshots updated in repo."
        break
    fi
done
