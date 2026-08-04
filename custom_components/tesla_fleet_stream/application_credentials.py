"""Application credentials platform for Tesla Fleet Stream."""

from homeassistant.components.application_credentials import ClientCredential
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .oauth import TeslaFleetStreamImplementation


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> config_entry_oauth2_flow.AbstractOAuth2Implementation:
    """Return the Tesla OAuth implementation."""
    return TeslaFleetStreamImplementation(hass, auth_domain, credential)


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return placeholders for the Application Credentials dialog."""
    return {
        "developer_url": "https://developer.tesla.com/",
        "redirect_url": "https://my.home-assistant.io/redirect/oauth",
    }
