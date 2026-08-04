"""Export OAuth tokens for the Tesla Fleet Gateway add-on."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_FLEET_API_BASE,
    DEFAULT_FLEET_API_BASE,
    GATEWAY_HANDOFF_REEXPORT_INTERVAL_SECONDS,
    GATEWAY_HANDOFF_RELATIVE_PATH,
    OAUTH_TOKEN_EXPORT_RELATIVE_PATH,
    normalize_fleet_api_base,
)

_LOGGER = logging.getLogger(__name__)
HANDOFF_VERSION = 1


def _fleet_api_base(entry: ConfigEntry) -> str:
    """Return the configured Fleet API base URL."""
    raw = (
        entry.options.get(CONF_FLEET_API_BASE)
        or entry.data.get(CONF_FLEET_API_BASE)
        or DEFAULT_FLEET_API_BASE
    )
    try:
        return normalize_fleet_api_base(raw)
    except ValueError:
        _LOGGER.warning(
            "Invalid fleet_api_base %s; falling back to %s", raw, DEFAULT_FLEET_API_BASE
        )
        return DEFAULT_FLEET_API_BASE


def gateway_handoff_path(hass: HomeAssistant) -> str:
    """Return the absolute gateway handoff export path."""
    return hass.config.path(GATEWAY_HANDOFF_RELATIVE_PATH)


def legacy_export_path(hass: HomeAssistant) -> str:
    """Return the absolute legacy token export path."""
    return hass.config.path(OAUTH_TOKEN_EXPORT_RELATIVE_PATH)


def _expires_at(token: dict[str, Any]) -> int | None:
    """Return the Unix timestamp when the access token expires.

    Home Assistant's OAuth2 token dict stores an absolute ``expires_at`` (and
    ``expires_in``); it does not set ``obtained_at``. Prefer the absolute value,
    then fall back to ``obtained_at``/``expires_in``, and finally to "now plus
    expires_in" so the add-on can always reason about staleness.
    """
    expires_at = token.get("expires_at")
    if expires_at:
        try:
            return int(float(expires_at))
        except (TypeError, ValueError):
            pass

    expires_in = int(token.get("expires_in", 0) or 0)
    obtained_at = int(token.get("obtained_at", 0) or 0)
    if expires_in <= 0:
        return None
    if obtained_at > 0:
        return obtained_at + expires_in
    return int(time.time()) + expires_in


def write_json_file(path: str, data: dict[str, Any]) -> None:
    """Atomically write a JSON file with owner-only permissions."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"))
    os.replace(tmp_path, path)
    os.chmod(path, 0o600)


def write_gateway_handoff(
    path: str,
    *,
    access_token: str,
    fleet_api_base: str,
    expires_at: int | None,
) -> None:
    """Write the add-on gateway handoff file (access token only, no secrets)."""
    now = int(time.time())
    handoff = {
        "version": HANDOFF_VERSION,
        "access_token": access_token,
        "fleet_api_base": fleet_api_base,
        "exported_at": now,
        "expires_at": expires_at,
    }
    write_json_file(path, handoff)


def _remove_legacy_export(hass: HomeAssistant) -> None:
    """Delete any stale legacy oauth_tokens.json left by older versions."""
    path = legacy_export_path(hass)
    try:
        os.remove(path)
    except FileNotFoundError:
        return
    except OSError as err:
        _LOGGER.warning("Failed to remove legacy Tesla OAuth token export %s: %s", path, err)
        return
    _LOGGER.info("Removed legacy Tesla OAuth token export at %s", path)


async def async_export_gateway_handoff(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Refresh OAuth if needed and export gateway handoff for the add-on."""
    if not isinstance(entry.data.get("token"), dict):
        return False

    fleet_base = _fleet_api_base(entry)

    try:
        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(
                hass, entry
            )
        )
    except ValueError as err:
        _LOGGER.warning("Failed to resolve Tesla OAuth implementation: %s", err)
        return False

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
        token = session.token
    except aiohttp.ClientResponseError as err:
        if err.status in (400, 401):
            _LOGGER.warning(
                "Tesla OAuth token refresh was rejected (HTTP %s); reauthentication required",
                err.status,
            )
            raise ConfigEntryAuthFailed(
                "Tesla OAuth token refresh was rejected"
            ) from err
        _LOGGER.warning(
            "Failed to refresh Tesla OAuth access token for export: %s", err
        )
        return False
    except aiohttp.ClientError as err:
        _LOGGER.warning(
            "Failed to refresh Tesla OAuth access token for export: %s", err
        )
        return False

    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return False

    expires_at = _expires_at(token)
    if expires_at is None:
        _LOGGER.warning(
            "Tesla OAuth token is missing expiry metadata; refusing to export handoff"
        )
        return False

    handoff_path = gateway_handoff_path(hass)
    try:
        write_gateway_handoff(
            handoff_path,
            access_token=access_token,
            fleet_api_base=fleet_base,
            expires_at=expires_at,
        )
    except OSError as err:
        _LOGGER.error(
            "Failed to export Tesla gateway handoff to %s: %s", handoff_path, err
        )
        return False

    # The long-lived refresh token is never exported. The add-on consumes only
    # the short-lived access token via the handoff file. Any stale legacy
    # oauth_tokens.json is cleaned up below.
    _remove_legacy_export(hass)

    _LOGGER.debug("Exported Tesla gateway handoff for the Fleet Gateway add-on")
    return True


async def _async_export_and_handle_auth(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Export the handoff and start reauth if the refresh token was rejected."""
    try:
        await async_export_gateway_handoff(hass, entry)
    except ConfigEntryAuthFailed:
        # Background tasks do not surface ConfigEntryAuthFailed to Home
        # Assistant, so trigger the reauth flow explicitly here.
        entry.async_start_reauth(hass)


@callback
def async_export_tokens(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Schedule gateway handoff export for the add-on."""
    hass.async_create_task(_async_export_and_handle_auth(hass, entry))


def remove_token_exports(hass: HomeAssistant) -> None:
    """Remove add-on token export files on integration unload."""
    for path in (gateway_handoff_path(hass), legacy_export_path(hass)):
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
        except OSError as err:
            _LOGGER.warning(
                "Failed to remove Tesla token export at %s: %s", path, err
            )

    _LOGGER.info("Removed Tesla token exports for the Fleet Gateway add-on")


async def async_setup_token_export(
    hass: HomeAssistant, entry: ConfigEntry
) -> callback:
    """Export on setup and periodically re-export refreshed access tokens."""
    await async_export_gateway_handoff(hass, entry)

    @callback
    def _handle_interval(_now) -> None:
        hass.async_create_task(_async_export_and_handle_auth(hass, entry))

    return async_track_time_interval(
        hass,
        _handle_interval,
        timedelta(seconds=GATEWAY_HANDOFF_REEXPORT_INTERVAL_SECONDS),
    )
