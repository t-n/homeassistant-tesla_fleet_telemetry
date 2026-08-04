"""Helpers for managing Tesla application credentials."""

from __future__ import annotations

from homeassistant.components.application_credentials import DATA_COMPONENT
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_DOMAIN, CONF_NAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TESLA_FLEET_DOMAIN = "tesla_fleet"


def get_stored_credentials(hass: HomeAssistant, domain: str):
    """Return stored application credentials for a domain."""
    return hass.data[DATA_COMPONENT].async_client_credentials(domain)


def has_credentials(hass: HomeAssistant, domain: str = DOMAIN) -> bool:
    """Return whether application credentials exist for this integration."""
    return bool(get_stored_credentials(hass, domain))


async def create_credentials(
    hass: HomeAssistant,
    client_id: str,
    client_secret: str,
    *,
    name: str = "Tesla Fleet Stream",
) -> None:
    """Store application credentials for this integration."""
    if has_credentials(hass):
        return

    await hass.data[DATA_COMPONENT].async_create_item(
        {
            CONF_DOMAIN: DOMAIN,
            CONF_CLIENT_ID: client_id.strip(),
            CONF_CLIENT_SECRET: client_secret.strip(),
            CONF_NAME: name,
        }
    )
