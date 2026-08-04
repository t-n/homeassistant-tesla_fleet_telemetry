#!/usr/bin/with-contenv bashio

set -euo pipefail

if [ -f /run/tesla_fleet_gateway.env ]; then
    set -a
    # shellcheck source=/run/tesla_fleet_gateway.env
    source /run/tesla_fleet_gateway.env
    set +a
fi

source /usr/local/bin/addon-defaults.sh
source /usr/local/bin/telemetry-connection-state.sh

RECOVERY_ENABLED="${TELEMETRY_RECOVERY_ENABLED:-$DEFAULT_TELEMETRY_RECOVERY_ENABLED}"
RECOVERY_DISCONNECT_SECONDS="${TELEMETRY_RECOVERY_DISCONNECT_SECONDS:-$DEFAULT_TELEMETRY_RECOVERY_DISCONNECT_SECONDS}"
RECOVERY_WAKE_VEHICLE="${TELEMETRY_RECOVERY_WAKE_VEHICLE:-$DEFAULT_TELEMETRY_RECOVERY_WAKE_VEHICLE}"
RECOVERY_CHECK_INTERVAL="${TELEMETRY_RECOVERY_CHECK_INTERVAL:-$DEFAULT_TELEMETRY_RECOVERY_CHECK_INTERVAL}"
RECOVERY_MAX_ATTEMPTS="${TELEMETRY_RECOVERY_MAX_ATTEMPTS:-$DEFAULT_TELEMETRY_RECOVERY_MAX_ATTEMPTS}"

LAST_ERROR_VIN=""
LAST_ERROR_COUNT=0

parse_fleet_telemetry_line() {
    local line="$1"
    local context status vin txtype error_count

    if ! echo "$line" | jq -e 'type == "object"' >/dev/null 2>&1; then
        return 0
    fi

    context="$(echo "$line" | jq -r '.context // empty')"
    if [ "$context" != "fleet-telemetry" ]; then
        return 0
    fi

    txtype="$(echo "$line" | jq -r '.txtype // empty')"
    if [ "$txtype" = "errors" ]; then
        vin="$(echo "$line" | jq -r '.Vin // .vin // empty')"
        error_count="$(echo "$line" | jq -r '.errors // .data.errors // 0')"
        if [ -n "$vin" ]; then
            LAST_ERROR_VIN="$vin"
            LAST_ERROR_COUNT="$error_count"
        fi
        return 0
    fi

    status="$(echo "$line" | jq -r '.Status // empty')"
    vin="$(echo "$line" | jq -r '.Vin // .vin // empty')"
    if [ -z "$status" ] || [ -z "$vin" ]; then
        if echo "$line" | jq -e '.msg == "socket_disconnected"' >/dev/null 2>&1; then
            vin="$(echo "$line" | jq -r '.Vin // .vin // empty')"
            error_count="$(echo "$line" | jq -r '.errors // 0')"
            if [ -n "$vin" ]; then
                if [ "${error_count:-0}" -gt 0 ] 2>/dev/null; then
                    telemetry_state_update_vin "$vin" "DISCONNECTED" "errors" "$error_count"
                elif [ -n "$LAST_ERROR_VIN" ] && [ "$LAST_ERROR_VIN" = "$vin" ]; then
                    telemetry_state_update_vin "$vin" "DISCONNECTED" "errors" "$LAST_ERROR_COUNT"
                else
                    telemetry_state_update_vin "$vin" "DISCONNECTED" "unknown" 0
                fi
                bashio::log.warning "Vehicle ${vin} disconnected from fleet-telemetry"
                LAST_ERROR_VIN=""
                LAST_ERROR_COUNT=0
            fi
        fi
        return 0
    fi

    case "$status" in
        CONNECTED)
            telemetry_state_update_vin "$vin" "CONNECTED" "" 0
            bashio::log.info "Vehicle ${vin} connected to fleet-telemetry"
            LAST_ERROR_VIN=""
            LAST_ERROR_COUNT=0
            ;;
        DISCONNECTED)
            if [ -n "$LAST_ERROR_VIN" ] && [ "$LAST_ERROR_VIN" = "$vin" ]; then
                telemetry_state_update_vin "$vin" "DISCONNECTED" "errors" "$LAST_ERROR_COUNT"
            else
                telemetry_state_update_vin "$vin" "DISCONNECTED" "unknown" 0
            fi
            bashio::log.warning "Vehicle ${vin} disconnected from fleet-telemetry"
            LAST_ERROR_VIN=""
            LAST_ERROR_COUNT=0
            ;;
    esac
}

attempt_recovery_for_vin() {
    local vin="$1"
    local reason attempts

    reason="$(telemetry_state_vin_field "$vin" "last_disconnect_reason")"
    attempts="$(telemetry_state_vin_field "$vin" "recovery_attempts")"
    attempts="${attempts:-0}"

    if [ "$attempts" -ge "$RECOVERY_MAX_ATTEMPTS" ]; then
        return 0
    fi

    bashio::log.info "Starting telemetry recovery for ${vin} (reason: ${reason:-unknown}, attempt $((attempts + 1))/${RECOVERY_MAX_ATTEMPTS})"
    telemetry_state_record_recovery_attempt "$vin"

    if [ "$RECOVERY_WAKE_VEHICLE" = "true" ]; then
        /usr/local/bin/wake-vehicles.sh || true
        sleep 5
    fi

    if FLEET_TELEMETRY_FORCE_REAPPLY=true /usr/local/bin/auto-apply-telemetry-config.sh; then
        bashio::log.info "Telemetry recovery re-apply completed for ${vin}"
    else
        bashio::log.warning "Telemetry recovery re-apply failed for ${vin}"
    fi
}

check_recovery_targets() {
    local vin status changed_at now elapsed reason attempts

    if [ "$RECOVERY_ENABLED" != "true" ]; then
        return 0
    fi

    if [ "${VEHICLE_COMMAND_ENABLED:-false}" != "true" ]; then
        return 0
    fi

    if [ "${TESLA_OAUTH_TOKENS_VERIFIED:-false}" != "true" ]; then
        return 0
    fi

    now="$(telemetry_state_now)"
    while IFS= read -r vin; do
        [ -n "$vin" ] || continue
        status="$(telemetry_state_vin_field "$vin" "status")"
        [ "$status" = "DISCONNECTED" ] || continue

        changed_at="$(telemetry_state_vin_field "$vin" "status_changed_at")"
        reason="$(telemetry_state_vin_field "$vin" "last_disconnect_reason")"
        attempts="$(telemetry_state_vin_field "$vin" "recovery_attempts")"
        attempts="${attempts:-0}"

        if [ "$attempts" -ge "$RECOVERY_MAX_ATTEMPTS" ]; then
            continue
        fi

        changed_at="${changed_at:-0}"
        elapsed=$((now - changed_at))

        if [ "$reason" = "errors" ] && [ "$elapsed" -ge 30 ]; then
            attempt_recovery_for_vin "$vin"
            continue
        fi

        if [ "$elapsed" -ge "$RECOVERY_DISCONNECT_SECONDS" ]; then
            attempt_recovery_for_vin "$vin"
        fi
    done < <(jq -r '.vins | keys[]?' "$TELEMETRY_CONNECTION_STATE_FILE" 2>/dev/null || true)
}

recovery_loop() {
    while true; do
        sleep "$RECOVERY_CHECK_INTERVAL"
        check_recovery_targets || true
    done
}

main() {
    telemetry_state_mark_gateway_start

    if [ "$RECOVERY_ENABLED" = "true" ] && [ "${VEHICLE_COMMAND_ENABLED:-false}" = "true" ]; then
        bashio::log.info "Telemetry connection watchdog enabled (disconnect threshold: ${RECOVERY_DISCONNECT_SECONDS}s)"
        recovery_loop &
        RECOVERY_LOOP_PID=$!
    else
        bashio::log.info "Telemetry connection watchdog log parser only (recovery disabled)"
        RECOVERY_LOOP_PID=""
    fi

    while IFS= read -r line; do
        parse_fleet_telemetry_line "$line" || true
    done

    if [ -n "${RECOVERY_LOOP_PID:-}" ] && kill -0 "$RECOVERY_LOOP_PID" 2>/dev/null; then
        kill "$RECOVERY_LOOP_PID" 2>/dev/null || true
        wait "$RECOVERY_LOOP_PID" 2>/dev/null || true
    fi
}

main
