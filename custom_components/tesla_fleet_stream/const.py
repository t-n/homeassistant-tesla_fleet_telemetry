"""Constants for Tesla Fleet Stream."""

from __future__ import annotations

import re

from homeassistant.const import Platform

DOMAIN = "tesla_fleet_stream"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
]

CONF_ATTACH_TO_EXISTING_DEVICE = "attach_to_existing_device"
CONF_DEVICE_DOMAIN = "device_domain"
CONF_ENABLED_PLATFORMS = "enabled_platforms"
CONF_FLEET_API_BASE = "fleet_api_base"
CONF_TOPIC_BASE = "topic_base"

DEFAULT_ATTACH_TO_EXISTING_DEVICE = False
DEFAULT_DEVICE_DOMAIN = "tesla_fleet"
DEFAULT_ENABLED_PLATFORMS = ["sensor", "binary_sensor", "device_tracker"]
DEFAULT_FLEET_API_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
DEFAULT_TOPIC_BASE = "tesla/telemetry"

ALLOWED_FLEET_API_HOSTS = frozenset(
    {
        "fleet-api.prd.na.vn.cloud.tesla.com",
        "fleet-api.prd.eu.vn.cloud.tesla.com",
        "fleet-api.prd.cn.vn.cloud.tesla.cn",
    }
)

# ISO-3779 VIN charset (no I/O/Q).
VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

# Ignore brief fleet-telemetry CONNECTED/DISCONNECTED churn before flipping HA
# availability. CONNECTED still applies immediately.
CONNECTIVITY_DISCONNECT_DEBOUNCE_SECONDS = 3.0

CHARGE_STATES = {
    "Starting": "starting",
    "Charging": "charging",
    "Stopped": "stopped",
    "Complete": "complete",
    "Disconnected": "disconnected",
    "NoPower": "no_power",
}

CHARGE_STATE_ENUM_OPTIONS = list(CHARGE_STATES.values())

# ChargeState may still arrive via MQTT but is not exposed as a HA entity.
CHARGE_STATE_RAW_FIELDS = frozenset({"DetailedChargeState"})
CHARGING_POWER_RAW_FIELDS = frozenset({"ACChargingPower", "DCChargingPower"})
IGNORED_TELEMETRY_FIELDS = frozenset({"ChargeState"})
COMBINED_CHARGER_POWER_KEY = "charger_power"

# DoorState is a single Tesla telemetry field whose value is a composite Doors
# message (6 booleans). It is fanned out into one binary sensor per door. Maps
# the proto Doors field name to the entity key/translation key. Cabin door keys
# match the official tesla_fleet integration (vehicle_state_df/dr/pf/pr).
DOOR_FIELD = "DoorState"
DOOR_SENSORS = {
    "DriverFront": "vehicle_state_df",
    "DriverRear": "vehicle_state_dr",
    "PassengerFront": "vehicle_state_pf",
    "PassengerRear": "vehicle_state_pr",
    "TrunkFront": "vehicle_state_ft",
    "TrunkRear": "vehicle_state_rt",
}

AUTHORIZE_URL = "https://auth.tesla.com/oauth2/v3/authorize"
TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"
SCOPES = [
    "openid",
    "offline_access",
    "vehicle_device_data",
    "vehicle_location",
]
GATEWAY_HANDOFF_RELATIVE_PATH = "tesla_fleet_stream/gateway_handoff.json"
OAUTH_TOKEN_EXPORT_RELATIVE_PATH = "tesla_fleet_stream/oauth_tokens.json"
GATEWAY_HANDOFF_REEXPORT_INTERVAL_SECONDS = 30 * 60


def vehicle_connectivity_signal(vin: str) -> str:
    """Return a dispatcher signal when vehicle connectivity changes."""
    return f"{DOMAIN}_{vin.lower()}_connectivity_update"


def new_entity_signal(platform: str) -> str:
    """Return a dispatcher signal for new entities."""
    return f"{DOMAIN}_new_{platform}"


def update_signal(platform: str, vin: str, key: str) -> str:
    """Return a dispatcher signal for entity state updates."""
    return f"{DOMAIN}_{platform}_{vin}_{key}_update"


def is_valid_vin(vin: str) -> bool:
    """Return True when vin looks like an ISO-3779 VIN."""
    return bool(VIN_PATTERN.fullmatch(vin.upper()))


def normalize_topic_base(topic_base: str) -> str:
    """Normalize and validate an MQTT topic base."""
    cleaned = topic_base.strip().strip("/")
    if not cleaned:
        raise ValueError("MQTT topic base cannot be empty")
    if "+" in cleaned or "#" in cleaned:
        raise ValueError("MQTT topic base cannot contain wildcards (+ or #)")
    return cleaned


def normalize_fleet_api_base(fleet_api_base: str) -> str:
    """Validate and normalize a Tesla Fleet API base URL."""
    from urllib.parse import urlparse

    parsed = urlparse(fleet_api_base.rstrip("/"))
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_FLEET_API_HOSTS:
        raise ValueError(
            "Fleet API base must be the official NA, EU, or CN Tesla host"
        )
    if parsed.path not in ("", "/"):
        raise ValueError("Fleet API base must not include a path")
    return f"https://{parsed.hostname}"

