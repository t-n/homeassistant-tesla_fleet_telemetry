#!/usr/bin/with-contenv bashio

set -euo pipefail

if [ -f /run/tesla_fleet_gateway.env ]; then
    set -a
    # shellcheck source=/run/tesla_fleet_gateway.env
    source /run/tesla_fleet_gateway.env
    set +a
fi

REQUEST_FILE="${FLEET_TELEMETRY_REQUEST_FILE:-/addon_config/fleet_telemetry_config.json}"
BASE="${TESLA_OAUTH_AUDIENCE:-}"

if [ -z "$BASE" ]; then
    bashio::log.warning "Skipping vehicle wake because Fleet API audience is not configured"
    exit 1
fi

if [ ! -f "$REQUEST_FILE" ]; then
    bashio::log.warning "Skipping vehicle wake because request file is missing: ${REQUEST_FILE}"
    exit 1
fi

if ! TESLA_AUTH_TOKEN="$(python3 /usr/local/bin/tesla_oauth.py token --quiet)"; then
    bashio::log.warning "Skipping vehicle wake because no Tesla OAuth access token is available"
    exit 1
fi

BASE="${BASE%/}"
wake_ok=0
wake_failed=0

while IFS= read -r vin; do
    [ -n "$vin" ] || continue
    response="$(curl -sS --max-time 20 \
        -X POST \
        --header "Authorization: Bearer ${TESLA_AUTH_TOKEN}" \
        --header "Content-Type: application/json" \
        "${BASE}/api/1/vehicles/${vin}/wake_up" || true)"
    if echo "$response" | jq -e '.response.state? // .response // empty' >/dev/null 2>&1; then
        wake_ok=$((wake_ok + 1))
        bashio::log.info "Requested wake for vehicle ${vin}"
    else
        wake_failed=$((wake_failed + 1))
        bashio::log.warning "Vehicle wake request failed for ${vin}: $(echo "$response" | tr -d '\n' | head -c 300)"
    fi
done < <(jq -r '.vins[]?' "$REQUEST_FILE")

if [ "$wake_ok" -gt 0 ]; then
    bashio::log.info "Vehicle wake requests sent for ${wake_ok} VIN(s)"
fi

if [ "$wake_failed" -gt 0 ]; then
    exit 1
fi
