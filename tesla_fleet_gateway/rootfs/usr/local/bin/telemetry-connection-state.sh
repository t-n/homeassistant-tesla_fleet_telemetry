#!/usr/bin/with-contenv bashio

# Shared helpers for persisting fleet-telemetry vehicle connection state across
# restarts. Sourced by the watchdog, startup apply logic, and shutdown handler.

set -euo pipefail

source /usr/local/bin/addon-defaults.sh

TELEMETRY_CONNECTION_STATE_FILE="${TELEMETRY_CONNECTION_STATE_FILE:-${ADDON_CONFIG_DIR}/telemetry_connection_state.json}"

telemetry_state_ensure_file() {
    mkdir -p "$(dirname "$TELEMETRY_CONNECTION_STATE_FILE")"
    if [ ! -f "$TELEMETRY_CONNECTION_STATE_FILE" ]; then
        echo '{"vins":{},"gateway_started_at":0}' > "$TELEMETRY_CONNECTION_STATE_FILE"
        chmod 600 "$TELEMETRY_CONNECTION_STATE_FILE"
    fi
}

telemetry_state_now() {
    date +%s
}

telemetry_state_mark_gateway_start() {
    local now

    telemetry_state_ensure_file
    now="$(telemetry_state_now)"
    jq --argjson now "$now" \
        '.gateway_started_at = $now' \
        "$TELEMETRY_CONNECTION_STATE_FILE" > "${TELEMETRY_CONNECTION_STATE_FILE}.tmp"
    mv "${TELEMETRY_CONNECTION_STATE_FILE}.tmp" "$TELEMETRY_CONNECTION_STATE_FILE"
    chmod 600 "$TELEMETRY_CONNECTION_STATE_FILE"
}

telemetry_state_update_vin() {
    local vin="$1"
    local status="$2"
    local reason="${3:-}"
    local error_count="${4:-0}"

    telemetry_state_ensure_file
    jq \
        --arg vin "$vin" \
        --arg status "$status" \
        --arg reason "$reason" \
        --argjson now "$(telemetry_state_now)" \
        --argjson error_count "$error_count" \
        '
        .vins[$vin] = (
            (.vins[$vin] // {})
            | .status = $status
            | .status_changed_at = $now
            | if $reason != "" then .last_disconnect_reason = $reason else . end
            | if $error_count > 0 then .last_error_count = $error_count else . end
            | if $status == "CONNECTED" then
                .recovery_attempts = 0
                | .connected_at = $now
                | del(.last_disconnect_reason)
              else . end
        )
        ' \
        "$TELEMETRY_CONNECTION_STATE_FILE" > "${TELEMETRY_CONNECTION_STATE_FILE}.tmp"
    mv "${TELEMETRY_CONNECTION_STATE_FILE}.tmp" "$TELEMETRY_CONNECTION_STATE_FILE"
    chmod 600 "$TELEMETRY_CONNECTION_STATE_FILE"
}

telemetry_state_mark_shutdown_disconnects() {
    local vin

    telemetry_state_ensure_file
    while IFS= read -r vin; do
        [ -n "$vin" ] || continue
        telemetry_state_update_vin "$vin" "DISCONNECTED" "shutdown" 0
    done < <(jq -r '.vins | to_entries[] | select(.value.status == "CONNECTED") | .key' \
        "$TELEMETRY_CONNECTION_STATE_FILE" 2>/dev/null || true)
}

telemetry_state_should_force_startup_reapply() {
    local vin status reason

    telemetry_state_ensure_file
    while IFS= read -r vin; do
        [ -n "$vin" ] || continue
        status="$(jq -r --arg vin "$vin" '.vins[$vin].status // ""' "$TELEMETRY_CONNECTION_STATE_FILE")"
        reason="$(jq -r --arg vin "$vin" '.vins[$vin].last_disconnect_reason // ""' "$TELEMETRY_CONNECTION_STATE_FILE")"
        if [ "$status" = "DISCONNECTED" ] && { [ "$reason" = "errors" ] || [ "$reason" = "shutdown" ]; }; then
            return 0
        fi
    done < <(jq -r '.vins | keys[]?' "$TELEMETRY_CONNECTION_STATE_FILE" 2>/dev/null || true)

    return 1
}

telemetry_state_record_recovery_attempt() {
    local vin="$1"

    telemetry_state_ensure_file
    jq \
        --arg vin "$vin" \
        --argjson now "$(telemetry_state_now)" \
        '
        .vins[$vin] = (
            (.vins[$vin] // {})
            | .recovery_attempts = ((.recovery_attempts // 0) + 1)
            | .last_recovery_at = $now
        )
        ' \
        "$TELEMETRY_CONNECTION_STATE_FILE" > "${TELEMETRY_CONNECTION_STATE_FILE}.tmp"
    mv "${TELEMETRY_CONNECTION_STATE_FILE}.tmp" "$TELEMETRY_CONNECTION_STATE_FILE"
    chmod 600 "$TELEMETRY_CONNECTION_STATE_FILE"
}

telemetry_state_vin_field() {
    local vin="$1"
    local field="$2"

    telemetry_state_ensure_file
    jq -r --arg vin "$vin" --arg field "$field" '.vins[$vin][$field] // empty' \
        "$TELEMETRY_CONNECTION_STATE_FILE"
}

telemetry_state_clear_disconnect_reasons() {
    telemetry_state_ensure_file
    jq '.vins |= with_entries(.value |= del(.last_disconnect_reason))' \
        "$TELEMETRY_CONNECTION_STATE_FILE" > "${TELEMETRY_CONNECTION_STATE_FILE}.tmp"
    mv "${TELEMETRY_CONNECTION_STATE_FILE}.tmp" "$TELEMETRY_CONNECTION_STATE_FILE"
    chmod 600 "$TELEMETRY_CONNECTION_STATE_FILE"
}
