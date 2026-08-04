"""Device tracker platform for Tesla Fleet Stream."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import new_entity_signal
from .coordinator import TeslaFleetStreamRuntime
from .descriptions import LOCATION_KEY, LOCATION_TRANSLATION_KEY
from .entity import TeslaFleetStreamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device trackers."""
    runtime: TeslaFleetStreamRuntime = entry.runtime_data
    if "device_tracker" not in runtime.enabled_platforms:
        return

    created: set[tuple[str, str]] = set()

    @callback
    def add_tracker(vin: str, key: str) -> None:
        entity_key = (vin, key)
        if key != LOCATION_KEY or entity_key in created:
            return

        async_add_entities([TeslaFleetStreamTracker(runtime, vin)])
        created.add(entity_key)

    for vin, key in runtime.iter_known_entities("device_tracker"):
        add_tracker(vin, key)

    entry.async_on_unload(
        async_dispatcher_connect(hass, new_entity_signal("device_tracker"), add_tracker)
    )


class TeslaFleetStreamTracker(TeslaFleetStreamEntity, TrackerEntity):
    """Telemetry-backed GPS tracker."""

    def __init__(self, runtime: TeslaFleetStreamRuntime, vin: str) -> None:
        super().__init__(runtime, vin, LOCATION_KEY, "device_tracker")
        self._attr_translation_key = LOCATION_TRANSLATION_KEY

    @callback
    def _restore_from_last_state(self, state) -> None:
        """Restore a device tracker location from Home Assistant state."""
        attrs = state.attributes
        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")
        if latitude is None or longitude is None:
            return
        self._runtime.restore_location(
            self._vin,
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "gps_accuracy": int(attrs.get("gps_accuracy", 0) or 0),
            },
        )

    @property
    def source_type(self) -> SourceType:
        """Return the tracker source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        location = self._runtime.get_location(self._vin) or {}
        return location.get("latitude")

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        location = self._runtime.get_location(self._vin) or {}
        return location.get("longitude")

    @property
    def location_accuracy(self) -> int:
        """Return GPS accuracy."""
        location = self._runtime.get_location(self._vin) or {}
        return location.get("gps_accuracy", 0)

