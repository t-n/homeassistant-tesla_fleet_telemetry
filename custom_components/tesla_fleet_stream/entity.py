"""Base entities for Tesla Fleet Stream."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import update_signal, vehicle_connectivity_signal


class TeslaFleetStreamEntity(RestoreEntity, Entity):
    """Base entity for telemetry-backed entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime, vin: str, key: str, platform: str) -> None:
        self._runtime = runtime
        self._vin = vin
        self._key = key
        self._platform = platform

    @property
    def unique_id(self) -> str:
        """Return a stable unique ID."""
        return f"{self._vin.lower()}_{self._key}"

    @property
    def device_info(self):
        """Return device information."""
        return self._runtime.get_device_info(self._vin)

    @property
    def available(self) -> bool:
        """Keep last-known values visible; ignore flaky stream connectivity."""
        if self._key == "connectivity":
            return True

        # Availability is based only on whether we have a value. Fleet-telemetry
        # CONNECTED/DISCONNECTED events are too noisy to gate entity availability.
        return self._runtime.entity_has_stored_value(
            self._platform, self._vin, self._key
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose telemetry receipt timestamps on the entity."""
        timestamps = self._runtime.get_entity_timestamps(self._vin, self._key)
        if timestamps is None:
            return None
        return {
            "last_updated": timestamps.last_updated.isoformat(),
            "last_changed": timestamps.last_changed.isoformat(),
        }

    @callback
    def _restore_from_last_state(self, state) -> None:
        """Restore runtime state from a saved Home Assistant state."""

    @callback
    def _handle_update(self) -> None:
        """Handle a runtime state update."""
        self.async_write_ha_state()

    @callback
    def _handle_connectivity_update(self) -> None:
        """Refresh availability when vehicle connectivity changes."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register update listeners and restore the last known state."""
        await super().async_added_to_hass()
        await self._async_restore_state()
        self._async_register_update_listeners()

    async def _async_restore_state(self) -> None:
        """Restore runtime state from saved Home Assistant state."""
        if (last_state := await self.async_get_last_state()) is not None:
            self._runtime.restore_entity_timestamps(
                self._vin, self._key, last_state.attributes
            )
            if last_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                self._restore_from_last_state(last_state)

    def _async_register_update_listeners(self) -> None:
        """Register dispatcher listeners for runtime updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                update_signal(self._platform, self._vin, self._key),
                self._handle_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                vehicle_connectivity_signal(self._vin),
                self._handle_connectivity_update,
            )
        )
