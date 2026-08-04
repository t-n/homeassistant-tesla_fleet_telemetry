"""Tesla Fleet API helpers for Tesla Fleet Stream."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow

from .const import CONF_FLEET_API_BASE, DEFAULT_FLEET_API_BASE

_LOGGER = logging.getLogger(__name__)


async def async_fetch_vehicle_vins(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """Return VINs visible to the authenticated Tesla account."""
    if not isinstance(entry.data.get("token"), dict):
        return []

    fleet_base = (
        entry.options.get(CONF_FLEET_API_BASE)
        or entry.data.get(CONF_FLEET_API_BASE)
        or DEFAULT_FLEET_API_BASE
    ).rstrip("/")

    try:
        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(
                hass, entry
            )
        )
    except ValueError as err:
        _LOGGER.warning("Failed to resolve Tesla OAuth implementation: %s", err)
        return []

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
        access_token = session.token["access_token"]
    except aiohttp.ClientResponseError as err:
        if err.status in (400, 401):
            _LOGGER.warning(
                "Tesla OAuth token refresh was rejected (HTTP %s); reauthentication required",
                err.status,
            )
            raise ConfigEntryAuthFailed(
                "Tesla OAuth token refresh was rejected"
            ) from err
        _LOGGER.warning("Failed to refresh Tesla OAuth access token: %s", err)
        return []
    except aiohttp.ClientError as err:
        _LOGGER.warning("Failed to refresh Tesla OAuth access token: %s", err)
        return []

    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(
                f"{fleet_base}/api/1/vehicles",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as response:
                response.raise_for_status()
                payload = await response.json()
    except aiohttp.ClientResponseError as err:
        if err.status in (401, 403):
            _LOGGER.warning(
                "Tesla Fleet API rejected the access token (HTTP %s); reauthentication required",
                err.status,
            )
            raise ConfigEntryAuthFailed(
                "Tesla Fleet API rejected the access token"
            ) from err
        _LOGGER.warning(
            "Failed to fetch Tesla vehicles from %s: %s",
            fleet_base,
            err,
        )
        return []
    except aiohttp.ClientError as err:
        _LOGGER.warning(
            "Failed to fetch Tesla vehicles from %s: %s",
            fleet_base,
            err,
        )
        return []

    vehicles = payload.get("response")
    if not isinstance(vehicles, list):
        _LOGGER.warning("Unexpected Tesla vehicle list response: %s", payload)
        return []

    vins: list[str] = []
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        vin = vehicle.get("vin")
        if isinstance(vin, str) and vin:
            vins.append(vin)

    return vins
