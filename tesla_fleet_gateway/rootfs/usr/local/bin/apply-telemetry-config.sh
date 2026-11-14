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
HTTP_CODE_FILE="$(mktemp)"
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
    rm -f "$RESPONSE_FILE" "$HTTP_CODE_FILE"
}

trap cleanup EXIT

# Capture body and HTTP status separately. Do not use --fail: a 4xx body (e.g.
# Unknown field) is the diagnosis, and permanent client errors must not look
# like a transient curl failure to the retry loop.
http_code="000"
curl_ok=true
if ! curl --silent --show-error \
    --cacert "$CA_FILE" \
    "${CURL_RESOLVE_ARGS[@]}" \
    --header "Authorization: Bearer ${TESLA_AUTH_TOKEN}" \
    --header "Content-Type: application/json" \
    --data @"$REQUEST_FILE" \
    --output "$RESPONSE_FILE" \
    --write-out "%{http_code}" \
    "${PROXY_URL}/api/1/vehicles/fleet_telemetry_config" \
    > "$HTTP_CODE_FILE"; then
    curl_ok=false
fi

http_code="$(tr -d '[:space:]' < "$HTTP_CODE_FILE")"
if [ -z "$http_code" ]; then
    http_code="000"
fi

tesla_error=""
if [ -s "$RESPONSE_FILE" ] && jq -e . "$RESPONSE_FILE" >/dev/null 2>&1; then
    tesla_error="$(jq -r '.error // empty' "$RESPONSE_FILE")"
fi

if [ "$curl_ok" = "true" ] && [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    cat "$RESPONSE_FILE"
    exit 0
fi

# HTTP 4xx from Tesla/proxy: permanent for this request body. Exit 3 so the
# auto-apply retry loop does not sleep/retry.
if [ "$http_code" -ge 400 ] && [ "$http_code" -lt 500 ]; then
    if printf '%s' "$tesla_error" | grep -qiE '^Unknown field[[:space:]]'; then
        warn_next_step \
            "Tesla rejected the Fleet Telemetry config: ${tesla_error}" \
            "Confirm every telemetry_fields name exists as a Field enum member in Tesla fleet-telemetry vehicle_data.proto (exact PascalCase)" \
            "One unknown field rejects the entire config; remove or rename it in add-on Telemetry fields, config.yaml schema, and tesla_oauth.py SUPPORTED_TELEMETRY_FIELDS" \
            "Composite values (DoorState, TpmsSoftWarnings, TpmsHardWarnings) use one proto field name — do not invent per-corner field names" \
            "HTTP ${http_code}; Tesla response follows"
    else
        problem="Tesla Fleet Telemetry config request failed (HTTP ${http_code})"
        if [ -n "$tesla_error" ]; then
            problem="${problem}: ${tesla_error}"
        fi
        warn_next_step \
            "$problem" \
            "Verify the vehicle is paired, the token has telemetry scopes, and the request JSON field names / alert_types are valid" \
            "HTTP 4xx is not retried; fix the request and restart the add-on (or force re-apply)" \
            "Tesla/vehicle-command response follows"
    fi
    if [ -s "$RESPONSE_FILE" ]; then
        while IFS= read -r line; do
            bashio::log.warning "$line"
        done < "$RESPONSE_FILE"
    fi
    exit 3
fi

if [ -s "$RESPONSE_FILE" ]; then
    warn_next_step \
        "Tesla Fleet Telemetry config request failed (HTTP ${http_code})" \
        "Verify the vehicle is paired, the token has telemetry scopes, and Tesla can reach the Tesla endpoint configured in the request JSON" \
        "Check especially: hostname, Tesla endpoint port 443, router forwarding to the gateway listener, TLS certificate chain, and the telemetry path" \
        "Tesla/vehicle-command response follows"
    while IFS= read -r line; do
        bashio::log.warning "$line"
    done < "$RESPONSE_FILE"
else
    warn_next_step \
        "Tesla Fleet Telemetry config request failed (HTTP ${http_code})" \
        "Verify the vehicle is paired, the token has telemetry scopes, and Tesla can reach the Tesla endpoint configured in the request JSON" \
        "Check especially: hostname, Tesla endpoint port 443, router forwarding to the gateway listener, TLS certificate chain, and the telemetry path"
fi
exit 1
