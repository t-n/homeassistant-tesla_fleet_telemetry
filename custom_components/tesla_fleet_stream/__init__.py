"""Tesla Fleet Stream integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ATTACH_TO_EXISTING_DEVICE,
    CONF_DEVICE_DOMAIN,
    CONF_ENABLED_PLATFORMS,
    CONF_FLEET_API_BASE,
    CONF_TOPIC_BASE,
    PLATFORMS,
)
from .coordinator import TeslaFleetStreamRuntime
from .token_export import (
    async_setup_token_export,
    remove_token_exports,
)

_LOGGER = logging.getLogger(__name__)

# Settings that require tearing down MQTT/entities. Token refreshes update
# entry.data["token"] and must NOT reload — that marks every entity unavailable.
_RELOAD_SETTING_KEYS = (
    CONF_TOPIC_BASE,
    CONF_FLEET_API_BASE,
    CONF_ATTACH_TO_EXISTING_DEVICE,
    CONF_DEVICE_DOMAIN,
    CONF_ENABLED_PLATFORMS,
)


def _reload_signature(entry: ConfigEntry) -> tuple[tuple[str, Any], ...]:
    """Return reload-relevant settings, ignoring OAuth token churn."""
    config = {**entry.data, **entry.options}
    items: list[tuple[str, Any]] = []
    for key in _RELOAD_SETTING_KEYS:
        value = config.get(key)
        if isinstance(value, list):
            value = tuple(value)
        items.append((key, value))
    return tuple(items)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tesla Fleet Stream from a config entry."""
    entry.async_on_unload(await async_setup_token_export(hass, entry))

    runtime = TeslaFleetStreamRuntime(hass, entry)
    runtime.reload_signature = _reload_signature(entry)
    entry.runtime_data = runtime

    # Reload only when MQTT/entity options change — not on OAuth token writes.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # Discover vehicles and pre-register entities before platform setup so a
    # config-entry reload always re-creates registry entities synchronously.
    await runtime.async_discover_vehicles()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await runtime.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
        remove_token_exports(hass)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change; ignore OAuth token-only data updates."""
    runtime: TeslaFleetStreamRuntime | None = getattr(entry, "runtime_data", None)
    signature = _reload_signature(entry)
    if runtime is not None and runtime.reload_signature == signature:
        _LOGGER.debug(
            "Ignoring config entry update without setting changes (token refresh)"
        )
        return

    await hass.config_entries.async_reload(entry.entry_id)

