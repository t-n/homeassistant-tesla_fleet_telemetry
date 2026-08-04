#!/usr/bin/with-contenv bashio

set -euo pipefail

if [ -f /run/tesla_fleet_gateway.env ]; then
    set -a
    # shellcheck source=/run/tesla_fleet_gateway.env
    source /run/tesla_fleet_gateway.env
    set +a
fi

REQUEST_FILE="${1:-}"

if [ -z "$REQUEST_FILE" ]; then
    bashio::log.error "usage: $0 <request-json-file>"
    exit 2
fi

if [ ! -f "$REQUEST_FILE" ]; then
    bashio::log.error "request file not found: $REQUEST_FILE"
    exit 2
fi

if [ -z "${TESLA_AUTH_TOKEN:-}" ]; then
    # The s6 `with-contenv` shebang runs `emptyenv`, which wipes the inherited
    # environment and reloads only /run/s6/container_environment. A token that
    # the caller (auto-apply-telemetry-config.sh) exported at runtime therefore
    # does NOT survive into this child process. Fetch it here instead so this
    # helper is self-sufficient; the OAuth settings it needs were just sourced
    # from /run/tesla_fleet_gateway.env.
    if ! TESLA_AUTH_TOKEN="$(python3 /usr/local/bin/tesla_oauth.py token --quiet)" \
        || [ -z "$TESLA_AUTH_TOKEN" ]; then
        bashio::log.error "TESLA_AUTH_TOKEN is not set and no Tesla OAuth access token could be fetched"
        exit 2
    fi
fi

PROXY_HOST="${TESLA_HTTP_PROXY_HOSTNAME:-${TESLA_ENDPOINT_HOST:-tesla.example.com}}"
PROXY_PORT="${TESLA_HTTP_PROXY_PORT:-4443}"
PROXY_URL="${TESLA_HTTP_PROXY_URL:-https://${PROXY_HOST}:${PROXY_PORT}}"
CA_FILE="${TESLA_HTTP_PROXY_CA_FILE:-/ssl/fullchain.pem}"
RESPONSE_FILE="$(mktemp)"
CURL_RESOLVE_ARGS=()

if [ "${TESLA_HTTP_PROXY_RESOLVE_LOCAL:-true}" = "true" ]; then
    CURL_RESOLVE_ARGS=(--resolve "${PROXY_HOST}:${PROXY_PORT}:127.0.0.1")
fi

warn_next_step() {
    local problem="$1"
    local next_step="$2"
    shift 2
    local details=("$@")
    local index
    local last_index

    bashio::log.warning "⚠️ ACTION REQUIRED"
    bashio::log.warning "⎢ Problem: ${problem}"
    if [ "${#details[@]}" -eq 0 ]; then
        bashio::log.warning "⎣ Next step: ${next_step}"
        return 0
    fi

    bashio::log.warning "⎢ Next step: ${next_step}"
    last_index=$((${#details[@]} - 1))
    for index in "${!details[@]}"; do
        if [ "$index" -eq "$last_index" ]; then
            bashio::log.warning "⎣ ${details[$index]}"
        else
            bashio::log.warning "⎢ ${details[$index]}"
        fi
    done
}

cleanup() {
    rm -f "$RESPONSE_FILE"
}

trap cleanup EXIT

if ! curl --fail --silent --show-error \
    --cacert "$CA_FILE" \
    "${CURL_RESOLVE_ARGS[@]}" \
    --header "Authorization: Bearer ${TESLA_AUTH_TOKEN}" \
    --header "Content-Type: application/json" \
    --data @"$REQUEST_FILE" \
    --output "$RESPONSE_FILE" \
    "${PROXY_URL}/api/1/vehicles/fleet_telemetry_config"; then
    if [ -s "$RESPONSE_FILE" ]; then
        warn_next_step \
            "Tesla Fleet Telemetry config request failed" \
            "Verify the vehicle is paired, the token has telemetry scopes, and Tesla can reach the Tesla endpoint configured in the request JSON" \
            "Check especially: hostname, Tesla endpoint port 443, router forwarding to the gateway listener, TLS certificate chain, and the telemetry path" \
            "Tesla/vehicle-command response follows"
        while IFS= read -r line; do
            bashio::log.warning "$line"
        done < "$RESPONSE_FILE"
    else
        warn_next_step \
            "Tesla Fleet Telemetry config request failed" \
            "Verify the vehicle is paired, the token has telemetry scopes, and Tesla can reach the Tesla endpoint configured in the request JSON" \
            "Check especially: hostname, Tesla endpoint port 443, router forwarding to the gateway listener, TLS certificate chain, and the telemetry path"
    fi
    exit 1
fi

cat "$RESPONSE_FILE"
