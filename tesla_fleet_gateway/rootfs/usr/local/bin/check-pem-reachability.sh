#!/usr/bin/with-contenv bashio

set -euo pipefail

source /usr/local/bin/addon-defaults.sh

if [ -f /run/tesla_fleet_gateway.env ]; then
    set -a
    # shellcheck disable=SC1091
    source /run/tesla_fleet_gateway.env
    set +a
fi

EDGE_PEM_ROOT="${EDGE_PEM_ROOT:-$DEFAULT_EDGE_PEM_ROOT}"
EDGE_PEM_PUBLIC_PATH="${EDGE_PEM_PUBLIC_PATH:-$DEFAULT_EDGE_PEM_PUBLIC_PATH}"
EDGE_TLS_CERT="${EDGE_TLS_CERT:-$DEFAULT_EDGE_TLS_CERT}"

WARNINGS=0

warn_next_step() {
    local problem="$1"
    local next_step="$2"
    shift 2
    local details=("$@")
    local index
    local last_index

    WARNINGS=$((WARNINGS + 1))
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

log_success() {
    local title="$1"
    local detail="$2"

    bashio::log.info "✅ ${title}"
    bashio::log.info "⎣ ${detail}"
}

PUBLIC_KEY_PATH="${EDGE_PEM_ROOT}${EDGE_PEM_PUBLIC_PATH}"
DOWNLOAD="$(mktemp)"
GATEWAY_PEM_URL="https://${GATEWAY_HOST}:${GATEWAY_TLS_PORT}${EDGE_PEM_PUBLIC_PATH}"
GATEWAY_RESOLVE_ARGS=(--resolve "${GATEWAY_HOST}:${GATEWAY_TLS_PORT}:127.0.0.1")
TESLA_PEM_URL="https://${TESLA_ENDPOINT_HOST}:${GATEWAY_TLS_PORT}${EDGE_PEM_PUBLIC_PATH}"
TESLA_RESOLVE_ARGS=(--resolve "${TESLA_ENDPOINT_HOST}:${GATEWAY_TLS_PORT}:127.0.0.1")

cleanup() {
    rm -f "$DOWNLOAD"
}

trap cleanup EXIT

fetch_pem() {
    local url="$1"
    shift
    curl --fail --silent --show-error \
        --max-time 10 \
        --cacert "$EDGE_TLS_CERT" \
        "$@" \
        --output "$DOWNLOAD" \
        "$url"
}

if fetch_pem "$GATEWAY_PEM_URL" "${GATEWAY_RESOLVE_ARGS[@]}"; then
    if cmp -s "$DOWNLOAD" "$PUBLIC_KEY_PATH"; then
        log_success "Gateway listener serves the Tesla public key PEM" "Verified ${GATEWAY_PEM_URL}"
    else
        warn_next_step \
            "Gateway listener returned a PEM that does not match the configured public key file" \
            "Confirm edge.pem_root and edge.pem_public_path point at ${PUBLIC_KEY_PATH}"
    fi
else
    warn_next_step \
        "Gateway listener did not return the Tesla public key PEM" \
        "Check nginx startup logs, TLS certificate paths, and that ${PUBLIC_KEY_PATH} exists"
fi

range_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --max-time 10 \
    --cacert "$EDGE_TLS_CERT" \
    "${GATEWAY_RESOLVE_ARGS[@]}" \
    -H "Range: bytes=0-200" \
    "$GATEWAY_PEM_URL" || true)"
if [ "$range_status" = "200" ] || [ "$range_status" = "206" ]; then
    log_success "Gateway listener accepts Tesla Range requests for the PEM" "Verified Range: bytes=0-200 returned HTTP ${range_status}"
else
    warn_next_step \
        "Gateway listener did not accept a Tesla-style Range request for the PEM" \
        "Tesla pairing and validation request the PEM with Range: bytes=0-200; got HTTP ${range_status:-unknown}" \
        "Check nginx PEM location settings on ${GATEWAY_PEM_URL}"
fi

if fetch_pem "$TESLA_PEM_URL" "${TESLA_RESOLVE_ARGS[@]}"; then
    if cmp -s "$DOWNLOAD" "$PUBLIC_KEY_PATH"; then
        if [ "$TESLA_ENDPOINT_HTTPS_PORT" = "$GATEWAY_TLS_PORT" ]; then
            log_success "Tesla endpoint serves the Tesla public key PEM" "Verified ${TESLA_PEM_URL}"
        else
            log_success "Tesla endpoint serves the Tesla public key PEM" "Verified ${TESLA_PEM_URL}; router forwards ${TESLA_ENDPOINT_HOST}:${TESLA_ENDPOINT_HTTPS_PORT} to gateway listener ${GATEWAY_TLS_PORT}"
        fi
    else
        warn_next_step \
            "Tesla endpoint returned a PEM that does not match the configured public key file" \
            "Confirm router or reverse-proxy forwarding to gateway listener ${GATEWAY_HOST}:${GATEWAY_TLS_PORT}"
    fi
else
    warn_next_step \
        "Tesla endpoint did not return the Tesla public key PEM on the gateway listener" \
        "Forward ${TESLA_ENDPOINT_HOST}:${TESLA_ENDPOINT_HTTPS_PORT} to gateway listener ${GATEWAY_HOST}:${GATEWAY_TLS_PORT}" \
        "Tesla registration, pairing, and OAuth require the PEM at https://${TESLA_ENDPOINT_HOST}:${TESLA_ENDPOINT_HTTPS_PORT}${EDGE_PEM_PUBLIC_PATH}"
fi

if [ "${TESLA_TELEMETRY_PASSTHROUGH_HOST:-}" != "${TESLA_ENDPOINT_HOST:-}" ] \
    && [ "${EDGE_TELEMETRY_MTLS_PASSTHROUGH:-false}" != "true" ]; then
    PASSTHROUGH_PEM_URL="https://${TESLA_TELEMETRY_PASSTHROUGH_HOST}:${GATEWAY_TLS_PORT}${EDGE_PEM_PUBLIC_PATH}"
    PASSTHROUGH_RESOLVE_ARGS=(--resolve "${TESLA_TELEMETRY_PASSTHROUGH_HOST}:${GATEWAY_TLS_PORT}:127.0.0.1")
    if fetch_pem "$PASSTHROUGH_PEM_URL" "${PASSTHROUGH_RESOLVE_ARGS[@]}"; then
        if cmp -s "$DOWNLOAD" "$PUBLIC_KEY_PATH"; then
            log_success "Telemetry passthrough hostname serves the Tesla public key PEM" "Verified ${PASSTHROUGH_PEM_URL}"
        else
            warn_next_step \
                "Telemetry passthrough hostname returned a PEM that does not match the configured public key file" \
                "Confirm nginx server_name includes ${TESLA_TELEMETRY_PASSTHROUGH_HOST}"
        fi
    else
        warn_next_step \
            "Telemetry passthrough hostname did not return the Tesla public key PEM" \
            "Register ${TESLA_TELEMETRY_PASSTHROUGH_HOST} in the Tesla developer app after this PEM check passes"
    fi
fi

if [ "$WARNINGS" -gt 0 ]; then
    exit 1
fi
