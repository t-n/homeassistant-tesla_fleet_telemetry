#!/usr/bin/with-contenv bashio

set -euo pipefail

source /usr/local/bin/addon-defaults.sh

export GATEWAY_HOST GATEWAY_TLS_PORT TESLA_ENDPOINT_HOST TESLA_ENDPOINT_HTTPS_PORT EDGE_PEM_ROOT EDGE_PEM_PUBLIC_PATH EDGE_TLS_CERT EDGE_TLS_KEY
export TELEMETRY_BIND_HOST TELEMETRY_BIND_PORT TELEMETRY_LOG_LEVEL
export TELEMETRY_RELIABLE_ACK TELEMETRY_TRANSMIT_DECODED_RECORDS TELEMETRY_DELIVERY_POLICY
export MQTT_BROKER MQTT_PORT MQTT_USERNAME MQTT_PASSWORD MQTT_CLIENT_ID MQTT_TOPIC_BASE
export MQTT_QOS MQTT_RETAINED MQTT_CONNECT_TIMEOUT_MS MQTT_PUBLISH_TIMEOUT_MS MQTT_KEEP_ALIVE_SECONDS
export TELEMETRY_ACCESS_LOG GATEWAY_ACCESS_LOG
export TESLA_TELEMETRY_HOST TESLA_TELEMETRY_PASSTHROUGH_HOST EDGE_TELEMETRY_MTLS_PASSTHROUGH
export GATEWAY_HTTP_BIND_HOST GATEWAY_HTTP_BIND_PORT NGINX_PEM_SERVER_NAMES
export VEHICLE_COMMAND_ENABLED VEHICLE_COMMAND_PRIVATE_KEY_PATH
export VEHICLE_COMMAND_BIND_HOST VEHICLE_COMMAND_BIND_PORT VEHICLE_COMMAND_TIMEOUT_SECONDS
export FLEET_TELEMETRY_AUTO_APPLY
export TESLA_OAUTH_CLIENT_ID TESLA_OAUTH_CLIENT_SECRET TESLA_OAUTH_AUTHORIZE_URL TESLA_OAUTH_TOKEN_URL
export TESLA_OAUTH_TOKEN_CACHE_FILE TESLA_OAUTH_STATE_FILE TESLA_OAUTH_REDIRECT_URI TESLA_OAUTH_CALLBACK_PATH
export TESLA_OAUTH_CALLBACK_BIND_HOST TESLA_OAUTH_CALLBACK_BIND_PORT TESLA_OAUTH_AUDIENCE TESLA_OAUTH_SCOPE
export TESLA_OAUTH_HANDOFF_FILE TESLA_OAUTH_USE_INTEGRATION_HANDOFF
export TESLA_OAUTH_USE_INTEGRATION_TOKEN TESLA_OAUTH_TOKENS_VERIFIED
export FLEET_TELEMETRY_REQUEST_FILE

config_bool_default() {
    local primary="$1"
    local legacy="$2"
    local default_value="$3"

    if bashio::config.exists "$primary"; then
        if bashio::config.true "$primary"; then
            echo "true"
        else
            echo "false"
        fi
        return
    fi

    if [ -n "$legacy" ] && bashio::config.exists "$legacy"; then
        if bashio::config.true "$legacy"; then
            echo "true"
        else
            echo "false"
        fi
        return
    fi

    echo "$default_value"
}

unique_hostnames() {
    local seen=""
    local host
    local result=""

    for host in "$@"; do
        [ -n "$host" ] || continue
        case " ${seen} " in
            *" ${host} "*) ;;
            *)
                seen="${seen} ${host}"
                result="${result} ${host}"
                ;;
        esac
    done

    echo "${result# }"
}

append_stream_map_entry() {
    local host="$1"
    local upstream="$2"

    [ -n "$host" ] || return 0
    case " ${STREAM_MAP_HOSTS_SEEN} " in
        *" ${host} "*) return 0 ;;
    esac

    STREAM_MAP_HOSTS_SEEN="${STREAM_MAP_HOSTS_SEEN} ${host}"
    STREAM_MAP_ENTRIES="${STREAM_MAP_ENTRIES}
        ${host} ${upstream};"
}

config_or_legacy() {
    local primary="$1"
    local legacy="$2"

    if bashio::config.exists "$primary"; then
        bashio::config "$primary"
    else
        bashio::config "$legacy"
    fi
}

config_default() {
    local key="$1"
    local default_value="$2"
    local value

    if ! bashio::config.exists "$key"; then
        echo "$default_value"
        return
    fi

    value="$(bashio::config "$key")"
    if [ -z "$value" ] || [ "$value" = "null" ]; then
        echo "$default_value"
    else
        echo "$value"
    fi
}

config_or_legacy_default() {
    local primary="$1"
    local legacy="$2"
    local default_value="$3"
    local primary_value

    if ! bashio::config.exists "$primary"; then
        bashio::config "$legacy"
        return
    fi

    primary_value="$(bashio::config "$primary")"
    if [ "$primary_value" = "$default_value" ] && bashio::config.exists "$legacy"; then
        bashio::config "$legacy"
    else
        echo "$primary_value"
    fi
}

config_with_renamed_fallbacks() {
    local primary="$1"
    local renamed="$2"
    local legacy="$3"
    local default_value="$4"
    local primary_value
    local renamed_value

    if bashio::config.exists "$primary"; then
        primary_value="$(bashio::config "$primary")"
        if [ "$primary_value" != "$default_value" ]; then
            echo "$primary_value"
            return
        fi
    fi

    if bashio::config.exists "$renamed"; then
        renamed_value="$(bashio::config "$renamed")"
        if [ "$renamed_value" != "$default_value" ]; then
            echo "$renamed_value"
            return
        fi
    fi

    if bashio::config.exists "$legacy"; then
        bashio::config "$legacy"
    elif bashio::config.exists "$primary"; then
        echo "$primary_value"
    elif bashio::config.exists "$renamed"; then
        echo "$renamed_value"
    else
        echo "$default_value"
    fi
}

legacy_options_json_path() {
    local key="$1"
    echo ".${key}"
}

legacy_config_exists() {
    local key="$1"
    local path value

    [ -f /data/options.json ] || return 1

    path="$(legacy_options_json_path "$key")"
    value="$(jq -r "${path} // empty" /data/options.json 2>/dev/null || true)"
    [ -n "$value" ] && [ "$value" != "null" ]
}

legacy_config() {
    local key="$1"
    local path

    path="$(legacy_options_json_path "$key")"
    jq -r "${path}" /data/options.json
}

legacy_config_true() {
    local key="$1"
    local value

    if ! legacy_config_exists "$key"; then
        return 1
    fi

    value="$(legacy_config "$key")"
    case "${value,,}" in
        true|1|yes|on)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

config_exists_any() {
    local key="$1"

    if bashio::config.exists "$key"; then
        return 0
    fi

    legacy_config_exists "$key"
}

config_value_any() {
    local key="$1"

    if bashio::config.exists "$key"; then
        bashio::config "$key"
        return
    fi

    if legacy_config_exists "$key"; then
        legacy_config "$key"
    fi
}

config_true_any() {
    local key="$1"

    if bashio::config.exists "$key"; then
        bashio::config.true "$key"
        return
    fi

    legacy_config_true "$key"
}

config_first_nonempty() {
    local key value

    for key in "$@"; do
        if config_exists_any "$key"; then
            value="$(config_value_any "$key")"
            if [ -n "$value" ] && [ "$value" != "null" ]; then
                echo "$value"
                return
            fi
        fi
    done

    echo ""
}

config_bool_with_legacy_chain() {
    local default_value="$1"
    shift
    local key

    for key in "$@"; do
        if config_exists_any "$key"; then
            if config_true_any "$key"; then
                echo "true"
            else
                echo "false"
            fi
            return
        fi
    done

    echo "$default_value"
}

config_bool_legacy_first() {
    local default_value="$1"
    shift
    local key

    for key in "$@"; do
        if config_exists_any "$key"; then
            if config_true_any "$key"; then
                echo "true"
            else
                echo "false"
            fi
            return
        fi
    done

    echo "$default_value"
}

resolve_public_domain() {
    local domain_value=""
    local legacy_host=""

    if bashio::config.exists "domain"; then
        domain_value="$(bashio::config "domain")"
        if [ "$domain_value" = "null" ]; then
            domain_value=""
        fi
    fi

    if [ -n "$domain_value" ] && [ "$domain_value" != "tesla.example.com" ]; then
        echo "$domain_value"
        return
    fi

    legacy_host="$(config_first_nonempty "$@")"
    if [ -n "$legacy_host" ]; then
        echo "$legacy_host"
        return
    fi

    if [ -n "$domain_value" ]; then
        echo "$domain_value"
        return
    fi

    echo "tesla.example.com"
}

resolve_fleet_api_audience() {
    local legacy_audience region

    legacy_audience="$(config_default 'tesla_oauth.audience' '')"
    if [ -n "$legacy_audience" ] && [ "$legacy_audience" != "null" ]; then
        echo "$legacy_audience"
        return
    fi

    if bashio::config.exists 'region'; then
        region="$(bashio::config 'region')"
    else
        echo "$DEFAULT_TESLA_FLEET_API_AUDIENCE_NA"
        return
    fi

    case "$region" in
        eu)
            echo "$DEFAULT_TESLA_FLEET_API_AUDIENCE_EU"
            ;;
        na)
            echo "$DEFAULT_TESLA_FLEET_API_AUDIENCE_NA"
            ;;
        cn)
            echo "$DEFAULT_TESLA_FLEET_API_AUDIENCE_CN"
            ;;
        *)
            echo "$DEFAULT_TESLA_FLEET_API_AUDIENCE_NA"
            ;;
    esac
}

https_listener_url() {
    local host="$1"
    local port="$2"
    local path="$3"

    if [ "$port" = "443" ]; then
        printf 'https://%s%s' "$host" "$path"
    else
        printf 'https://%s:%s%s' "$host" "$port" "$path"
    fi
}

GATEWAY_HOST="$(resolve_public_domain gateway_listener.host addon_lan.host common.public_host)"
GATEWAY_TLS_PORT="$(config_with_renamed_fallbacks 'advanced.tls_port' 'gateway_listener.tls_port' 'addon_lan.tls_port' '1443')"
if [ "$GATEWAY_TLS_PORT" = "1443" ] && bashio::config.exists 'common.public_tls_port'; then
    common_tls_port="$(bashio::config 'common.public_tls_port')"
    if [ -n "$common_tls_port" ] && [ "$common_tls_port" != "null" ] && [ "$common_tls_port" != "1443" ]; then
        GATEWAY_TLS_PORT="$common_tls_port"
    fi
fi
TESLA_ENDPOINT_HOST="$(resolve_public_domain tesla_endpoint.host tesla_internet.host activation.external_host)"
if [ "$TESLA_ENDPOINT_HOST" = "tesla.example.com" ] && [ "$GATEWAY_HOST" != "tesla.example.com" ]; then
    TESLA_ENDPOINT_HOST="$GATEWAY_HOST"
fi
TESLA_ENDPOINT_HTTPS_PORT="$DEFAULT_TESLA_ENDPOINT_HTTPS_PORT"
EDGE_PEM_ROOT="$(config_default 'edge.pem_root' "$DEFAULT_EDGE_PEM_ROOT")"
EDGE_PEM_PUBLIC_PATH="$(config_default 'edge.pem_public_path' "$DEFAULT_EDGE_PEM_PUBLIC_PATH")"
EDGE_TLS_CERT="$(config_default 'advanced.certfile' "$(config_default 'edge.tls_cert' "$DEFAULT_EDGE_TLS_CERT")")"
EDGE_TLS_KEY="$(config_default 'advanced.keyfile' "$(config_default 'edge.tls_key' "$DEFAULT_EDGE_TLS_KEY")")"
TESLA_TELEMETRY_PASSTHROUGH_HOST="$(config_first_nonempty advanced.telemetry_host tesla_endpoint.telemetry_host)"
if [ -z "$TESLA_TELEMETRY_PASSTHROUGH_HOST" ] || [ "$TESLA_TELEMETRY_PASSTHROUGH_HOST" = "null" ]; then
    TESLA_TELEMETRY_PASSTHROUGH_HOST="${DEFAULT_TESLA_TELEMETRY_PASSTHROUGH_PREFIX}.${TESLA_ENDPOINT_HOST}"
fi
HOSTS_PEM_ENABLED="$(config_bool_legacy_first "true" hosts.pem_enabled)"
HOSTS_TELEMETRY_ENABLED="$(config_bool_legacy_first "false" edge.telemetry_mtls_passthrough telemetry.mtls_passthrough hosts.telemetry_enabled)"
if [ "$HOSTS_TELEMETRY_ENABLED" = "true" ]; then
    EDGE_TELEMETRY_MTLS_PASSTHROUGH="true"
    VEHICLE_COMMAND_ENABLED="true"
    FLEET_TELEMETRY_AUTO_APPLY="true"
else
    EDGE_TELEMETRY_MTLS_PASSTHROUGH="false"
    VEHICLE_COMMAND_ENABLED="false"
    FLEET_TELEMETRY_AUTO_APPLY="false"
fi
if [ "$EDGE_TELEMETRY_MTLS_PASSTHROUGH" = "true" ]; then
    TESLA_TELEMETRY_HOST="$TESLA_TELEMETRY_PASSTHROUGH_HOST"
else
    TESLA_TELEMETRY_HOST="$TESLA_ENDPOINT_HOST"
fi
GATEWAY_HTTP_BIND_HOST="$(config_default 'gateway_http.bind_host' "$DEFAULT_GATEWAY_HTTP_BIND_HOST")"
GATEWAY_HTTP_BIND_PORT="$(config_default 'gateway_http.bind_port' "$DEFAULT_GATEWAY_HTTP_BIND_PORT")"
TELEMETRY_BIND_HOST="$(config_default 'telemetry.bind_host' "$DEFAULT_TELEMETRY_BIND_HOST")"
TELEMETRY_BIND_PORT="$(config_default 'telemetry.bind_port' "$DEFAULT_TELEMETRY_BIND_PORT")"
NGINX_PEM_SERVER_NAMES="$(unique_hostnames "$GATEWAY_HOST" "$TESLA_ENDPOINT_HOST" "$TESLA_TELEMETRY_PASSTHROUGH_HOST")"
TELEMETRY_LOG_LEVEL="$(config_default 'telemetry.log_level' "$DEFAULT_TELEMETRY_LOG_LEVEL")"
MQTT_BROKER="$(bashio::config 'mqtt.broker')"
MQTT_PORT="$(config_default 'mqtt.port' "$DEFAULT_MQTT_PORT")"
MQTT_USERNAME="$(bashio::config 'mqtt.username')"
MQTT_PASSWORD="$(bashio::config 'mqtt.password')"
MQTT_TOPIC_BASE="$(bashio::config 'mqtt.topic_base')"
MQTT_CLIENT_ID="$(config_default 'mqtt.client_id' "$DEFAULT_MQTT_CLIENT_ID")"
MQTT_QOS="$(config_default 'mqtt.qos' "$DEFAULT_MQTT_QOS")"
MQTT_CONNECT_TIMEOUT_MS="$(config_default 'mqtt.connect_timeout_ms' "$DEFAULT_MQTT_CONNECT_TIMEOUT_MS")"
MQTT_PUBLISH_TIMEOUT_MS="$(config_default 'mqtt.publish_timeout_ms' "$DEFAULT_MQTT_PUBLISH_TIMEOUT_MS")"
MQTT_KEEP_ALIVE_SECONDS="$(config_default 'mqtt.keep_alive_seconds' "$DEFAULT_MQTT_KEEP_ALIVE_SECONDS")"
VEHICLE_COMMAND_PRIVATE_KEY_PATH="$(config_default 'vehicle_command.private_key_path' "$DEFAULT_VEHICLE_COMMAND_PRIVATE_KEY_PATH")"
VEHICLE_COMMAND_BIND_HOST="$(config_default 'vehicle_command.bind_host' "$DEFAULT_VEHICLE_COMMAND_BIND_HOST")"
VEHICLE_COMMAND_BIND_PORT="$(config_default 'vehicle_command.bind_port' "$DEFAULT_VEHICLE_COMMAND_BIND_PORT")"
VEHICLE_COMMAND_TIMEOUT_SECONDS="$(config_default 'vehicle_command.timeout_seconds' "$DEFAULT_VEHICLE_COMMAND_TIMEOUT_SECONDS")"
TESLA_OAUTH_CLIENT_ID="$(config_default 'tesla_oauth.client_id' '')"
TESLA_OAUTH_CLIENT_SECRET="$(config_default 'tesla_oauth.client_secret' '')"
TESLA_OAUTH_AUTHORIZE_URL="$(config_default 'tesla_oauth.authorize_url' "$DEFAULT_TESLA_OAUTH_AUTHORIZE_URL")"
TESLA_OAUTH_TOKEN_URL="$(config_default 'tesla_oauth.token_url' "$DEFAULT_TESLA_OAUTH_TOKEN_URL")"
TESLA_OAUTH_CALLBACK_PATH="$(config_default 'tesla_oauth.callback_path' "$DEFAULT_TESLA_OAUTH_CALLBACK_PATH")"
TESLA_OAUTH_REDIRECT_URI="$(config_default 'tesla_oauth.redirect_uri' '')"
TESLA_OAUTH_CALLBACK_BIND_HOST="$(config_default 'tesla_oauth.callback_bind_host' "$DEFAULT_TESLA_OAUTH_CALLBACK_BIND_HOST")"
TESLA_OAUTH_CALLBACK_BIND_PORT="$(config_default 'tesla_oauth.callback_bind_port' "$DEFAULT_TESLA_OAUTH_CALLBACK_BIND_PORT")"
TESLA_OAUTH_AUDIENCE="$(resolve_fleet_api_audience)"
TESLA_OAUTH_SCOPE="$(config_default 'tesla_oauth.scope' "$DEFAULT_TESLA_OAUTH_SCOPE")"

legacy_to_addon_config() {
    local configured_path="$1"
    local file_name="$2"
    local legacy_path="/share/tesla/${file_name}"
    local new_path="${ADDON_CONFIG_DIR}/${file_name}"

    if [ "$configured_path" != "$legacy_path" ] && [ "$configured_path" != "$new_path" ]; then
        echo "$configured_path"
        return 0
    fi

    mkdir -p "$ADDON_CONFIG_DIR"

    if [ -f "$legacy_path" ] && [ ! -f "$new_path" ]; then
        mv "$legacy_path" "$new_path"
        bashio::log.info "ℹ️ Migrated private add-on data"
        bashio::log.info "⎣ Moved ${file_name} from ${legacy_path} to ${new_path}"
    fi

    echo "$new_path"
}

TESLA_OAUTH_TOKEN_CACHE_FILE="$(legacy_to_addon_config "$(config_default 'tesla_oauth.token_cache_file' "$DEFAULT_TESLA_OAUTH_TOKEN_CACHE_FILE")" "tesla_oauth_tokens.json")"
TESLA_OAUTH_HANDOFF_FILE="$DEFAULT_TESLA_OAUTH_HANDOFF_FILE"
TESLA_OAUTH_USE_INTEGRATION_HANDOFF=false
TESLA_OAUTH_USE_INTEGRATION_TOKEN=false
TESLA_OAUTH_TOKENS_VERIFIED=false
TESLA_OAUTH_STATE_FILE="$(legacy_to_addon_config "$(config_default 'tesla_oauth.state_file' "$DEFAULT_TESLA_OAUTH_STATE_FILE")" "tesla_oauth_state.json")"
FLEET_TELEMETRY_REQUEST_FILE="$(legacy_to_addon_config "$(config_default 'fleet_telemetry_config.request_file' "$DEFAULT_FLEET_TELEMETRY_REQUEST_FILE")" "fleet_telemetry_config.json")"

if [ -z "$TESLA_OAUTH_REDIRECT_URI" ] || [ "$TESLA_OAUTH_REDIRECT_URI" = "null" ]; then
    TESLA_OAUTH_REDIRECT_URI="$DEFAULT_TESLA_OAUTH_REDIRECT_URI"
fi

TESLA_OAUTH_MY_REDIRECT_LOCATION_BLOCK=""
if [ "$TESLA_OAUTH_REDIRECT_URI" = "$DEFAULT_TESLA_OAUTH_REDIRECT_URI" ]; then
    TESLA_OAUTH_MY_REDIRECT_LOCATION_BLOCK="        location = /_my_redirect/oauth {
            return 302 \$scheme://\$host${TESLA_OAUTH_CALLBACK_PATH}\$is_args\$args;
        }"
fi

if [ "$TESLA_ENDPOINT_HTTPS_PORT" = "$GATEWAY_TLS_PORT" ] && [ "$TESLA_ENDPOINT_HTTPS_PORT" != "443" ]; then
    bashio::log.info "ℹ️ Using Tesla endpoint HTTPS port 443 because the Fleet Telemetry API requires it"
    bashio::log.info "⎣ Make sure the router forwards ${TESLA_ENDPOINT_HOST}:443 to the gateway listener at ${GATEWAY_HOST}:${GATEWAY_TLS_PORT}"
    TESLA_ENDPOINT_HTTPS_PORT="443"
fi

if [ ! -f "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" ] && [ -f "${HOMEASSISTANT_CONFIG_DIR}/tesla_fleet.key" ]; then
    bashio::log.info "Using detected Tesla private key at ${HOMEASSISTANT_CONFIG_DIR}/tesla_fleet.key because configured vehicle_command.private_key_path was not found: ${VEHICLE_COMMAND_PRIVATE_KEY_PATH}"
    VEHICLE_COMMAND_PRIVATE_KEY_PATH="${HOMEASSISTANT_CONFIG_DIR}/tesla_fleet.key"
fi

case "$MQTT_BROKER" in
    tcp://*|ssl://*|ws://*|wss://*)
        ;;
    *)
        MQTT_BROKER="tcp://${MQTT_BROKER}"
        ;;
esac

if [ "$(config_bool_default 'telemetry.reliable_ack' '' "$DEFAULT_TELEMETRY_RELIABLE_ACK")" = "true" ]; then
    TELEMETRY_RELIABLE_ACK=true
else
    TELEMETRY_RELIABLE_ACK=false
fi

if [ "$(config_bool_default 'telemetry.transmit_decoded_records' '' "$DEFAULT_TELEMETRY_TRANSMIT_DECODED_RECORDS")" = "true" ]; then
    TELEMETRY_TRANSMIT_DECODED_RECORDS=true
else
    TELEMETRY_TRANSMIT_DECODED_RECORDS=false
fi

if [ "$(config_bool_default 'mqtt.retained' '' "$DEFAULT_MQTT_RETAINED")" = "true" ]; then
    MQTT_RETAINED=true
else
    MQTT_RETAINED=false
fi

TELEMETRY_DELIVERY_POLICY="$(config_default 'telemetry.delivery_policy' "$DEFAULT_TELEMETRY_DELIVERY_POLICY")"

if [ "$(config_bool_with_legacy_chain "$DEFAULT_TELEMETRY_ACCESS_LOG" advanced.telemetry_access_log logging.telemetry_access_log edge.access_log)" = "true" ]; then
    GATEWAY_ACCESS_LOG="access_log /dev/stdout tesla_gateway;"
else
    GATEWAY_ACCESS_LOG="access_log off;"
fi
TELEMETRY_ACCESS_LOG="$GATEWAY_ACCESS_LOG"

if [ "$(config_bool_with_legacy_chain "$DEFAULT_TELEMETRY_ACCESS_LOG" advanced.telemetry_access_log logging.telemetry_access_log edge.access_log)" = "true" ]; then
    STREAM_ACCESS_LOG="access_log /dev/stdout tesla_stream;"
else
    STREAM_ACCESS_LOG="access_log off;"
fi

# User-fixable startup failures must not exit non-zero: s6 would restart the
# service every second and flood the logs. Ask Supervisor to stop the add-on.
stop_after_config_error() {
    local message="$1"

    bashio::log.fatal "${message}"
    bashio::log.fatal "Stopping the add-on. Fix the configuration, then start it again."
    bashio::addon.stop
    # Supervisor stop is asynchronous; stay put so s6 cannot restart-loop first.
    exec sleep infinity
}

fail_next_step() {
    local problem="$1"
    local next_step="$2"

    bashio::log.error "⚠️ ACTION REQUIRED"
    bashio::log.error "⎢ Problem: ${problem}"
    bashio::log.error "⎣ Next step: ${next_step}"
    stop_after_config_error "Tesla Fleet Gateway onboarding is incomplete"
}

case "$TESLA_OAUTH_CALLBACK_PATH" in
    /*)
        ;;
    *)
        fail_next_step \
            "tesla_oauth.callback_path must start with /" \
            "Set tesla_oauth.callback_path to a path such as /tesla/callback"
        ;;
esac

case "$TESLA_OAUTH_CALLBACK_PATH" in
    *[!A-Za-z0-9_./-]*)
        fail_next_step \
            "tesla_oauth.callback_path contains invalid characters" \
            "Use only letters, numbers, slash, dot, underscore, and dash"
        ;;
esac

TESLA_OAUTH_CALLBACK_LOCATION_BLOCK="        location = ${TESLA_OAUTH_CALLBACK_PATH} {
            ${GATEWAY_ACCESS_LOG}
            proxy_pass http://${TESLA_OAUTH_CALLBACK_BIND_HOST}:${TESLA_OAUTH_CALLBACK_BIND_PORT};
            proxy_http_version 1.1;
            proxy_set_header Host \$host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For \$remote_addr;
        }"

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
    local detail="${2:-}"

    bashio::log.info "✅ ${title}"
    if [ -n "$detail" ]; then
        bashio::log.info "⎣ ${detail}"
    fi
}

require_hostname() {
    local label="$1"
    local host="$2"

    if ! printf '%s' "$host" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$'; then
        fail_next_step \
            "${label} is not a valid hostname: ${host}" \
            "Use a DNS hostname without spaces, paths, or special characters"
    fi
}

if [ "$TESLA_ENDPOINT_HOST" = "tesla.example.com" ] || [ "$GATEWAY_HOST" = "tesla.example.com" ]; then
    fail_next_step \
        "Add-on domain is still the default placeholder (tesla.example.com)" \
        "Set a real public domain in add-on options before starting telemetry"
fi

require_hostname "Domain" "$GATEWAY_HOST"
require_hostname "Tesla endpoint host" "$TESLA_ENDPOINT_HOST"
require_hostname "Telemetry host" "$TESLA_TELEMETRY_PASSTHROUGH_HOST"

case "$EDGE_TLS_CERT" in
    /ssl/*) ;;
    *)
        fail_next_step \
            "TLS certificate path must be under /ssl/: ${EDGE_TLS_CERT}" \
            "Set advanced.certfile to a file under /ssl (for example /ssl/fullchain.pem from the Let's Encrypt add-on)"
        ;;
esac
case "$EDGE_TLS_KEY" in
    /ssl/*) ;;
    *)
        fail_next_step \
            "TLS private key path must be under /ssl/: ${EDGE_TLS_KEY}" \
            "Set advanced.keyfile to a file under /ssl (for example /ssl/privkey.pem from the Let's Encrypt add-on)"
        ;;
esac

sync_legacy_oauth_token_cache() {
    local integration_file="$DEFAULT_TESLA_OAUTH_INTEGRATION_TOKEN_FILE"

    # Do not copy long-lived refresh tokens into addon_config. The supported path
    # is gateway_handoff.json (access token only) from tesla_fleet_stream.
    if [ -f "$integration_file" ] \
        && jq -e '.refresh_token | type == "string" and length > 0' "$integration_file" >/dev/null 2>&1; then
        warn_next_step \
            "Deprecated oauth_tokens.json with a refresh token is still present" \
            "Reload tesla_fleet_stream so it exports gateway_handoff.json and deletes the legacy file; the add-on no longer copies refresh tokens"
    fi
}

handoff_access_token_valid() {
    local handoff_file="$1"
    local expires_at

    if [ ! -f "$handoff_file" ]; then
        return 1
    fi

    if ! jq -e '.access_token | type == "string" and length > 0' "$handoff_file" >/dev/null 2>&1; then
        return 1
    fi

    expires_at="$(jq -r '.expires_at // empty' "$handoff_file")"
    if [ -z "$expires_at" ] || [ "$expires_at" = "null" ]; then
        return 1
    fi

    [ "$expires_at" -gt "$(date +%s)" ]
}

resolve_oauth_handoff() {
    local handoff_file="$DEFAULT_TESLA_OAUTH_HANDOFF_FILE"
    local handoff_audience=""

    if handoff_access_token_valid "$handoff_file"; then
        TESLA_OAUTH_USE_INTEGRATION_HANDOFF=true
        TESLA_OAUTH_USE_INTEGRATION_TOKEN=true
        handoff_audience="$(jq -r '.fleet_api_base // empty' "$handoff_file")"
        case "$handoff_audience" in
            https://fleet-api.prd.na.vn.cloud.tesla.com|\
            https://fleet-api.prd.eu.vn.cloud.tesla.com|\
            https://fleet-api.prd.cn.vn.cloud.tesla.cn)
                TESLA_OAUTH_AUDIENCE="$handoff_audience"
                ;;
            "")
                ;;
            *)
                warn_next_step \
                    "gateway_handoff.json has an unsupported fleet_api_base" \
                    "Set Fleet API base in tesla_fleet_stream options to the official NA, EU, or CN host"
                ;;
        esac
        log_success \
            "Tesla OAuth is managed by Home Assistant" \
            "Access token handoff: ${handoff_file}"
        return 0
    fi

    if [ -f "$handoff_file" ] \
        && jq -e '.access_token | type == "string" and length > 0' "$handoff_file" >/dev/null 2>&1; then
        warn_next_step \
            "Tesla OAuth access token from tesla_fleet_stream has expired" \
            "Re-authenticate the tesla_fleet_stream integration in Home Assistant"
    fi

    sync_legacy_oauth_token_cache
}

sync_oauth_token_cache() {
    resolve_oauth_handoff
}

sync_oauth_token_cache

require_file() {
    local label="$1"
    local path="$2"
    local next_step="$3"

    if [ ! -f "$path" ]; then
        fail_next_step "${label} not found at ${path}" "$next_step"
    fi
}

require_valid_public_key() {
    local path="$1"

    if ! openssl ec -pubin -in "$path" -noout >/dev/null 2>&1; then
        fail_next_step \
            "Tesla public key PEM is not a valid EC public key: ${path}" \
            "Regenerate it with: openssl ec -in ${VEHICLE_COMMAND_PRIVATE_KEY_PATH} -pubout -out ${path}"
    fi
}

require_valid_private_key() {
    local path="$1"

    if ! openssl ec -in "$path" -noout >/dev/null 2>&1; then
        fail_next_step \
            "Vehicle command private key is not a valid EC private key: ${path}" \
            "Regenerate a prime256v1 private key and place it at ${path}"
    fi
}

check_key_pair_match() {
    local private_key_path="$1"
    local public_key_path="$2"
    local generated_public_key

    if [ ! -f "$private_key_path" ]; then
        return 0
    fi

    generated_public_key="$(mktemp)"
    if ! openssl ec -in "$private_key_path" -pubout -out "$generated_public_key" >/dev/null 2>&1; then
        rm -f "$generated_public_key"
        return 0
    fi

    if ! cmp -s "$generated_public_key" "$public_key_path"; then
        rm -f "$generated_public_key"
        fail_next_step \
            "Vehicle command private key does not match the hosted Tesla public key PEM" \
            "Regenerate ${public_key_path} from ${private_key_path}, then re-register and re-pair the virtual key if Tesla already saw the old public key"
    fi

    rm -f "$generated_public_key"
}

check_port_available() {
    local label="$1"
    local host="$2"
    local port="$3"
    local next_step="$4"
    local probe_log
    local probe_pid
    local output

    probe_log="$(mktemp)"
    busybox nc -l -s "$host" -p "$port" >/dev/null 2>"$probe_log" &
    probe_pid=$!
    sleep 1

    if kill -0 "$probe_pid" 2>/dev/null; then
        kill "$probe_pid" 2>/dev/null || true
        wait "$probe_pid" 2>/dev/null || true
        rm -f "$probe_log"
        return 0
    fi

    output="$(cat "$probe_log")"
    rm -f "$probe_log"

    if [ -z "$output" ]; then
        output="bind attempt failed"
    fi

    fail_next_step "${label} ${host}:${port} is unavailable: ${output}" "$next_step"
}

PUBLIC_KEY_PATH="${EDGE_PEM_ROOT}${EDGE_PEM_PUBLIC_PATH}"

require_file \
    "TLS certificate" \
    "$EDGE_TLS_CERT" \
    "Install or renew the Home Assistant SSL certificate for this domain"
require_file \
    "TLS private key" \
    "$EDGE_TLS_KEY" \
    "Install or renew the Home Assistant SSL certificate for this domain"
log_success "TLS files found" "Certificate: ${EDGE_TLS_CERT}; key: ${EDGE_TLS_KEY}"

# Home Assistant config is mounted read-only, so never try to create
# /homeassistant/tesla_fleet.key here. Derive the public PEM from the official
# integration's existing private key (or an operator-provided key) instead.
if [ ! -f "$PUBLIC_KEY_PATH" ] && [ -f "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" ]; then
    mkdir -p "$(dirname "$PUBLIC_KEY_PATH")"
    if openssl ec -in "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" -pubout -out "$PUBLIC_KEY_PATH" >/dev/null 2>&1; then
        chmod 600 "$PUBLIC_KEY_PATH" || true
        bashio::log.info "ℹ️ Derived Tesla public key PEM from existing private key"
        bashio::log.info "⎣ Wrote ${PUBLIC_KEY_PATH} from ${VEHICLE_COMMAND_PRIVATE_KEY_PATH}"
    fi
fi

if [ ! -f "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" ]; then
    fail_next_step \
        "Vehicle command private key not found at ${VEHICLE_COMMAND_PRIVATE_KEY_PATH}" \
        "Configure the official Tesla Fleet integration first (it creates /config/tesla_fleet.key), or place a matching EC private key there"
fi

require_file \
    "Tesla public key PEM" \
    "$PUBLIC_KEY_PATH" \
    "Place the matching public key at ${PUBLIC_KEY_PATH}, or ensure the private key at ${VEHICLE_COMMAND_PRIVATE_KEY_PATH} can be read so the add-on can derive it"
require_valid_public_key "$PUBLIC_KEY_PATH"
log_success "Tesla public key PEM is present and valid" "Gateway listener URL: https://${GATEWAY_HOST}:${GATEWAY_TLS_PORT}${EDGE_PEM_PUBLIC_PATH}"

if [ "$VEHICLE_COMMAND_ENABLED" = "true" ]; then
    require_file \
        "Vehicle command private key" \
        "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" \
        "Place the private key at ${VEHICLE_COMMAND_PRIVATE_KEY_PATH}, or disable hosts.telemetry_enabled until activation"
    require_valid_private_key "$VEHICLE_COMMAND_PRIVATE_KEY_PATH"
    check_key_pair_match "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" "$PUBLIC_KEY_PATH"
    log_success "Vehicle Command Proxy key is ready" "Private key matches the hosted Tesla public key PEM"
elif [ -f "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" ]; then
    require_valid_private_key "$VEHICLE_COMMAND_PRIVATE_KEY_PATH"
    check_key_pair_match "$VEHICLE_COMMAND_PRIVATE_KEY_PATH" "$PUBLIC_KEY_PATH"
    log_success "Vehicle command private key is present" "Private key matches the hosted Tesla public key PEM; enable hosts.telemetry_enabled when ready to apply telemetry config"
else
    warn_next_step \
        "Vehicle Command Proxy is disabled and no private key was found at ${VEHICLE_COMMAND_PRIVATE_KEY_PATH}" \
        "Before applying Fleet Telemetry config, place the private key there and enable hosts.telemetry_enabled"
fi

if { [ -n "$MQTT_USERNAME" ] && [ -z "$MQTT_PASSWORD" ]; } || { [ -z "$MQTT_USERNAME" ] && [ -n "$MQTT_PASSWORD" ]; }; then
    fail_next_step \
        "MQTT username and password must both be set or both be empty" \
        "Set both mqtt.username and mqtt.password, or clear both if the broker allows anonymous access"
fi
log_success "MQTT configuration is internally consistent" "Broker: ${MQTT_BROKER}:${MQTT_PORT}; topic base: ${MQTT_TOPIC_BASE}"

if [ "$GATEWAY_TLS_PORT" != "443" ]; then
    log_success \
        "Using non-standard gateway listener TLS port ${GATEWAY_TLS_PORT}" \
        "This is valid when the router forwards ${TESLA_ENDPOINT_HOST}:443 to gateway listener ${GATEWAY_HOST}:${GATEWAY_TLS_PORT}"
fi

log_success \
    "Tesla endpoint HTTPS port is 443" \
    "Forward ${TESLA_ENDPOINT_HOST}:443 to gateway listener ${GATEWAY_HOST}:${GATEWAY_TLS_PORT}"

if [ "$EDGE_TELEMETRY_MTLS_PASSTHROUGH" = "true" ]; then
    if [ "$TESLA_TELEMETRY_PASSTHROUGH_HOST" = "$TESLA_ENDPOINT_HOST" ]; then
        warn_next_step \
            "Fleet Telemetry mTLS passthrough cannot share the PEM hostname" \
            "Set advanced.telemetry_host to a dedicated hostname (for example telemetry.${TESLA_ENDPOINT_HOST}) or disable hosts.telemetry_enabled"
    else
        log_success \
            "Fleet Telemetry mTLS passthrough is enabled" \
            "Vehicles connect with mTLS to ${TESLA_TELEMETRY_HOST}:443 via TCP passthrough (SNI) to ${TELEMETRY_BIND_HOST}:${TELEMETRY_BIND_PORT}; PEM/OAuth stay on ${TESLA_ENDPOINT_HOST}:443"
    fi
else
    log_success \
        "Public HTTPS serves PEM and OAuth directly on the gateway listener" \
        "nginx terminates TLS on ${GATEWAY_HOST}:${GATEWAY_TLS_PORT} (same as the working nginx proxy on :8443); enable hosts.telemetry_enabled after registering the telemetry hostname in Tesla"
fi

if [ "$TESLA_OAUTH_USE_INTEGRATION_HANDOFF" = "true" ]; then
    log_success \
        "Tesla OAuth credentials stay in Home Assistant Application Credentials" \
        "Complete OAuth in the tesla_fleet_stream integration; the add-on reads ${TESLA_OAUTH_HANDOFF_FILE}"
elif [ -n "$TESLA_OAUTH_CLIENT_ID" ] && [ "$TESLA_OAUTH_CLIENT_ID" != "null" ] \
    && [ -n "$TESLA_OAUTH_CLIENT_SECRET" ] && [ "$TESLA_OAUTH_CLIENT_SECRET" != "null" ]; then
    log_success \
        "Legacy Tesla OAuth app credentials are configured in add-on options" \
        "Deprecated: remove client_id/client_secret and complete OAuth in the tesla_fleet_stream integration instead"
else
    warn_next_step \
        "Tesla OAuth is not configured" \
        "Add the tesla_fleet_stream integration and complete Tesla OAuth in Home Assistant"
fi

if [ "$TESLA_OAUTH_USE_INTEGRATION_HANDOFF" = "true" ]; then
    if /usr/local/bin/tesla_oauth.py verify; then
        TESLA_OAUTH_TOKENS_VERIFIED=true
    else
        warn_next_step \
            "Tesla OAuth handoff token could not be verified" \
            "Re-authenticate the tesla_fleet_stream integration in Home Assistant"
    fi
elif [ -f "$TESLA_OAUTH_TOKEN_CACHE_FILE" ] \
    && jq -e '.access_token | type == "string" and length > 0' "$TESLA_OAUTH_TOKEN_CACHE_FILE" >/dev/null 2>&1 \
    && jq -e '.refresh_token | type == "string" and length > 0' "$TESLA_OAUTH_TOKEN_CACHE_FILE" >/dev/null 2>&1; then
    if [ -n "$TESLA_OAUTH_CLIENT_ID" ] && [ "$TESLA_OAUTH_CLIENT_ID" != "null" ] \
        && [ -n "$TESLA_OAUTH_CLIENT_SECRET" ] && [ "$TESLA_OAUTH_CLIENT_SECRET" != "null" ]; then
        if /usr/local/bin/tesla_oauth.py verify; then
            TESLA_OAUTH_TOKENS_VERIFIED=true
        else
            warn_next_step \
                "Legacy Tesla OAuth tokens are present but could not be verified" \
                "Complete OAuth in tesla_fleet_stream or verify legacy client credentials and Fleet API region"
        fi
    else
        log_success "Legacy Tesla OAuth tokens are cached" "Using token cache at ${TESLA_OAUTH_TOKEN_CACHE_FILE}"
    fi
elif [ "$VEHICLE_COMMAND_ENABLED" = "true" ]; then
    warn_next_step \
        "Tesla OAuth tokens are missing or incomplete" \
        "Add the tesla_fleet_stream integration and complete Tesla OAuth in Home Assistant"
fi

if [ "$TESLA_OAUTH_USE_INTEGRATION_HANDOFF" = "true" ]; then
    log_success \
        "Tesla OAuth callback is managed by Home Assistant" \
        "Complete OAuth in the tesla_fleet_stream integration; redirect URI https://my.home-assistant.io/redirect/oauth"
    TESLA_OAUTH_CALLBACK_LOCATION_BLOCK=""
    TESLA_OAUTH_MY_REDIRECT_LOCATION_BLOCK=""
elif [ -n "$TESLA_OAUTH_CLIENT_ID" ] && [ "$TESLA_OAUTH_CLIENT_ID" != "null" ] \
    && [ -n "$TESLA_OAUTH_CLIENT_SECRET" ] && [ "$TESLA_OAUTH_CLIENT_SECRET" != "null" ]; then
    if [ "$TESLA_OAUTH_REDIRECT_URI" = "$DEFAULT_TESLA_OAUTH_REDIRECT_URI" ]; then
        log_success "Legacy Tesla OAuth callback is configured" "Redirect URI: ${TESLA_OAUTH_REDIRECT_URI}; register this in the Tesla developer app; set My Home Assistant to $(https_listener_url "$GATEWAY_HOST" "$GATEWAY_TLS_PORT" "/")"
    else
        log_success "Legacy Tesla OAuth callback is configured" "Redirect URI: ${TESLA_OAUTH_REDIRECT_URI}; callback listener: ${TESLA_OAUTH_CALLBACK_BIND_HOST}:${TESLA_OAUTH_CALLBACK_BIND_PORT}${TESLA_OAUTH_CALLBACK_PATH}"
    fi
else
    warn_next_step \
        "Tesla OAuth callback is not available" \
        "Complete OAuth in the tesla_fleet_stream integration in Home Assistant"
fi

check_port_available \
    "Gateway listener TLS port" \
    "0.0.0.0" \
    "$GATEWAY_TLS_PORT" \
    "Change advanced.tls_port or stop the service already listening on ${GATEWAY_TLS_PORT}"
if [ "$EDGE_TELEMETRY_MTLS_PASSTHROUGH" = "true" ]; then
    log_success "Gateway listener TLS port is available" "nginx stream can bind 0.0.0.0:${GATEWAY_TLS_PORT}"
    check_port_available \
        "Gateway internal HTTP port" \
        "$GATEWAY_HTTP_BIND_HOST" \
        "$GATEWAY_HTTP_BIND_PORT" \
        "Change gateway_http.bind_port or stop the service already listening on ${GATEWAY_HTTP_BIND_HOST}:${GATEWAY_HTTP_BIND_PORT}"
    log_success "Gateway internal HTTP port is available" "nginx can bind ${GATEWAY_HTTP_BIND_HOST}:${GATEWAY_HTTP_BIND_PORT}"
else
    log_success "Gateway listener TLS port is available" "nginx https can bind 0.0.0.0:${GATEWAY_TLS_PORT}"
fi
check_port_available \
    "Telemetry bind port" \
    "$TELEMETRY_BIND_HOST" \
    "$TELEMETRY_BIND_PORT" \
    "Change telemetry.bind_port or stop the service already listening on ${TELEMETRY_BIND_HOST}:${TELEMETRY_BIND_PORT}"
log_success "Local telemetry port is available" "fleet-telemetry can bind ${TELEMETRY_BIND_HOST}:${TELEMETRY_BIND_PORT}"
if [ "$TESLA_TELEMETRY_PASSTHROUGH_HOST" != "$TESLA_ENDPOINT_HOST" ] \
    && ! openssl x509 -in "$EDGE_TLS_CERT" -noout -text 2>/dev/null | grep -Fq "DNS:${TESLA_TELEMETRY_PASSTHROUGH_HOST}"; then
    warn_next_step \
        "TLS certificate does not list the Fleet Telemetry passthrough hostname" \
        "Reissue the Home Assistant certificate with DNS:${TESLA_TELEMETRY_PASSTHROUGH_HOST} or set advanced.telemetry_host to a name already on the certificate"
fi
if [ "$EDGE_TELEMETRY_MTLS_PASSTHROUGH" = "true" ]; then
    log_success \
        "Fleet Telemetry hostname is configured for mTLS passthrough" \
        "Vehicles connect to ${TESLA_TELEMETRY_HOST}:443; add DNS for ${TESLA_TELEMETRY_PASSTHROUGH_HOST} pointing at the same address as ${TESLA_ENDPOINT_HOST}"
elif [ "$TESLA_TELEMETRY_PASSTHROUGH_HOST" != "$TESLA_ENDPOINT_HOST" ]; then
    log_success \
        "Telemetry passthrough hostname serves PEM until mTLS is enabled" \
        "Register ${TESLA_TELEMETRY_PASSTHROUGH_HOST} in the Tesla developer app, then enable hosts.telemetry_enabled"
else
    warn_next_step \
        "Vehicle mTLS requires a dedicated telemetry hostname" \
        "Register telemetry.${TESLA_ENDPOINT_HOST} in Tesla after verifying its PEM, then enable hosts.telemetry_enabled"
fi
if [ "$TESLA_OAUTH_USE_INTEGRATION_HANDOFF" != "true" ] \
    && [ -n "$TESLA_OAUTH_CLIENT_ID" ] && [ "$TESLA_OAUTH_CLIENT_ID" != "null" ] \
    && [ -n "$TESLA_OAUTH_CLIENT_SECRET" ] && [ "$TESLA_OAUTH_CLIENT_SECRET" != "null" ]; then
    check_port_available \
        "Tesla OAuth callback port" \
        "$TESLA_OAUTH_CALLBACK_BIND_HOST" \
        "$TESLA_OAUTH_CALLBACK_BIND_PORT" \
        "Change tesla_oauth.callback_bind_port or stop the service already listening on ${TESLA_OAUTH_CALLBACK_BIND_HOST}:${TESLA_OAUTH_CALLBACK_BIND_PORT}"
    log_success "Tesla OAuth callback port is available" "Callback service can bind ${TESLA_OAUTH_CALLBACK_BIND_HOST}:${TESLA_OAUTH_CALLBACK_BIND_PORT}"
fi

mkdir -p /etc/fleet-telemetry /etc/nginx

# Build fleet-telemetry config with jq so MQTT credentials are JSON-escaped.
jq -n \
    --arg host "$TELEMETRY_BIND_HOST" \
    --argjson port "$TELEMETRY_BIND_PORT" \
    --arg log_level "$TELEMETRY_LOG_LEVEL" \
    --argjson reliable_ack "$TELEMETRY_RELIABLE_ACK" \
    --argjson transmit_decoded_records "$TELEMETRY_TRANSMIT_DECODED_RECORDS" \
    --arg delivery_policy "$TELEMETRY_DELIVERY_POLICY" \
    --arg server_cert "$EDGE_TLS_CERT" \
    --arg server_key "$EDGE_TLS_KEY" \
    --arg mqtt_broker "${MQTT_BROKER}:${MQTT_PORT}" \
    --arg mqtt_client_id "$MQTT_CLIENT_ID" \
    --arg mqtt_username "$MQTT_USERNAME" \
    --arg mqtt_password "$MQTT_PASSWORD" \
    --arg mqtt_topic_base "$MQTT_TOPIC_BASE" \
    --argjson mqtt_qos "$MQTT_QOS" \
    --argjson mqtt_retained "$MQTT_RETAINED" \
    --argjson mqtt_connect_timeout_ms "$MQTT_CONNECT_TIMEOUT_MS" \
    --argjson mqtt_publish_timeout_ms "$MQTT_PUBLISH_TIMEOUT_MS" \
    --argjson mqtt_keep_alive_seconds "$MQTT_KEEP_ALIVE_SECONDS" \
    '{
      host: $host,
      port: $port,
      log_level: $log_level,
      json_log_enable: true,
      reliable_ack: $reliable_ack,
      transmit_decoded_records: $transmit_decoded_records,
      delivery_policy: $delivery_policy,
      logger: { verbose: false },
      records: {
        alerts: ["logger", "mqtt"],
        connectivity: ["logger", "mqtt"],
        errors: ["logger", "mqtt"],
        V: ["logger", "mqtt"]
      },
      tls: {
        server_cert: $server_cert,
        server_key: $server_key
      },
      mqtt: {
        broker: $mqtt_broker,
        client_id: $mqtt_client_id,
        username: $mqtt_username,
        password: $mqtt_password,
        topic_base: $mqtt_topic_base,
        qos: $mqtt_qos,
        retained: $mqtt_retained,
        connect_timeout_ms: $mqtt_connect_timeout_ms,
        publish_timeout_ms: $mqtt_publish_timeout_ms,
        keep_alive_seconds: $mqtt_keep_alive_seconds
      }
    }' > /etc/fleet-telemetry/config.json
chmod 600 /etc/fleet-telemetry/config.json

NGINX_LOAD_MODULE=""
NGINX_STREAM_BLOCK=""
NGINX_HTTP_LISTEN=""
if [ "$EDGE_TELEMETRY_MTLS_PASSTHROUGH" = "true" ]; then
    STREAM_MAP_ENTRIES=""
    STREAM_MAP_HOSTS_SEEN=""
    append_stream_map_entry "$TESLA_ENDPOINT_HOST" gateway_http
    append_stream_map_entry "$GATEWAY_HOST" gateway_http
    if [ "$TESLA_TELEMETRY_PASSTHROUGH_HOST" != "$TESLA_ENDPOINT_HOST" ]; then
        append_stream_map_entry "$TESLA_TELEMETRY_PASSTHROUGH_HOST" fleet_telemetry
    fi

    NGINX_LOAD_MODULE="load_module /usr/lib/nginx/modules/ngx_stream_module.so;"
    NGINX_STREAM_BLOCK="stream {
    log_format tesla_stream 'tesla_stream remote=\$remote_addr sni=\"\$ssl_preread_server_name\" upstream=\"\$upstream_addr\"';
    ${STREAM_ACCESS_LOG}

    upstream fleet_telemetry {
        server ${TELEMETRY_BIND_HOST}:${TELEMETRY_BIND_PORT};
    }

    upstream gateway_http {
        server ${GATEWAY_HTTP_BIND_HOST}:${GATEWAY_HTTP_BIND_PORT};
    }

    map \$ssl_preread_server_name \$stream_upstream {${STREAM_MAP_ENTRIES}
        default gateway_http;
    }

    server {
        listen ${GATEWAY_TLS_PORT};
        listen [::]:${GATEWAY_TLS_PORT};
        ssl_preread on;
        proxy_pass \$stream_upstream;
        proxy_timeout 3600s;
    }
}
"
    NGINX_HTTP_LISTEN="        listen ${GATEWAY_HTTP_BIND_HOST}:${GATEWAY_HTTP_BIND_PORT} ssl;
        listen [::1]:${GATEWAY_HTTP_BIND_PORT} ssl;"
else
    NGINX_HTTP_LISTEN="        listen ${GATEWAY_TLS_PORT} ssl;
        listen [::]:${GATEWAY_TLS_PORT} ssl;"
fi

cat > /etc/nginx/nginx.conf <<EOF
${NGINX_LOAD_MODULE}

events {}

${NGINX_STREAM_BLOCK}
http {
    log_format tesla_gateway 'tesla_gateway remote=\$remote_addr method=\$request_method uri=\$uri status=\$status range="\$http_range" ua="\$http_user_agent"';
    access_log off;
    log_not_found off;
    server_tokens off;

    server {
${NGINX_HTTP_LISTEN}
        http2 on;
        server_name ${NGINX_PEM_SERVER_NAMES};

        ssl_certificate ${EDGE_TLS_CERT};
        ssl_certificate_key ${EDGE_TLS_KEY};
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        location ^~ /.well-known/appspecific/ {
            alias ${EDGE_PEM_ROOT}/.well-known/appspecific/;
            default_type application/x-pem-file;
            ${GATEWAY_ACCESS_LOG}
            add_header Cache-Control "public, max-age=300";
        }

${TESLA_OAUTH_MY_REDIRECT_LOCATION_BLOCK}

${TESLA_OAUTH_CALLBACK_LOCATION_BLOCK}

        location / {
            access_log off;
            return 444;
        }
    }
}
EOF

nginx -t -c /etc/nginx/nginx.conf >/dev/null
if [ "$EDGE_TELEMETRY_MTLS_PASSTHROUGH" = "true" ]; then
    log_success "nginx edge configuration is valid" "SNI stream passthrough and PEM routing were rendered successfully"
    bashio::log.info "Rendered config: gateway listener ${GATEWAY_HOST}:${GATEWAY_TLS_PORT} (SNI stream), Tesla endpoint https://${TESLA_ENDPOINT_HOST}:${TESLA_ENDPOINT_HTTPS_PORT}, Fleet Telemetry ${TESLA_TELEMETRY_HOST}:443 (mTLS passthrough) → ${TELEMETRY_BIND_HOST}:${TELEMETRY_BIND_PORT}, MQTT ${MQTT_BROKER}:${MQTT_PORT}"
else
    log_success "nginx edge configuration is valid" "Direct HTTPS PEM/OAuth on ${GATEWAY_HOST}:${GATEWAY_TLS_PORT} (matches nginx proxy behavior)"
    bashio::log.info "Rendered config: gateway listener ${GATEWAY_HOST}:${GATEWAY_TLS_PORT} (direct HTTPS), Tesla endpoint https://${TESLA_ENDPOINT_HOST}:${TESLA_ENDPOINT_HTTPS_PORT}, Fleet Telemetry ${TESLA_TELEMETRY_HOST}:443 (mTLS passthrough ${EDGE_TELEMETRY_MTLS_PASSTHROUGH}) → ${TELEMETRY_BIND_HOST}:${TELEMETRY_BIND_PORT}, MQTT ${MQTT_BROKER}:${MQTT_PORT}"
fi
log_success "Tesla Fleet Gateway runtime is ready to start"

write_runtime_env_value() {
    printf "'%s'" "${1//\'/\'\\\'\'}"
}

mkdir -p /run
{
    printf 'GATEWAY_HOST=%s\n' "$(write_runtime_env_value "$GATEWAY_HOST")"
    printf 'EDGE_PEM_ROOT=%s\n' "$(write_runtime_env_value "$EDGE_PEM_ROOT")"
    printf 'EDGE_PEM_PUBLIC_PATH=%s\n' "$(write_runtime_env_value "$EDGE_PEM_PUBLIC_PATH")"
    printf 'TESLA_OAUTH_TOKENS_VERIFIED=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_TOKENS_VERIFIED")"
    printf 'TESLA_TELEMETRY_HOST=%s\n' "$(write_runtime_env_value "$TESLA_TELEMETRY_HOST")"
    printf 'TESLA_ENDPOINT_HOST=%s\n' "$(write_runtime_env_value "$TESLA_ENDPOINT_HOST")"
    printf 'TESLA_ENDPOINT_HTTPS_PORT=%s\n' "$(write_runtime_env_value "$TESLA_ENDPOINT_HTTPS_PORT")"
    printf 'FLEET_TELEMETRY_REQUEST_FILE=%s\n' "$(write_runtime_env_value "$FLEET_TELEMETRY_REQUEST_FILE")"
    printf 'VEHICLE_COMMAND_BIND_HOST=%s\n' "$(write_runtime_env_value "$VEHICLE_COMMAND_BIND_HOST")"
    printf 'VEHICLE_COMMAND_BIND_PORT=%s\n' "$(write_runtime_env_value "$VEHICLE_COMMAND_BIND_PORT")"
    printf 'EDGE_TLS_CERT=%s\n' "$(write_runtime_env_value "$EDGE_TLS_CERT")"
    printf 'TESLA_OAUTH_TOKEN_CACHE_FILE=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_TOKEN_CACHE_FILE")"
    printf 'TESLA_OAUTH_HANDOFF_FILE=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_HANDOFF_FILE")"
    printf 'TESLA_OAUTH_USE_INTEGRATION_HANDOFF=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_USE_INTEGRATION_HANDOFF")"
    printf 'TESLA_OAUTH_CLIENT_ID=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_CLIENT_ID")"
    # Never persist the client secret when using integration handoff. For the
    # deprecated legacy OAuth path only, pass it through the runtime env file.
    if [ "$TESLA_OAUTH_USE_INTEGRATION_HANDOFF" != "true" ]; then
        printf 'TESLA_OAUTH_CLIENT_SECRET=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_CLIENT_SECRET")"
    fi
    printf 'TESLA_OAUTH_TOKEN_URL=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_TOKEN_URL")"
    printf 'TESLA_OAUTH_AUDIENCE=%s\n' "$(write_runtime_env_value "$TESLA_OAUTH_AUDIENCE")"
    printf 'EDGE_TELEMETRY_MTLS_PASSTHROUGH=%s\n' "$(write_runtime_env_value "$EDGE_TELEMETRY_MTLS_PASSTHROUGH")"
    printf 'FLEET_TELEMETRY_AUTO_APPLY=%s\n' "$(write_runtime_env_value "$FLEET_TELEMETRY_AUTO_APPLY")"
    printf 'VEHICLE_COMMAND_ENABLED=%s\n' "$(write_runtime_env_value "$VEHICLE_COMMAND_ENABLED")"
    printf 'TESLA_TELEMETRY_PASSTHROUGH_HOST=%s\n' "$(write_runtime_env_value "$TESLA_TELEMETRY_PASSTHROUGH_HOST")"
    printf 'GATEWAY_TLS_PORT=%s\n' "$(write_runtime_env_value "$GATEWAY_TLS_PORT")"
    printf 'GATEWAY_HTTP_BIND_PORT=%s\n' "$(write_runtime_env_value "$GATEWAY_HTTP_BIND_PORT")"
    printf 'TELEMETRY_RECOVERY_ENABLED=%s\n' "$(write_runtime_env_value "$DEFAULT_TELEMETRY_RECOVERY_ENABLED")"
    printf 'TELEMETRY_RECOVERY_DISCONNECT_SECONDS=%s\n' "$(write_runtime_env_value "$DEFAULT_TELEMETRY_RECOVERY_DISCONNECT_SECONDS")"
    printf 'TELEMETRY_RECOVERY_WAKE_VEHICLE=%s\n' "$(write_runtime_env_value "$DEFAULT_TELEMETRY_RECOVERY_WAKE_VEHICLE")"
    printf 'TELEMETRY_RECOVERY_CHECK_INTERVAL=%s\n' "$(write_runtime_env_value "$DEFAULT_TELEMETRY_RECOVERY_CHECK_INTERVAL")"
    printf 'TELEMETRY_RECOVERY_MAX_ATTEMPTS=%s\n' "$(write_runtime_env_value "$DEFAULT_TELEMETRY_RECOVERY_MAX_ATTEMPTS")"
    printf 'TELEMETRY_CONNECTION_STATE_FILE=%s\n' "$(write_runtime_env_value "$DEFAULT_TELEMETRY_CONNECTION_STATE_FILE")"
} > /run/tesla_fleet_gateway.env
chmod 600 /run/tesla_fleet_gateway.env
