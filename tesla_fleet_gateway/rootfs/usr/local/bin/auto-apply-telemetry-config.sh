#!/usr/bin/with-contenv bashio

set -euo pipefail

source /usr/local/bin/telemetry-connection-state.sh

if [ -f /run/tesla_fleet_gateway.env ]; then
    set -a
    # shellcheck source=/run/tesla_fleet_gateway.env
    source /run/tesla_fleet_gateway.env
    set +a
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

log_success() {
    local title="$1"
    local detail="$2"

    bashio::log.info "✅ ${title}"
    bashio::log.info "⎣ ${detail}"
}

validate_request_json() {
    local request_file="$1"
    local endpoint_host="$2"
    local endpoint_port="$3"
    local request_host
    local request_port

    if ! jq -e 'type == "object"' "$request_file" >/dev/null; then
        warn_next_step \
            "Fleet Telemetry request is not a JSON object: ${request_file}" \
            "Replace it with a valid fleet_telemetry_config request JSON file"
        return 1
    fi

    if ! jq -e '.vins | type == "array" and length > 0 and all(.[]; type == "string" and length > 0)' "$request_file" >/dev/null; then
        warn_next_step \
            "Fleet Telemetry request has no VINs" \
            "Add at least one VIN to the top-level vins array"
        return 1
    fi

    if ! jq -e '.config.fields | type == "object" and length > 0' "$request_file" >/dev/null; then
        warn_next_step \
            "Fleet Telemetry request has no fields" \
            "Add at least one telemetry field under config.fields"
        return 1
    fi

    request_host="$(jq -er '.config.hostname' "$request_file" 2>/dev/null || true)"
    if [ "$request_host" != "$endpoint_host" ]; then
        warn_next_step \
            "Fleet Telemetry request hostname is ${request_host:-missing}, expected ${endpoint_host}" \
            "Set config.hostname in ${request_file} to ${endpoint_host}"
        return 1
    fi

    request_port="$(jq -er '.config.port | tostring' "$request_file" 2>/dev/null || true)"
    if [ "$request_port" != "$endpoint_port" ]; then
        warn_next_step \
            "Fleet Telemetry request port is ${request_port:-missing}, expected ${endpoint_port}" \
            "Set config.port in ${request_file} to ${endpoint_port}"
        return 1
    fi

    return 0
}

wait_for_proxy() {
    local proxy_port="$1"
    local bind_host="$2"
    local retry_seconds="$3"
    local deadline

    deadline=$((SECONDS + retry_seconds))
    while [ "$SECONDS" -le "$deadline" ]; do
        if busybox nc -z "$bind_host" "$proxy_port" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done

    return 1
}

telemetry_field_apply_signature() {
    # Compare field names and resend intervals. interval_seconds is not compared
    # against Tesla's GET response because Tesla may normalize or omit it.
    jq -r '(.config.fields // {}) | to_entries | sort_by(.key) | map(.key + ":" + ((.value.resend_interval_seconds // 0) | tostring)) | join(",")' "$1"
}

telemetry_response_apply_signature() {
    jq -r '(.response.config.fields // {}) | to_entries | sort_by(.key) | map(.key + ":" + ((.value.resend_interval_seconds // 0) | tostring)) | join(",")'
}

request_file_digest() {
    local request_file="$1"

    if [ ! -f "$request_file" ]; then
        echo ""
        return 0
    fi

    md5sum "$request_file" | awk '{print $1}'
}

telemetry_already_synced() {
    # Returns 0 when Tesla already reports the telemetry config synced for every
    # VIN with a matching hostname/port/field timing. This is a plain Fleet API
    # GET and does not need the Vehicle Command Proxy, so it lets us skip the
    # signed re-apply in the steady state. Requires TESLA_AUTH_TOKEN to be set.
    local request_file="$1"
    local base="${TESLA_OAUTH_AUDIENCE:-}"
    local req_host req_port req_apply vin cfg synced chost cport capply

    [ -n "$base" ] || return 1
    base="${base%/}"
    req_host="$(jq -r '.config.hostname' "$request_file")"
    req_port="$(jq -r '.config.port | tostring' "$request_file")"
    req_apply="$(telemetry_field_apply_signature "$request_file")"

    while IFS= read -r vin; do
        [ -n "$vin" ] || continue
        cfg="$(curl -s --max-time 15 \
            --header "Authorization: Bearer ${TESLA_AUTH_TOKEN}" \
            "${base}/api/1/vehicles/${vin}/fleet_telemetry_config")" || return 1
        synced="$(echo "$cfg" | jq -r '.response.synced // false')"
        chost="$(echo "$cfg" | jq -r '.response.config.hostname // ""')"
        cport="$(echo "$cfg" | jq -r '.response.config.port // "" | tostring')"
        capply="$(echo "$cfg" | telemetry_response_apply_signature)"
        if [ "$synced" != "true" ] || [ "$chost" != "$req_host" ] \
            || [ "$cport" != "$req_port" ] || [ "$capply" != "$req_apply" ]; then
            return 1
        fi
    done < <(jq -r '.vins[]' "$request_file")

    return 0
}

if [ "${TESLA_OAUTH_TOKENS_VERIFIED:-false}" != "true" ]; then
    bashio::log.warning "Skipping Fleet Telemetry auto-apply because OAuth tokens could not be verified"
    exit 0
fi

if [ "${VEHICLE_COMMAND_ENABLED:-false}" != "true" ]; then
    exit 0
fi

REQUEST_FILE="${FLEET_TELEMETRY_REQUEST_FILE:-/addon_config/fleet_telemetry_config.json}"
PROXY_PORT="${VEHICLE_COMMAND_BIND_PORT:-4443}"
CA_FILE="${EDGE_TLS_CERT:-/ssl/fullchain.pem}"
PROXY_URL="https://${TESLA_ENDPOINT_HOST}:${PROXY_PORT}"
APPLY_RESPONSE_FILE="/tmp/fleet_telemetry_config_apply_response.json"

# Always reconcile the request file from add-on options, then push to Tesla when
# the reconciled file differs from Tesla's synced config.
REQUEST_DIGEST_BEFORE="$(request_file_digest "$REQUEST_FILE")"
if [ ! -f "$REQUEST_FILE" ]; then
    bashio::log.info "Generating Fleet Telemetry request file"
else
    bashio::log.info "Reconciling Fleet Telemetry request file with add-on options"
fi
if ! /usr/local/bin/tesla_oauth.py prepare-telemetry-config; then
    exit 1
fi
REQUEST_DIGEST_AFTER="$(request_file_digest "$REQUEST_FILE")"
REQUEST_FILE_CHANGED=false
if [ "$REQUEST_DIGEST_BEFORE" != "$REQUEST_DIGEST_AFTER" ]; then
    REQUEST_FILE_CHANGED=true
    bashio::log.info "Fleet Telemetry request file changed during startup reconciliation"
fi

if [ ! -f "$REQUEST_FILE" ]; then
    warn_next_step \
        "Fleet Telemetry request file was not found: ${REQUEST_FILE}" \
        "Create the request JSON file or change fleet_telemetry_config.request_file"
    exit 1
fi

if ! validate_request_json "$REQUEST_FILE" "$TESLA_TELEMETRY_HOST" "$TESLA_ENDPOINT_HTTPS_PORT"; then
    exit 1
fi

log_success "Fleet Telemetry config preconditions passed" "Request ${REQUEST_FILE} targets ${TESLA_TELEMETRY_HOST}:${TESLA_ENDPOINT_HTTPS_PORT}"

if ! TESLA_AUTH_TOKEN="$(python3 /usr/local/bin/tesla_oauth.py token --quiet)"; then
    warn_next_step \
        "Fleet Telemetry config was validated but no Tesla OAuth access token could be fetched" \
        "Complete the OAuth refresh-token setup shown above, then restart the add-on"
    exit 1
fi
export TESLA_AUTH_TOKEN

FORCE_REAPPLY=false
if [ "${FLEET_TELEMETRY_FORCE_REAPPLY:-false}" = "true" ]; then
    FORCE_REAPPLY=true
    bashio::log.info "Forcing Fleet Telemetry signed re-apply"
elif telemetry_state_should_force_startup_reapply; then
    FORCE_REAPPLY=true
    bashio::log.info "Previous gateway run dropped active vehicle stream(s); forcing telemetry re-apply on startup"
elif [ "$REQUEST_FILE_CHANGED" = "true" ]; then
    FORCE_REAPPLY=true
    bashio::log.info "Fleet Telemetry request file changed; forcing signed re-apply on startup"
fi

# Skip the signed re-apply when Tesla already has the matching config synced.
# Setting fleet_telemetry_config requires a vehicle-command-signed request via
# the proxy, but checking the current state is a plain GET. Re-pushing an
# already-synced config on every restart is redundant and would surface a
# spurious error if the proxy path hiccups. Recovery paths set FORCE_REAPPLY.
if [ "$FORCE_REAPPLY" != "true" ] && telemetry_already_synced "$REQUEST_FILE"; then
    log_success \
        "Fleet Telemetry config already synced at Tesla" \
        "All VINs report synced=true for ${TESLA_TELEMETRY_HOST}:${TESLA_ENDPOINT_HTTPS_PORT}; skipping signed re-apply"
    exit 0
fi

if ! wait_for_proxy "$PROXY_PORT" "${VEHICLE_COMMAND_BIND_HOST:-127.0.0.1}" "30"; then
    warn_next_step \
        "Vehicle Command Proxy did not become reachable on ${VEHICLE_COMMAND_BIND_HOST:-127.0.0.1}:${PROXY_PORT}" \
        "Check hosts.telemetry_enabled, tesla-http-proxy lines in the add-on log, and TESLA_KEY_FILE"
    exit 1
fi

export TESLA_HTTP_PROXY_HOSTNAME="$TESLA_ENDPOINT_HOST"
export TESLA_HTTP_PROXY_PORT="$PROXY_PORT"
export TESLA_HTTP_PROXY_CA_FILE="$CA_FILE"
export TESLA_HTTP_PROXY_RESOLVE_LOCAL="true"

# Retry the signed apply a few times to absorb a brief proxy-startup window.
# Capture stdout+stderr together so the real curl/Tesla error is preserved (the
# apply helper writes its diagnostics to both streams).
APPLY_MAX_ATTEMPTS="${FLEET_TELEMETRY_APPLY_MAX_ATTEMPTS:-5}"
APPLY_RETRY_DELAY="${FLEET_TELEMETRY_APPLY_RETRY_DELAY:-3}"
APPLY_OUTPUT_FILE="$(mktemp)"
apply_attempt=1
apply_ok=false

while [ "$apply_attempt" -le "$APPLY_MAX_ATTEMPTS" ]; do
    if /usr/local/bin/apply-telemetry-config.sh "$REQUEST_FILE" > "$APPLY_OUTPUT_FILE" 2>&1; then
        apply_ok=true
        break
    fi

    if [ "$apply_attempt" -lt "$APPLY_MAX_ATTEMPTS" ]; then
        bashio::log.info "Fleet Telemetry config apply attempt ${apply_attempt}/${APPLY_MAX_ATTEMPTS} failed; retrying in ${APPLY_RETRY_DELAY}s"
        sleep "$APPLY_RETRY_DELAY"
    fi
    apply_attempt=$((apply_attempt + 1))
done

if [ "$apply_ok" = "true" ]; then
    if jq -e . "$APPLY_OUTPUT_FILE" >/dev/null 2>&1; then
        bashio::log.info "Fleet Telemetry apply response: $(jq -c . "$APPLY_OUTPUT_FILE")"
    else
        bashio::log.info "Fleet Telemetry apply response: $(tr -d '\n' < "$APPLY_OUTPUT_FILE" | head -c 500)"
    fi
    log_success "Fleet Telemetry config applied" "Tesla accepted the request after ${apply_attempt} attempt(s)"
    telemetry_state_clear_disconnect_reasons
    rm -f "$APPLY_OUTPUT_FILE"
else
    bashio::log.warning "Fleet Telemetry apply output (final attempt):"
    while IFS= read -r line; do
        [ -n "$line" ] && bashio::log.warning "⎢ ${line}"
    done < "$APPLY_OUTPUT_FILE"
    rm -f "$APPLY_OUTPUT_FILE"

    # Probe the proxy's TLS directly so cert/handshake problems are visible.
    bashio::log.warning "Vehicle Command Proxy TLS probe (https://${TESLA_ENDPOINT_HOST}:${PROXY_PORT}/):"
    curl -sS -v -o /dev/null --max-time 10 \
        --cacert "$CA_FILE" \
        --resolve "${TESLA_ENDPOINT_HOST}:${PROXY_PORT}:127.0.0.1" \
        "https://${TESLA_ENDPOINT_HOST}:${PROXY_PORT}/" 2>&1 \
        | grep -iE "connected|connect to|SSL|TLS|certificate|subject:|issuer:|alert|verif|refused|handshake|HTTP/|unable" \
        | while IFS= read -r line; do
            bashio::log.warning "⎢ ${line}"
        done

    warn_next_step \
        "Fleet Telemetry config apply failed after ${APPLY_MAX_ATTEMPTS} attempts" \
        "If GET /api/1/vehicles/<vin>/fleet_telemetry_config shows synced=true, the active config is already in place; otherwise review the apply output and TLS probe above"
    exit 1
fi
