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
CONF_REGION = "region"
CONF_TOPIC_BASE = "topic_base"

DEFAULT_ATTACH_TO_EXISTING_DEVICE = True
DEFAULT_DEVICE_DOMAIN = "tesla_fleet"
DEFAULT_ENABLED_PLATFORMS = ["sensor", "binary_sensor", "device_tracker"]
DEFAULT_TOPIC_BASE = "tesla/telemetry"

# Sole Fleet API region setting (integration). The gateway add-on reads the same
# value from gateway_handoff.json and must not offer a separate region option.
FLEET_API_REGIONS = ("eu", "na", "cn")
FLEET_API_BASE_BY_REGION = {
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",
}
ALLOWED_FLEET_API_HOSTS = frozenset(
    host.removeprefix("https://") for host in FLEET_API_BASE_BY_REGION.values()
)
# Backward-compat alias for older call sites / docs snippets.
DEFAULT_FLEET_API_BASE = FLEET_API_BASE_BY_REGION["na"]

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

# Pack electricals → derived live power / Wh/km. LifetimeEnergyUsedDrive is
# Semi-only and intentionally unsupported.
CONSUMPTION_INPUT_RAW_FIELDS = frozenset(
    {"PackVoltage", "PackCurrent", "VehicleSpeed", "Odometer", "EnergyRemaining", "LifetimeEnergyUsed"}
)
DERIVED_PACK_POWER_KEY = "power"
DERIVED_CONSUMPTION_KEY = "consumption"
DERIVED_CONSUMPTION_AVERAGE_KEY = "consumption_average"
# Recomputed from other telemetry — do not restore stale HA state over inputs.
DERIVED_SENSOR_KEYS = frozenset(
    {
        DERIVED_PACK_POWER_KEY,
        DERIVED_CONSUMPTION_KEY,
        DERIVED_CONSUMPTION_AVERAGE_KEY,
        COMBINED_CHARGER_POWER_KEY,
    }
)
# VehicleSpeed is stored in native mph; ignore crawl/noise below this.
CONSUMPTION_MIN_SPEED_MPH = 3.0
MPH_TO_KMH = 1.609344
# Minimum drive-session deltas before publishing an average (reduces startup noise).
CONSUMPTION_AVERAGE_MIN_DISTANCE_MILES = 0.2
CONSUMPTION_AVERAGE_MIN_ENERGY_KWH = 0.05

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


def normalize_region(region: str) -> str:
    """Validate and normalize a Fleet API region code."""
    cleaned = region.strip().lower()
    if cleaned not in FLEET_API_BASE_BY_REGION:
        raise ValueError("Fleet API region must be eu, na, or cn")
    return cleaned


def fleet_api_base_for_region(region: str) -> str:
    """Return the official Fleet API base URL for a region."""
    return FLEET_API_BASE_BY_REGION[normalize_region(region)]


def region_for_fleet_api_base(fleet_api_base: str) -> str:
    """Return the region code for an official Fleet API base URL."""
    normalized = normalize_fleet_api_base(fleet_api_base)
    for region, base in FLEET_API_BASE_BY_REGION.items():
        if base == normalized:
            return region
    raise ValueError("Fleet API base must be the official NA, EU, or CN Tesla host")


def resolve_entry_region(
    data: dict | None = None,
    options: dict | None = None,
) -> str | None:
    """Resolve region from entry data/options without inventing a default.

    Prefer explicit ``region``. Fall back to deriving it from a stored
    ``fleet_api_base``. Return None when neither is usable so callers cannot
    silently pick the wrong continent.
    """
    merged = {**(data or {}), **(options or {})}
    raw_region = merged.get(CONF_REGION)
    if isinstance(raw_region, str) and raw_region.strip():
        try:
            return normalize_region(raw_region)
        except ValueError:
            pass

    raw_base = merged.get(CONF_FLEET_API_BASE)
    if isinstance(raw_base, str) and raw_base.strip():
        try:
            return region_for_fleet_api_base(raw_base)
        except ValueError:
            pass
    return None

