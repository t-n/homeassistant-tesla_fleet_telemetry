"""Binary sensor platform for Tesla Fleet Stream."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import new_entity_signal
from .coordinator import TeslaFleetStreamRuntime
from .descriptions import BINARY_SENSOR_DESCRIPTIONS, DOOR_BINARY_SENSOR_DESCRIPTIONS
from .entity import TeslaFleetStreamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    runtime: TeslaFleetStreamRuntime = entry.runtime_data
    if "binary_sensor" not in runtime.enabled_platforms:
        return

    created: set[tuple[str, str]] = set()
    descriptions_by_key = {
        description.key: description
        for description in (
            *BINARY_SENSOR_DESCRIPTIONS.values(),
            *DOOR_BINARY_SENSOR_DESCRIPTIONS.values(),
        )
    }

    @callback
    def add_binary_sensor(vin: str, key: str) -> None:
        entity_key = (vin, key)
        if entity_key in created:
            return

        description = descriptions_by_key.get(key)
        if description is not None:
            async_add_entities(
                [TeslaFleetStreamBinarySensor(runtime, vin, description)]
            )
            created.add(entity_key)

    for vin, key in runtime.iter_known_entities("binary_sensor"):
        add_binary_sensor(vin, key)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, new_entity_signal("binary_sensor"), add_binary_sensor
        )
    )


class TeslaFleetStreamBinarySensor(TeslaFleetStreamEntity, BinarySensorEntity):
    """Telemetry-backed binary sensor."""

    def __init__(self, runtime: TeslaFleetStreamRuntime, vin: str, description) -> None:
        super().__init__(runtime, vin, description.key, "binary_sensor")
        self.entity_description = description

    @callback
    def _restore_from_last_state(self, state) -> None:
        """Restore a binary sensor value from Home Assistant state."""
        if state.state == STATE_ON:
            value = True
        elif state.state == STATE_OFF:
            value = False
        elif state.state in {"occupied", "present", "on"}:
            value = True
        elif state.state in {"clear", "not_occupied", "unoccupied", "off", "away"}:
            value = False
        else:
            return
        self._runtime.restore_binary_sensor_value(self._vin, self._key, value)

    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor state."""
        return self._runtime.get_binary_sensor_value(self._vin, self._key)

