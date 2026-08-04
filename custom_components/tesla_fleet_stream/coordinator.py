"""MQTT runtime for Tesla Fleet Stream."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.mqtt.subscription import (
    async_prepare_subscribe_topics,
    async_subscribe_topics,
    async_unsubscribe_topics,
)
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from homeassistant.util.dt import parse_datetime

from .const import (
    CHARGE_STATE_RAW_FIELDS,
    CHARGING_POWER_RAW_FIELDS,
    COMBINED_CHARGER_POWER_KEY,
    CONF_ATTACH_TO_EXISTING_DEVICE,
    CONF_DEVICE_DOMAIN,
    CONF_ENABLED_PLATFORMS,
    CONF_FLEET_API_BASE,
    CONF_TOPIC_BASE,
    CONNECTIVITY_DISCONNECT_DEBOUNCE_SECONDS,
    DEFAULT_ATTACH_TO_EXISTING_DEVICE,
    DEFAULT_DEVICE_DOMAIN,
    DEFAULT_ENABLED_PLATFORMS,
    DEFAULT_FLEET_API_BASE,
    DEFAULT_TOPIC_BASE,
    DOOR_FIELD,
    DOOR_SENSORS,
    IGNORED_TELEMETRY_FIELDS,
    vehicle_connectivity_signal,
    new_entity_signal,
    update_signal,
)
from .fleet_api import async_fetch_vehicle_vins
from .descriptions import (
    BINARY_SENSOR_DESCRIPTIONS,
    DOOR_BINARY_SENSOR_DESCRIPTIONS,
    LOCATION_FIELD,
    LOCATION_KEY,
    SENSOR_DESCRIPTIONS,
)
from .models import EntityTimestamps, VehicleTelemetryState
from .parsers import (
    decode_payload,
    extract_bool,
    extract_charge_state,
    extract_connectivity,
    extract_doors,
    extract_location,
    extract_numeric_scalar,
    extract_sample_time,
    extract_scalar,
    normalize_charge_state,
)

_LOGGER = logging.getLogger(__name__)


class TeslaFleetStreamRuntime:
    """Runtime state and MQTT subscriptions for Tesla Fleet Stream."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        config = {**entry.data, **entry.options}

        self.topic_base: str = config.get(CONF_TOPIC_BASE, DEFAULT_TOPIC_BASE).strip("/")
        self.attach_to_existing_device: bool = config.get(
            CONF_ATTACH_TO_EXISTING_DEVICE, DEFAULT_ATTACH_TO_EXISTING_DEVICE
        )
        self.device_domain: str = config.get(CONF_DEVICE_DOMAIN, DEFAULT_DEVICE_DOMAIN)
        self.enabled_platforms: set[str] = set(
            config.get(CONF_ENABLED_PLATFORMS, DEFAULT_ENABLED_PLATFORMS)
        )

        self._sub_state = None
        self._vehicles: dict[str, VehicleTelemetryState] = {}
        self._known_entities: dict[str, set[tuple[str, str]]] = {
            "sensor": set(),
            "binary_sensor": set(),
            "device_tracker": set(),
        }
        self._message_counts = {"metrics": 0, "connectivity": 0}
        self._logged_vins: set[str] = set()
        self._connectivity_disconnect_unsubs: dict[str, Callable[[], None]] = {}
        # Set by async_setup_entry; used to ignore token-only config updates.
        self.reload_signature: tuple[tuple[str, Any], ...] | None = None

    async def async_start(self) -> None:
        """Start MQTT subscriptions."""
        topic_map = {
            "metrics": {
                "topic": f"{self.topic_base}/+/v/+",
                "msg_callback": self._handle_metric_message,
                "qos": 1,
            },
            "connectivity": {
                "topic": f"{self.topic_base}/+/connectivity",
                "msg_callback": self._handle_connectivity_message,
                "qos": 1,
            },
        }
        self._sub_state = async_prepare_subscribe_topics(
            self.hass,
            self._sub_state,
            topic_map,
        )
        await async_subscribe_topics(self.hass, self._sub_state)
        _LOGGER.info(
            "Subscribed to MQTT telemetry on %s/+/v/+ and %s/+/connectivity",
            self.topic_base,
            self.topic_base,
        )

    async def async_discover_vehicles(self) -> None:
        """Discover account vehicles and pre-register telemetry entities."""
        vins: list[str] = []
        try:
            vins = await async_fetch_vehicle_vins(self.hass, self.entry)
        except ConfigEntryAuthFailed:
            # Surface auth failures so Home Assistant can prompt for reauth.
            raise
        except Exception:
            _LOGGER.exception("Tesla vehicle discovery failed")

        if not vins:
            vins = self._vins_from_registry()
            if vins:
                _LOGGER.warning(
                    "Fleet API returned no vehicles; re-registering %d VIN(s) "
                    "from the Home Assistant device/entity registry",
                    len(vins),
                )

        if not vins:
            _LOGGER.error(
                "No Tesla vehicles discovered; telemetry entities will not be "
                "registered until discovery succeeds (reload the integration "
                "after fixing OAuth or network access)"
            )
            return

        self.register_vins(vins)

    def _vins_from_registry(self) -> list[str]:
        """Return VINs previously associated with this config entry."""
        vins: set[str] = set()

        device_registry = dr.async_get(self.hass)
        for device in device_registry.devices.values():
            if self.entry.entry_id not in device.config_entries:
                continue
            for domain, identifier in device.identifiers:
                if domain in (self.device_domain, self.entry.domain):
                    vins.add(identifier)

        if vins:
            return sorted(vins)

        entity_registry = er.async_get(self.hass)
        vin_prefix = re.compile(r"^([a-z0-9]{17})_", re.IGNORECASE)
        for entity in entity_registry.entities.values():
            if entity.config_entry_id != self.entry.entry_id:
                continue
            unique_id = entity.unique_id
            if not unique_id:
                continue
            match = vin_prefix.match(unique_id)
            if match:
                vins.add(match.group(1).upper())

        return sorted(vins)

    @callback
    def register_vins(self, vins: Iterable[str]) -> None:
        """Pre-register entities for known VINs before telemetry arrives."""
        for raw_vin in vins:
            vin = raw_vin.upper()
            if "sensor" in self.enabled_platforms:
                for description in SENSOR_DESCRIPTIONS.values():
                    self._ensure_entity("sensor", vin, description.key)
                self._ensure_entity("sensor", vin, COMBINED_CHARGER_POWER_KEY)

            if "binary_sensor" in self.enabled_platforms:
                for description in BINARY_SENSOR_DESCRIPTIONS.values():
                    self._ensure_entity("binary_sensor", vin, description.key)
                for description in DOOR_BINARY_SENSOR_DESCRIPTIONS.values():
                    self._ensure_entity("binary_sensor", vin, description.key)

            if "device_tracker" in self.enabled_platforms:
                self._ensure_entity("device_tracker", vin, LOCATION_KEY)

    async def async_stop(self) -> None:
        """Stop MQTT subscriptions."""
        for vin in list(self._connectivity_disconnect_unsubs):
            self._cancel_connectivity_disconnect(vin)
        self._sub_state = async_unsubscribe_topics(self.hass, self._sub_state)

    def iter_known_entities(self, platform: str) -> Iterable[tuple[str, str]]:
        """Return already-discovered entity keys for a platform."""
        return self._known_entities[platform]

    def get_entity_timestamps(self, vin: str, key: str) -> EntityTimestamps | None:
        """Return telemetry timestamps for an entity key."""
        return self._vehicles.get(vin, VehicleTelemetryState()).timestamps.get(key)

    def get_sensor_value(self, vin: str, key: str) -> Any | None:
        """Return a sensor value."""
        return self._vehicles.get(vin, VehicleTelemetryState()).sensors.get(key)

    def get_binary_sensor_value(self, vin: str, key: str) -> bool | None:
        """Return a binary sensor value."""
        return self._vehicles.get(vin, VehicleTelemetryState()).binary_sensors.get(key)

    def get_location(self, vin: str) -> dict[str, Any] | None:
        """Return the latest location."""
        return self._vehicles.get(vin, VehicleTelemetryState()).location

    def get_vehicle_connectivity(self, vin: str) -> bool | None:
        """Return the latest vehicle stream connectivity, if known."""
        vehicle = self._vehicles.get(vin)
        if vehicle is None:
            return None
        return vehicle.connectivity

    def entity_has_stored_value(self, platform: str, vin: str, key: str) -> bool:
        """Return whether an entity already has a cached telemetry value."""
        vehicle = self._vehicles.get(vin)
        if vehicle is None:
            return False

        if platform == "sensor":
            return vehicle.sensors.get(key) is not None
        if platform == "binary_sensor":
            return key in vehicle.binary_sensors
        if platform == "device_tracker":
            return vehicle.location is not None
        return False

    @callback
    def restore_entity_timestamps(
        self, vin: str, key: str, attributes: dict[str, Any]
    ) -> None:
        """Restore telemetry timestamps from saved entity attributes."""
        last_updated = _parse_timestamp_attribute(attributes.get("last_updated"))
        last_changed = _parse_timestamp_attribute(attributes.get("last_changed"))
        if last_updated is None or last_changed is None:
            return

        vehicle = self._vehicles.setdefault(vin, VehicleTelemetryState())
        vehicle.timestamps[key] = EntityTimestamps(
            last_updated=last_updated,
            last_changed=last_changed,
        )

    @callback
    def restore_sensor_value(self, vin: str, key: str, value: Any) -> None:
        """Restore a sensor value from Home Assistant state."""
        self._vehicles.setdefault(vin, VehicleTelemetryState()).sensors[key] = value

    @callback
    def restore_binary_sensor_value(
        self, vin: str, key: str, value: bool | None
    ) -> None:
        """Restore a binary sensor value from Home Assistant state."""
        vehicle = self._vehicles.setdefault(vin, VehicleTelemetryState())
        vehicle.binary_sensors[key] = value
        if key == "connectivity":
            vehicle.connectivity = value

    @callback
    def restore_location(self, vin: str, location: dict[str, Any]) -> None:
        """Restore a device tracker location from Home Assistant state."""
        self._vehicles.setdefault(vin, VehicleTelemetryState()).location = location

    def get_device_info(self, vin: str) -> DeviceInfo:
        """Return DeviceInfo for a VIN."""
        # NOTE: Returning another integration's identifiers in device_info is
        # deprecated in HA 2026.8 (single config-entry-owned devices). Keep
        # this for compatibility now; migrate to linking entities via
        # self.device_entry and a config-entry migration in a future release.
        if self.attach_to_existing_device:
            return DeviceInfo(identifiers={(self.device_domain, vin)})

        return DeviceInfo(
            identifiers={(self.entry.domain, vin)},
            manufacturer="Tesla",
            model="Vehicle",
            serial_number=vin,
            default_name=vin,
        )

    @callback
    def _handle_metric_message(self, msg: ReceiveMessage) -> None:
        """Handle a telemetry metric MQTT message."""
        tail = self._topic_tail(msg.topic)
        if len(tail) != 3 or tail[1] != "v":
            return

        vin, _, raw_field = tail
        vin = vin.upper()
        payload = decode_payload(msg.payload)
        vehicle = self._vehicles.setdefault(vin, VehicleTelemetryState())
        sample_time = extract_sample_time(payload)

        if raw_field in IGNORED_TELEMETRY_FIELDS:
            return

        if raw_field in SENSOR_DESCRIPTIONS:
            description = SENSOR_DESCRIPTIONS[raw_field]
            if raw_field in CHARGE_STATE_RAW_FIELDS:
                value = normalize_charge_state(extract_charge_state(payload))
                # Invalid/null charge enums arrive during stream reconnects; keep
                # the last known state so availability does not flicker.
                if value is None and vehicle.sensors.get(description.key) is not None:
                    return
            elif description.state_class == SensorStateClass.MEASUREMENT:
                value = extract_numeric_scalar(payload)
                if value is None:
                    prior = vehicle.sensors.get(description.key)
                    if isinstance(prior, (int, float)):
                        return
            else:
                value = extract_scalar(payload)
            previous = vehicle.sensors.get(description.key)
            vehicle.sensors[description.key] = value
            self._record_entity_update(
                vehicle,
                description.key,
                value,
                previous,
                sample_time,
            )
            self._log_metric_traffic(vin, raw_field, value)
            self._ensure_entity("sensor", vin, description.key)
            async_dispatcher_send(
                self.hass, update_signal("sensor", vin, description.key)
            )
            if raw_field in CHARGING_POWER_RAW_FIELDS:
                self._update_combined_charger_power(vin)
            return

        if raw_field == DOOR_FIELD:
            doors = extract_doors(payload)
            if doors is None:
                return
            for proto_name, door_key in DOOR_SENSORS.items():
                if proto_name not in doors:
                    continue
                previous = vehicle.binary_sensors.get(door_key)
                vehicle.binary_sensors[door_key] = doors[proto_name]
                self._record_entity_update(
                    vehicle,
                    door_key,
                    doors[proto_name],
                    previous,
                    sample_time,
                )
                self._ensure_entity("binary_sensor", vin, door_key)
                async_dispatcher_send(
                    self.hass, update_signal("binary_sensor", vin, door_key)
                )
            self._log_metric_traffic(vin, raw_field, doors)
            return

        if raw_field in BINARY_SENSOR_DESCRIPTIONS:
            description = BINARY_SENSOR_DESCRIPTIONS[raw_field]
            value = extract_bool(payload)
            previous = vehicle.binary_sensors.get(description.key)
            if value is not None or description.key not in vehicle.binary_sensors:
                vehicle.binary_sensors[description.key] = value
                self._record_entity_update(
                    vehicle,
                    description.key,
                    value,
                    previous,
                    sample_time,
                )
            self._log_metric_traffic(vin, raw_field, value)
            self._ensure_entity("binary_sensor", vin, description.key)
            async_dispatcher_send(
                self.hass,
                update_signal("binary_sensor", vin, description.key),
            )
            return

        if raw_field == LOCATION_FIELD:
            location = extract_location(payload)
            previous = vehicle.location
            vehicle.location = location
            self._record_entity_update(
                vehicle,
                LOCATION_KEY,
                location,
                previous,
                sample_time,
            )
            self._log_metric_traffic(vin, raw_field, location)
            self._ensure_entity("device_tracker", vin, LOCATION_KEY)
            async_dispatcher_send(
                self.hass,
                update_signal("device_tracker", vin, LOCATION_KEY),
            )

    @callback
    def _handle_connectivity_message(self, msg: ReceiveMessage) -> None:
        """Handle a connectivity MQTT message."""
        tail = self._topic_tail(msg.topic)
        if len(tail) != 2 or tail[1] != "connectivity":
            return

        vin = tail[0].upper()
        payload = decode_payload(msg.payload)
        value = extract_connectivity(payload)
        sample_time = extract_sample_time(payload)
        vehicle = self._vehicles.setdefault(vin, VehicleTelemetryState())

        # CONNECTED applies immediately; DISCONNECTED is debounced so brief
        # fleet-telemetry reconnect churn does not mark entities unavailable.
        if value is True:
            self._cancel_connectivity_disconnect(vin)
            self._apply_connectivity(vin, True, sample_time)
            return

        if value is False:
            if vehicle.connectivity is False:
                self._apply_connectivity(vin, False, sample_time)
                return
            self._schedule_connectivity_disconnect(vin, sample_time)
            return

        self._cancel_connectivity_disconnect(vin)
        self._apply_connectivity(vin, value, sample_time)

    def _cancel_connectivity_disconnect(self, vin: str) -> None:
        """Cancel a pending deferred disconnect for a VIN."""
        unsub = self._connectivity_disconnect_unsubs.pop(vin, None)
        if unsub is not None:
            unsub()

    def _schedule_connectivity_disconnect(
        self, vin: str, sample_time: datetime | None
    ) -> None:
        """Defer marking a vehicle disconnected to absorb brief stream blips."""
        self._cancel_connectivity_disconnect(vin)

        @callback
        def _apply_deferred(_now: datetime) -> None:
            self._connectivity_disconnect_unsubs.pop(vin, None)
            self._apply_connectivity(vin, False, sample_time)

        self._connectivity_disconnect_unsubs[vin] = async_call_later(
            self.hass,
            CONNECTIVITY_DISCONNECT_DEBOUNCE_SECONDS,
            _apply_deferred,
        )
        _LOGGER.debug(
            "Debouncing disconnect for %s by %.1fs",
            vin,
            CONNECTIVITY_DISCONNECT_DEBOUNCE_SECONDS,
        )

    def _apply_connectivity(
        self, vin: str, value: bool | None, sample_time: datetime | None
    ) -> None:
        """Apply connectivity state and refresh dependent entity availability."""
        vehicle = self._vehicles.setdefault(vin, VehicleTelemetryState())
        previous = vehicle.connectivity
        vehicle.connectivity = value
        vehicle.binary_sensors["connectivity"] = value
        self._record_entity_update(
            vehicle,
            "connectivity",
            value,
            previous,
            sample_time,
        )
        self._log_connectivity_traffic(vin, value)

        self._ensure_entity("binary_sensor", vin, "connectivity")
        async_dispatcher_send(
            self.hass,
            update_signal("binary_sensor", vin, "connectivity"),
        )
        if value != previous:
            async_dispatcher_send(
                self.hass,
                vehicle_connectivity_signal(vin),
            )

    def _log_metric_traffic(self, vin: str, raw_field: str, value: Any) -> None:
        """Log incoming MQTT metric traffic without flooding the log."""
        self._message_counts["metrics"] += 1
        if vin not in self._logged_vins:
            self._logged_vins.add(vin)
            _LOGGER.info(
                "Received first telemetry MQTT message for %s (%s)",
                vin,
                raw_field,
            )
        _LOGGER.debug("MQTT metric %s/%s: %s", vin, raw_field, value)

    def _log_connectivity_traffic(self, vin: str, value: bool | None) -> None:
        """Log vehicle connectivity MQTT events."""
        self._message_counts["connectivity"] += 1
        _LOGGER.info(
            "MQTT connectivity %s: %s (metrics received: %s)",
            vin,
            value,
            self._message_counts["metrics"],
        )

    @callback
    def recompute_combined_charger_power(self, vin: str) -> None:
        """Recompute combined charger power after restoring AC/DC values."""
        self._update_combined_charger_power(vin)

    @callback
    def _update_combined_charger_power(self, vin: str) -> None:
        """Publish the active AC or DC charging power as a single sensor."""
        vehicle = self._vehicles.get(vin)
        if vehicle is None:
            return

        combined = _combine_charging_power(
            vehicle.sensors.get("ac_charging_power"),
            vehicle.sensors.get("dc_charging_power"),
        )
        previous = vehicle.sensors.get(COMBINED_CHARGER_POWER_KEY)
        vehicle.sensors[COMBINED_CHARGER_POWER_KEY] = combined
        self._record_entity_update(
            vehicle,
            COMBINED_CHARGER_POWER_KEY,
            combined,
            previous,
            None,
        )
        self._ensure_entity("sensor", vin, COMBINED_CHARGER_POWER_KEY)
        async_dispatcher_send(
            self.hass,
            update_signal("sensor", vin, COMBINED_CHARGER_POWER_KEY),
        )

    def _ensure_entity(self, platform: str, vin: str, key: str) -> None:
        """Ensure an entity exists for the given platform and key."""
        entity_key = (vin, key)
        if entity_key in self._known_entities[platform]:
            return

        self._known_entities[platform].add(entity_key)
        async_dispatcher_send(self.hass, new_entity_signal(platform), vin, key)

    def _topic_tail(self, topic: str) -> list[str]:
        """Return the topic parts after the configured topic base."""
        base_parts = self.topic_base.split("/")
        topic_parts = topic.split("/")
        if topic_parts[: len(base_parts)] != base_parts:
            return []
        return topic_parts[len(base_parts) :]

    @staticmethod
    def _record_entity_update(
        vehicle: VehicleTelemetryState,
        key: str,
        new_value: Any,
        previous_value: Any,
        sample_time: datetime | None,
    ) -> None:
        """Record when telemetry was received and when the value last changed."""
        now = sample_time or dt_util.utcnow()
        timestamps = vehicle.timestamps.get(key)
        changed = not _values_equal(previous_value, new_value)

        if timestamps is None or changed:
            vehicle.timestamps[key] = EntityTimestamps(
                last_updated=now,
                last_changed=now,
            )
            return

        vehicle.timestamps[key] = EntityTimestamps(
            last_updated=now,
            last_changed=timestamps.last_changed,
        )


def _values_equal(previous: Any, new: Any) -> bool:
    """Return whether two telemetry values should be treated as unchanged."""
    return previous == new


def _parse_timestamp_attribute(value: Any) -> datetime | None:
    """Parse a timestamp stored in Home Assistant entity attributes."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return parse_datetime(value)
    return None


def _combine_charging_power(ac: Any, dc: Any) -> float | None:
    """Return active charging power in kW (AC and DC are mutually exclusive)."""
    ac_kw = ac if isinstance(ac, (int, float)) else None
    dc_kw = dc if isinstance(dc, (int, float)) else None
    if ac_kw is not None and ac_kw > 0:
        return float(ac_kw)
    if dc_kw is not None and dc_kw > 0:
        return float(dc_kw)
    if ac_kw is not None or dc_kw is not None:
        return float(max(ac_kw or 0, dc_kw or 0))
    return None
