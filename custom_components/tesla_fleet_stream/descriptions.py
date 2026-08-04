"""Entity descriptions for Tesla Fleet Stream."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

from .const import CHARGE_STATE_ENUM_OPTIONS, DOOR_FIELD, DOOR_SENSORS


@dataclass(frozen=True, kw_only=True)
class TeslaFleetStreamSensorDescription(SensorEntityDescription):
    """Describes a telemetry-backed sensor."""

    raw_field: str
    key: str


@dataclass(frozen=True, kw_only=True)
class TeslaFleetStreamBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a telemetry-backed binary sensor."""

    raw_field: str
    key: str


SENSOR_DESCRIPTIONS: dict[str, TeslaFleetStreamSensorDescription] = {
    "Soc": TeslaFleetStreamSensorDescription(
        key="soc",
        raw_field="Soc",
        translation_key="charge_state_battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "RatedRange": TeslaFleetStreamSensorDescription(
        key="rated_range",
        raw_field="RatedRange",
        translation_key="charge_state_battery_range",
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "IdealBatteryRange": TeslaFleetStreamSensorDescription(
        key="ideal_battery_range",
        raw_field="IdealBatteryRange",
        translation_key="charge_state_ideal_battery_range",
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "ChargeRateMilePerHour": TeslaFleetStreamSensorDescription(
        key="charge_rate",
        raw_field="ChargeRateMilePerHour",
        translation_key="charge_state_charge_rate",
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "VehicleSpeed": TeslaFleetStreamSensorDescription(
        key="vehicle_speed",
        raw_field="VehicleSpeed",
        translation_key="drive_state_speed",
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "ChargeAmps": TeslaFleetStreamSensorDescription(
        key="charge_amps",
        raw_field="ChargeAmps",
        translation_key="charge_state_charger_actual_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    "InsideTemp": TeslaFleetStreamSensorDescription(
        key="inside_temp",
        raw_field="InsideTemp",
        translation_key="climate_state_inside_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "OutsideTemp": TeslaFleetStreamSensorDescription(
        key="outside_temp",
        raw_field="OutsideTemp",
        translation_key="climate_state_outside_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    # ChargeState remains in gateway telemetry as fallback but is not exposed here
    # to avoid duplicating DetailedChargeState ("Charging (live)").
    "DetailedChargeState": TeslaFleetStreamSensorDescription(
        key="detailed_charge_state",
        raw_field="DetailedChargeState",
        translation_key="charge_state_charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_STATE_ENUM_OPTIONS,
    ),
    "ACChargingPower": TeslaFleetStreamSensorDescription(
        key="ac_charging_power",
        raw_field="ACChargingPower",
        translation_key="ac_charging_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "DCChargingPower": TeslaFleetStreamSensorDescription(
        key="dc_charging_power",
        raw_field="DCChargingPower",
        translation_key="dc_charging_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "TimeToFullCharge": TeslaFleetStreamSensorDescription(
        key="time_to_full_charge",
        raw_field="TimeToFullCharge",
        translation_key="charge_state_minutes_to_full_charge",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}

COMBINED_CHARGER_POWER_DESCRIPTION = TeslaFleetStreamSensorDescription(
    key="charger_power",
    raw_field="",
    translation_key="charge_state_charger_power",
    native_unit_of_measurement=UnitOfPower.KILO_WATT,
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)

SENSOR_DESCRIPTIONS_BY_KEY: dict[str, TeslaFleetStreamSensorDescription] = {
    description.key: description for description in SENSOR_DESCRIPTIONS.values()
}
SENSOR_DESCRIPTIONS_BY_KEY[COMBINED_CHARGER_POWER_DESCRIPTION.key] = (
    COMBINED_CHARGER_POWER_DESCRIPTION
)


BINARY_SENSOR_DESCRIPTIONS: dict[str, TeslaFleetStreamBinarySensorDescription] = {
    "Locked": TeslaFleetStreamBinarySensorDescription(
        key="locked",
        raw_field="Locked",
        translation_key="vehicle_state_locked",
        icon="mdi:lock",
    ),
    "DriverSeatOccupied": TeslaFleetStreamBinarySensorDescription(
        key="driver_seat_occupied",
        raw_field="DriverSeatOccupied",
        translation_key="vehicle_state_driver_seat_occupied",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:car-seat",
    ),
    "connectivity": TeslaFleetStreamBinarySensorDescription(
        key="connectivity",
        raw_field="connectivity",
        translation_key="state",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
}

# Doors arrive as a single composite DoorState field and are fanned out into one
# binary sensor per door. Keyed by entity key (not raw_field) since all six share
# the DoorState raw field; the coordinator special-cases DoorState routing.
DOOR_BINARY_SENSOR_DESCRIPTIONS: dict[str, TeslaFleetStreamBinarySensorDescription] = {
    key: TeslaFleetStreamBinarySensorDescription(
        key=key,
        raw_field=DOOR_FIELD,
        translation_key=key,
        device_class=BinarySensorDeviceClass.DOOR,
    )
    for key in DOOR_SENSORS.values()
}

LOCATION_KEY = "location"
LOCATION_FIELD = "Location"
LOCATION_TRANSLATION_KEY = "location"
