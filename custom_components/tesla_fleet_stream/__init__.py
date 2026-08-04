"""Tesla Fleet Stream integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.helper_integration import async_remove_helper_devices

from .const import (
    CONF_ATTACH_TO_EXISTING_DEVICE,
    CONF_DEVICE_DOMAIN,
    CONF_ENABLED_PLATFORMS,
    CONF_FLEET_API_BASE,
    CONF_TOPIC_BASE,
    DEFAULT_DEVICE_DOMAIN,
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to HA 2026.8 device_entry linking."""
    if entry.version < 2:
        _LOGGER.debug(
            "Migrating tesla_fleet_stream from version %s to 2 (device_entry linking)",
            entry.version,
        )
        config = {**entry.data, **entry.options}
        device_domain = config.get(CONF_DEVICE_DOMAIN, DEFAULT_DEVICE_DOMAIN)
        device_registry = dr.async_get(hass)

        # Old attach mode put tesla_fleet identifiers in DeviceInfo, which either
        # co-owned the Fleet device or forked a duplicate. Clean those up and
        # relink entities to the real tesla_fleet device when present.
        for device in list(
            dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        ):
            for domain, vin in device.identifiers:
                if domain != device_domain:
                    continue
                source = None
                for candidate in device_registry.async_get_devices(
                    identifiers={(device_domain, vin)}
                ):
                    if candidate.id == device.id:
                        continue
                    for entry_id in candidate.config_entries:
                        cfg = hass.config_entries.async_get_entry(entry_id)
                        if cfg is not None and cfg.domain == device_domain:
                            source = candidate
                            break
                    if source is not None:
                        break
                if source is not None:
                    async_remove_helper_devices(
                        hass,
                        helper_config_entry_id=entry.entry_id,
                        source_device_id=source.id,
                    )
                break

        hass.config_entries.async_update_entry(entry, version=2)

    return True


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
