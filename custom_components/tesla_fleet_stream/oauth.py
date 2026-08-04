"""OAuth implementation for Tesla Fleet Stream."""

from __future__ import annotations

from typing import Any

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant

from .const import AUTHORIZE_URL, SCOPES, TOKEN_URL


class TeslaFleetStreamImplementation(AuthImplementation):
    """Tesla OAuth2 implementation using Home Assistant's redirect service."""

    def __init__(
        self,
        hass: HomeAssistant,
        auth_domain: str,
        credential: ClientCredential,
    ) -> None:
        """Initialize Tesla OAuth."""
        super().__init__(
            hass,
            auth_domain,
            credential,
            AuthorizationServer(AUTHORIZE_URL, TOKEN_URL),
        )

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra authorize query parameters required by Tesla."""
        return {
            "prompt": "login",
            "prompt_missing_scopes": "true",
            "scope": " ".join(SCOPES),
        }
