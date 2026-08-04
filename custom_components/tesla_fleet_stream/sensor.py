"""Sensor platform for Tesla Fleet Stream."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.util.dt import parse_datetime
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    SpeedConverter,
    TemperatureConverter,
)
from homeassistant.util.variance import ignore_variance
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import new_entity_signal
from .coordinator import TeslaFleetStreamRuntime
from .descriptions import SENSOR_DESCRIPTIONS_BY_KEY
from .entity import TeslaFleetStreamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    runtime: TeslaFleetStreamRuntime = entry.runtime_data
    if "sensor" not in runtime.enabled_platforms:
        return

    created: set[tuple[str, str]] = set()

    @callback
    def add_sensor(vin: str, key: str) -> None:
        entity_key = (vin, key)
        if entity_key in created:
            return

        description = SENSOR_DESCRIPTIONS_BY_KEY.get(key)
        if description is not None:
            async_add_entities([TeslaFleetStreamSensor(runtime, vin, description)])
            created.add(entity_key)

    for vin, key in runtime.iter_known_entities("sensor"):
        add_sensor(vin, key)

    entry.async_on_unload(
        async_dispatcher_connect(hass, new_entity_signal("sensor"), add_sensor)
    )


class TeslaFleetStreamSensor(RestoreSensor, TeslaFleetStreamEntity):
    """Telemetry-backed sensor."""

    def __init__(self, runtime: TeslaFleetStreamRuntime, vin: str, description) -> None:
        super().__init__(runtime, vin, description.key, "sensor")
        self.entity_description = description
        if description.device_class == SensorDeviceClass.TIMESTAMP:
            self._get_timestamp = ignore_variance(
                func=lambda value: dt_util.now() + timedelta(hours=value),
                ignored_variance=timedelta(minutes=4),
            )

    async def _async_restore_state(self) -> None:
        """Restore runtime state using native sensor data when available."""
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            if self._restore_from_sensor_data(last_sensor_data.native_value):
                return

        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                self._restore_from_last_state(last_state)

    @callback
    def _restore_from_sensor_data(self, native_value) -> bool:
        """Restore a sensor value from stored native sensor data."""
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            target = native_value
            if isinstance(target, str):
                target = parse_datetime(target)
            if not isinstance(target, datetime):
                return False
            hours = (target - dt_util.utcnow()).total_seconds() / 3600
            if hours > 0:
                self._runtime.restore_sensor_value(self._vin, self._key, hours)
                return True
            return False

        if self.entity_description.device_class == SensorDeviceClass.ENUM:
            if isinstance(native_value, str):
                self._runtime.restore_sensor_value(self._vin, self._key, native_value)
                return True
            return False

        if isinstance(native_value, (int, float)):
            self._restore_measurement_value(float(native_value))
            return True
        return False

    @callback
    def _restore_from_last_state(self, state) -> None:
        """Restore a sensor value from legacy Home Assistant state."""
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            target = parse_datetime(state.state)
            if target is not None:
                hours = (target - dt_util.utcnow()).total_seconds() / 3600
                if hours > 0:
                    self._runtime.restore_sensor_value(self._vin, self._key, hours)
            return

        if self.entity_description.device_class == SensorDeviceClass.ENUM:
            self._runtime.restore_sensor_value(self._vin, self._key, state.state)
            return

        try:
            value = float(state.state)
        except ValueError:
            return

        display_unit = state.attributes.get("unit_of_measurement")
        native_unit = self.entity_description.native_unit_of_measurement
        if (
            display_unit
            and native_unit
            and display_unit != native_unit
            and self.entity_description.device_class is not None
        ):
            value = self._convert_display_value_to_native(
                value,
                display_unit,
                native_unit,
                self.entity_description.device_class,
            )

        self._restore_measurement_value(value)

    @callback
    def _restore_measurement_value(self, value: float) -> None:
        """Restore a numeric measurement into runtime state."""
        self._runtime.restore_sensor_value(self._vin, self._key, value)
        if self._key in ("ac_charging_power", "dc_charging_power"):
            self._runtime.recompute_combined_charger_power(self._vin)

    @staticmethod
    def _convert_display_value_to_native(
        value: float,
        display_unit: str,
        native_unit: str,
        device_class: SensorDeviceClass,
    ) -> float:
        """Convert a legacy displayed state value back to the native unit."""
        converter_by_class = {
            SensorDeviceClass.DISTANCE: DistanceConverter,
            SensorDeviceClass.SPEED: SpeedConverter,
            SensorDeviceClass.TEMPERATURE: TemperatureConverter,
        }
        converter = converter_by_class.get(device_class)
        if converter is None:
            return value
        if (
            display_unit not in converter.VALID_UNITS
            or native_unit not in converter.VALID_UNITS
        ):
            return value
        return converter.convert(value, display_unit, native_unit)

    @property
    def available(self) -> bool:
        """Return entity availability."""
        if self.entity_description.device_class != SensorDeviceClass.TIMESTAMP:
            return super().available

        value = self._runtime.get_sensor_value(self._vin, self._key)
        return isinstance(value, (int, float)) and value > 0

    @property
    def native_value(self):
        """Return the sensor value."""
        value = self._runtime.get_sensor_value(self._vin, self._key)
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            if not isinstance(value, (int, float)) or value <= 0:
                return None
            return self._get_timestamp(value)
        return value
