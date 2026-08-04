"""Payload parsing helpers for Tesla Fleet Stream."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util
from homeassistant.util.dt import parse_datetime

from .const import CHARGE_STATES, CHARGE_STATE_ENUM_OPTIONS

INVALID_SENTINEL_KEYS = ("invalid", "Invalid")

SCALAR_PAYLOAD_KEYS = (
    "value",
    "Value",
    "boolean_value",
    "BooleanValue",
    "booleanValue",
    "signal",
    "Signal",
    "state",
    "State",
)

NUMERIC_PAYLOAD_KEYS = (
    "value",
    "Value",
    "float_value",
    "FloatValue",
    "floatValue",
    "double_value",
    "DoubleValue",
    "doubleValue",
    "int_value",
    "IntValue",
    "intValue",
    "long_value",
    "LongValue",
    "longValue",
)

PRESENCE_TRUE_STRINGS = frozenset(
    {
        "true",
        "on",
        "online",
        "connected",
        "1",
        "yes",
        "occupied",
        "present",
        "detected",
        "latched",
        "locked",
    }
)
PRESENCE_FALSE_STRINGS = frozenset(
    {
        "false",
        "off",
        "offline",
        "disconnected",
        "0",
        "no",
        "unoccupied",
        "notoccupied",
        "not_occupied",
        "absent",
        "clear",
        "empty",
        "unlatched",
        "unlocked",
    }
)

CHARGE_STATE_PAYLOAD_KEYS = (
    "detailed_charge_state_value",
    "DetailedChargeStateValue",
    "charging_value",
    "ChargingValue",
    "value",
    "Value",
    "state",
    "State",
    "signal",
    "Signal",
)

CHARGE_STATE_ENUM_BY_NUMBER = {
    1: "disconnected",
    2: "no_power",
    3: "starting",
    4: "charging",
    5: "complete",
    6: "stopped",
}


TIMESTAMP_PAYLOAD_KEYS = (
    "CreatedAt",
    "created_at",
    "createdAt",
    "timestamp",
    "Timestamp",
    "receivedat",
    "ReceivedAt",
)


def extract_sample_time(payload: Any) -> datetime | None:
    """Extract a vehicle or gateway sample timestamp from a telemetry payload."""
    if not isinstance(payload, dict):
        return None

    for key in TIMESTAMP_PAYLOAD_KEYS:
        if key not in payload:
            continue
        parsed = _parse_timestamp_value(payload[key])
        if parsed is not None:
            return parsed
    return None


def _parse_timestamp_value(value: Any) -> datetime | None:
    """Parse a timestamp from common fleet-telemetry encodings."""
    if isinstance(value, str):
        return parse_datetime(value)

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp <= 0:
            return None
        if timestamp > 1e12:
            timestamp /= 1000
        return dt_util.utc_from_timestamp(timestamp)

    return None


def decode_payload(payload: bytes | str) -> Any:
    """Decode an MQTT payload, falling back to a raw string."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload

    # Fleet Telemetry metric values are JSON-encoded; some bridges double-encode.
    if isinstance(data, str):
        stripped = data.strip()
        if stripped and stripped[0] in {'"', "{", "[", "t", "f", "n"}:
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
    return data


def extract_charge_state(payload: Any) -> Any | None:
    """Extract a charge state value from a Tesla telemetry payload."""
    if isinstance(payload, dict):
        if any(payload.get(key) is True for key in INVALID_SENTINEL_KEYS):
            return None

        for key in CHARGE_STATE_PAYLOAD_KEYS:
            value = payload.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value

        return None

    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload

    return None


def normalize_charge_state(value: Any) -> str | None:
    """Normalize Tesla charge state values to tesla_fleet enum states."""
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return CHARGE_STATE_ENUM_BY_NUMBER.get(int(value))

    if isinstance(value, str):
        stripped = value.strip()
        for prefix in ("DetailedChargeState", "ChargeState"):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :]
                break

        mapped = CHARGE_STATES.get(stripped)
        if mapped is not None:
            return mapped

        lowered = stripped.lower()
        if lowered in CHARGE_STATE_ENUM_OPTIONS:
            return lowered

    return None


def extract_scalar(payload: Any) -> Any | None:
    """Extract a scalar value from a Tesla telemetry payload."""
    if isinstance(payload, dict):
        if any(payload.get(key) is True for key in INVALID_SENTINEL_KEYS):
            return None

        for key in SCALAR_PAYLOAD_KEYS:
            value = payload.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            if isinstance(value, dict):
                nested = extract_scalar(value)
                if nested is not None:
                    return nested

        return None

    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload

    return None


def extract_numeric_scalar(payload: Any) -> float | None:
    """Extract a numeric telemetry value, ignoring non-numeric state strings."""
    if isinstance(payload, bool):
        return None
    if isinstance(payload, (int, float)):
        return float(payload)
    if isinstance(payload, str):
        try:
            return float(payload.strip())
        except ValueError:
            return None
    if isinstance(payload, dict):
        if any(payload.get(key) is True for key in INVALID_SENTINEL_KEYS):
            return None
        for key in NUMERIC_PAYLOAD_KEYS:
            if key not in payload:
                continue
            coerced = extract_numeric_scalar(payload[key])
            if coerced is not None:
                return coerced
    return None


def extract_bool(payload: Any) -> bool | None:
    """Extract a boolean value from a Tesla telemetry payload."""
    value = extract_scalar(payload)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        for prefix in ("driverseatoccupied", "presence", "occupancy"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
        if normalized in PRESENCE_TRUE_STRINGS:
            return True
        if normalized in PRESENCE_FALSE_STRINGS:
            return False
    return None


def extract_connectivity(payload: Any) -> bool | None:
    """Extract a binary connectivity state from a connectivity payload."""
    if isinstance(payload, dict):
        status = payload.get("Status") or payload.get("status")
        if isinstance(status, str):
            normalized = status.strip().lower()
            if normalized in {"connected", "online", "active", "open"}:
                return True
            if normalized in {"disconnected", "offline", "closed", "inactive"}:
                return False
    return extract_bool(payload)


DOOR_PROTO_FIELDS = (
    "DriverFront",
    "DriverRear",
    "PassengerFront",
    "PassengerRear",
    "TrunkFront",
    "TrunkRear",
)

_DOOR_CONTAINER_KEYS = (
    "door_value",
    "DoorValue",
    "doors",
    "Doors",
    "DoorState",
    "value",
    "Value",
)


def _coerce_door_bool(value: Any) -> bool | None:
    """Coerce a single door value to a boolean (True == open)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "open", "opened", "1", "on"}:
            return True
        if normalized in {"false", "closed", "0", "off"}:
            return False
    return None


def _find_doors_mapping(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Locate the dict that actually holds the per-door booleans."""
    normalized = {str(key).lower().replace("_", ""): key for key in payload}
    if any(name.lower() in normalized for name in DOOR_PROTO_FIELDS):
        return payload

    for key in _DOOR_CONTAINER_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = _find_doors_mapping(nested)
            if found is not None:
                return found
    return None


def extract_doors(payload: Any) -> dict[str, bool] | None:
    """Extract per-door open/closed booleans from a DoorState payload.

    Returns a mapping keyed by proto Doors field name (DriverFront, ...). The
    exact MQTT shape from fleet-telemetry can be a flat object or nested under a
    value/door_value key, so this is tolerant of both and of key casing.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None

    if any(payload.get(key) is True for key in INVALID_SENTINEL_KEYS):
        return None

    source = _find_doors_mapping(payload)
    if source is None:
        return None

    lookup = {str(key).lower().replace("_", ""): value for key, value in source.items()}
    result: dict[str, bool] = {}
    for name in DOOR_PROTO_FIELDS:
        coerced = _coerce_door_bool(lookup.get(name.lower()))
        if coerced is not None:
            result[name] = coerced

    return result or None


def extract_location(payload: Any) -> dict[str, Any] | None:
    """Extract GPS coordinates from a Tesla telemetry payload."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None

    if isinstance(payload, dict):
        if any(payload.get(key) is True for key in INVALID_SENTINEL_KEYS):
            return None

        coords = _extract_location_coords(payload)
        if coords is not None:
            return coords

        for key in (
            "location_value",
            "LocationValue",
            "value",
            "Value",
            "Location",
            "location",
        ):
            nested = payload.get(key)
            if isinstance(nested, dict):
                coords = _extract_location_coords(nested)
                if coords is not None:
                    return coords

    if isinstance(payload, list) and len(payload) == 2:
        try:
            return {
                "latitude": float(payload[0]),
                "longitude": float(payload[1]),
                "gps_accuracy": 0,
            }
        except (TypeError, ValueError):
            return None

    return None


def _extract_location_coords(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract latitude/longitude from a flat coordinate mapping."""
    latitude = _first_present(payload, ("latitude", "Latitude", "lat", "Lat"))
    longitude = _first_present(payload, ("longitude", "Longitude", "lon", "Lng", "Long"))
    accuracy = _first_present(
        payload, ("gps_accuracy", "GpsAccuracy", "accuracy", "Accuracy")
    )

    if latitude is None or longitude is None:
        return None

    try:
        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "gps_accuracy": int(float(accuracy)) if accuracy is not None else 0,
        }
    except (TypeError, ValueError):
        return None


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    """Return the first present value from a dictionary."""
    for key in keys:
        if key in payload:
            return payload[key]
    return None

