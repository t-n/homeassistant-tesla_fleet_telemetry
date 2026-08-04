"""Config flow for Tesla Fleet Stream."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow

from .application_credentials import async_get_description_placeholders
from .const import (
    CONF_ATTACH_TO_EXISTING_DEVICE,
    CONF_DEVICE_DOMAIN,
    CONF_ENABLED_PLATFORMS,
    CONF_FLEET_API_BASE,
    CONF_TOPIC_BASE,
    DEFAULT_ATTACH_TO_EXISTING_DEVICE,
    DEFAULT_DEVICE_DOMAIN,
    DEFAULT_ENABLED_PLATFORMS,
    DEFAULT_FLEET_API_BASE,
    DEFAULT_TOPIC_BASE,
    DOMAIN,
)
from .credentials import (
    TESLA_FLEET_DOMAIN,
    create_credentials,
    get_stored_credentials,
    has_credentials,
)

_LOGGER = logging.getLogger(__name__)


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle Tesla OAuth, credentials, and MQTT settings."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the flow handler."""
        super().__init__()
        self._oauth_data: dict[str, Any] | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start setup: credentials, OAuth, then MQTT options."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if not has_credentials(self.hass):
            fleet_credentials = get_stored_credentials(self.hass, TESLA_FLEET_DOMAIN)
            if fleet_credentials:
                return await self.async_step_reuse_tesla_fleet()
            return await self.async_step_credentials()

        return await super().async_step_user(user_input)

    async def async_step_reuse_tesla_fleet(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reuse application credentials from the official Tesla Fleet integration."""
        fleet_credentials = get_stored_credentials(self.hass, TESLA_FLEET_DOMAIN)
        if not fleet_credentials:
            return await self.async_step_credentials()

        if user_input is not None:
            if user_input["action"] == "reuse":
                credential = next(iter(fleet_credentials.values()))
                await create_credentials(
                    self.hass,
                    credential.client_id,
                    credential.client_secret,
                    name=credential.name or "Tesla Fleet (shared)",
                )
                return await super().async_step_user()
            return await self.async_step_credentials()

        return self.async_show_form(
            step_id="reuse_tesla_fleet",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="reuse"): vol.In(
                        {
                            "reuse": "Reuse Tesla Fleet credentials",
                            "manual": "Enter credentials manually",
                        }
                    )
                }
            ),
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect Tesla developer application credentials."""
        if user_input is not None:
            await create_credentials(
                self.hass,
                user_input["client_id"],
                user_input["client_secret"],
            )
            return await super().async_step_user()

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(
                {
                    vol.Required("client_id"): str,
                    vol.Required("client_secret"): str,
                }
            ),
            description_placeholders=await async_get_description_placeholders(
                self.hass
            ),
        )

    async def async_step_mqtt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure MQTT topic and entity options."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_TOPIC_BASE])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Tesla Fleet Stream",
                data={
                    **(self._oauth_data or {}),
                    **user_input,
                },
            )

        return self.async_show_form(
            step_id="mqtt",
            data_schema=_build_schema(),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Re-authenticate when Tesla revokes the refresh token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm Tesla re-authentication."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await super().async_step_user()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Continue setup after OAuth succeeds."""
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)

        self._oauth_data = data
        return await self.async_step_mqtt()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return TeslaFleetStreamOptionsFlow(config_entry)


class TeslaFleetStreamOptionsFlow(OptionsFlow):
    """Handle Tesla Fleet Stream options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = {
            **self._config_entry.data,
            **self._config_entry.options,
        }
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(defaults),
        )


def _build_schema(defaults: dict | None = None) -> vol.Schema:
    """Build the MQTT and entity options schema."""
    defaults = defaults or {}
    platforms = {platform: platform for platform in DEFAULT_ENABLED_PLATFORMS}

    return vol.Schema(
        {
            vol.Required(
                CONF_TOPIC_BASE,
                default=defaults.get(CONF_TOPIC_BASE, DEFAULT_TOPIC_BASE),
            ): str,
            vol.Optional(
                CONF_FLEET_API_BASE,
                default=defaults.get(CONF_FLEET_API_BASE, DEFAULT_FLEET_API_BASE),
            ): str,
            vol.Optional(
                CONF_ATTACH_TO_EXISTING_DEVICE,
                default=defaults.get(
                    CONF_ATTACH_TO_EXISTING_DEVICE,
                    DEFAULT_ATTACH_TO_EXISTING_DEVICE,
                ),
            ): bool,
            vol.Optional(
                CONF_DEVICE_DOMAIN,
                default=defaults.get(CONF_DEVICE_DOMAIN, DEFAULT_DEVICE_DOMAIN),
            ): str,
            vol.Optional(
                CONF_ENABLED_PLATFORMS,
                default=defaults.get(
                    CONF_ENABLED_PLATFORMS, DEFAULT_ENABLED_PLATFORMS
                ),
            ): cv.multi_select(platforms),
        }
    )
