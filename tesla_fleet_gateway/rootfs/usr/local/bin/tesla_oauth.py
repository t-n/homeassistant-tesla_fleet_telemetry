#!/usr/bin/env python3

import argparse
import json
import os
import secrets
import stat
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.oauth2.rfc7636 import create_s256_code_challenge

MY_AUTH_CALLBACK_PATH = "https://my.home-assistant.io/redirect/oauth"
DEFAULT_FLEET_API_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
DEFAULT_HANDOFF_FILE = "/homeassistant/tesla_fleet_stream/gateway_handoff.json"
DEFAULT_HANDOFF_LEEWAY_SECONDS = 120
ALLOWED_FLEET_API_HOSTS = frozenset(
    {
        "fleet-api.prd.na.vn.cloud.tesla.com",
        "fleet-api.prd.eu.vn.cloud.tesla.com",
        "fleet-api.prd.cn.vn.cloud.tesla.cn",
    }
)
# Keep intervals aligned with config.yaml default telemetry_fields.
DEFAULT_TELEMETRY_FIELDS = {
    "Soc": {"interval_seconds": 1},
    "VehicleSpeed": {"interval_seconds": 10},
    "Location": {"interval_seconds": 10},
    "ChargeAmps": {"interval_seconds": 1},
    "InsideTemp": {"interval_seconds": 60},
    "OutsideTemp": {"interval_seconds": 60},
    "DetailedChargeState": {"interval_seconds": 1, "resend_interval_seconds": 300},
    "ChargeState": {"interval_seconds": 1},
    "DCChargingPower": {"interval_seconds": 1},
    "TimeToFullCharge": {"interval_seconds": 1},
    "Locked": {"interval_seconds": 1, "resend_interval_seconds": 300},
    "DoorState": {"interval_seconds": 1, "resend_interval_seconds": 300},
    "DriverSeatOccupied": {"interval_seconds": 1, "resend_interval_seconds": 300},
    "ACChargingPower": {"interval_seconds": 1},
    "IdealBatteryRange": {"interval_seconds": 10, "resend_interval_seconds": 300},
    "ChargeRateMilePerHour": {"interval_seconds": 1},
    "RatedRange": {"interval_seconds": 10, "resend_interval_seconds": 300},
}


class OAuthError(RuntimeError):
    pass


def log(level, message):
    level_label = {
        "info": "INFO",
        "warning": "WARNING",
        "error": "ERROR",
    }.get(level, level.upper())
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {level_label}: {message}", file=sys.stderr, flush=True)


def log_success(title, detail=None):
    log("info", f"✅ {title}")
    if detail:
        log("info", f"⎣ {detail}")


def log_notice(title, detail=None):
    log("info", f"ℹ️ {title}")
    if detail:
        log("info", f"⎣ {detail}")


def warn_next_step(problem, next_step, details=None):
    detail_lines = [f"Problem: {problem}", f"Next step: {next_step}"] + list(details or [])

    log("warning", "⚠️ ACTION REQUIRED")
    for index, detail in enumerate(detail_lines):
        prefix = "⎣" if index == len(detail_lines) - 1 else "⎢"
        log("warning", f"{prefix} {detail}")


def log_error(problem, next_step):
    detail_lines = [f"Problem: {problem}", f"Next step: {next_step}"]

    log("error", "⚠️ ACTION REQUIRED")
    for index, detail in enumerate(detail_lines):
        prefix = "⎣" if index == len(detail_lines) - 1 else "⎢"
        log("error", f"{prefix} {detail}")


def env(name, default=""):
    value = os.environ.get(name, default)
    return "" if value in ("", "null", None) else value


def write_secret_json(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(data, file, separators=(",", ":"))
    os.replace(tmp, target)
    os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)


def write_json_file(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")
    os.replace(tmp, target)
    os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)


def read_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


# Mirror of the raw Tesla field names the tesla_fleet_stream integration can map
# to Home Assistant entities (descriptions.py + DEFAULT_TELEMETRY_FIELDS). Keep
# this in sync with the config.yaml telemetry_fields enum when adding support.
SUPPORTED_TELEMETRY_FIELDS = frozenset(DEFAULT_TELEMETRY_FIELDS)
DEFAULT_ADDON_OPTIONS_FILE = "/data/options.json"
DEPRECATED_TELEMETRY_FIELD_RENAMES = {
    "EstBatteryRange": "RatedRange",
}


def migrate_telemetry_fields(fields):
    """Apply one-way field renames for deprecated Tesla telemetry keys."""
    for old_name, new_name in DEPRECATED_TELEMETRY_FIELD_RENAMES.items():
        if old_name not in fields:
            continue
        old_settings = fields.pop(old_name)
        if new_name not in fields:
            fields[new_name] = dict(old_settings) if isinstance(old_settings, dict) else {}
    return fields


def load_configured_telemetry_fields(options_file=None):
    """Build the telemetry field map from add-on options.

    Falls back to DEFAULT_TELEMETRY_FIELDS when the option is absent or empty so
    upgraded installs keep their previous behavior. Names are constrained by the
    config.yaml enum, but any unknown name is still passed through (with a
    warning) so newly released Tesla fields are not blocked before the schema
    and integration descriptions are updated.
    """
    path = options_file or env("ADDON_OPTIONS_FILE", DEFAULT_ADDON_OPTIONS_FILE)
    options = read_json(path)
    raw = options.get("telemetry_fields") if isinstance(options, dict) else None
    if not isinstance(raw, list) or not raw:
        return dict(DEFAULT_TELEMETRY_FIELDS)

    fields = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        entry = {}
        interval = item.get("interval_seconds")
        if not isinstance(interval, bool) and isinstance(interval, int) and interval > 0:
            entry["interval_seconds"] = interval
        resend = item.get("resend_interval_seconds")
        if not isinstance(resend, bool) and isinstance(resend, int) and resend > 0:
            entry["resend_interval_seconds"] = resend
        fields[name] = entry
        if name not in SUPPORTED_TELEMETRY_FIELDS:
            log(
                "warning",
                f"⚠️ Telemetry field {name} has no tesla_fleet_stream entity "
                "mapping; its data will reach MQTT only",
            )

    if not fields:
        return migrate_telemetry_fields(dict(DEFAULT_TELEMETRY_FIELDS))

    # Pick up newly supported default fields on upgrade without re-saving options.
    for name, defaults in DEFAULT_TELEMETRY_FIELDS.items():
        if name not in fields:
            fields[name] = dict(defaults)
            continue
        for key, value in defaults.items():
            fields[name].setdefault(key, value)

    return migrate_telemetry_fields(fields)


def load_vin_allowlist(options_file=None):
    """Return optional VIN allowlist from add-on options."""
    path = options_file or env("ADDON_OPTIONS_FILE", DEFAULT_ADDON_OPTIONS_FILE)
    options = read_json(path)
    raw = options.get("vin_allowlist") if isinstance(options, dict) else None
    if not isinstance(raw, list):
        return set()
    allowlist = {vin.strip().upper() for vin in raw if isinstance(vin, str) and vin.strip()}
    return allowlist


def apply_vin_allowlist(vins):
    """Filter VINs by the optional allowlist."""
    vin_allowlist = load_vin_allowlist()
    if not vin_allowlist:
        return list(vins)
    filtered = [vin for vin in vins if isinstance(vin, str) and vin.upper() in vin_allowlist]
    if not filtered:
        raise OAuthError(
            "VIN allowlist is set but none of the listed VINs were returned by Fleet API"
        )
    return filtered


def normalize_fleet_api_base(audience):
    """Return a Tesla Fleet API base URL, rejecting unknown hosts."""
    if not audience:
        return DEFAULT_FLEET_API_BASE
    parsed = urlparse(audience.rstrip("/"))
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_FLEET_API_HOSTS:
        raise OAuthError(
            f"Unsupported Fleet API base URL: {audience}. "
            "Use the official NA, EU, or CN Tesla Fleet API host."
        )
    if parsed.path not in ("", "/"):
        raise OAuthError(f"Fleet API base URL must not include a path: {audience}")
    return f"https://{parsed.hostname}"


def fleet_api_base(audience):
    return normalize_fleet_api_base(audience)


@dataclass
class Settings:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    token_cache_file: str
    state_file: str
    redirect_uri: str
    callback_path: str
    bind_host: str
    bind_port: int
    audience: str
    scope: str
    handoff_file: str

    @classmethod
    def from_env(cls):
        callback_path = env("TESLA_OAUTH_CALLBACK_PATH", "/auth/external/callback")
        redirect_uri = env("TESLA_OAUTH_REDIRECT_URI", MY_AUTH_CALLBACK_PATH)

        return cls(
            client_id=env("TESLA_OAUTH_CLIENT_ID"),
            client_secret=env("TESLA_OAUTH_CLIENT_SECRET"),
            authorize_url=env("TESLA_OAUTH_AUTHORIZE_URL", "https://auth.tesla.com/oauth2/v3/authorize"),
            token_url=env("TESLA_OAUTH_TOKEN_URL", "https://auth.tesla.com/oauth2/v3/token"),
            token_cache_file=env("TESLA_OAUTH_TOKEN_CACHE_FILE", "/addon_config/tesla_oauth_tokens.json"),
            state_file=env("TESLA_OAUTH_STATE_FILE", "/addon_config/tesla_oauth_state.json"),
            redirect_uri=redirect_uri,
            callback_path=callback_path,
            bind_host=env("TESLA_OAUTH_CALLBACK_BIND_HOST", "127.0.0.1"),
            bind_port=int(env("TESLA_OAUTH_CALLBACK_BIND_PORT", "18543")),
            audience=env("TESLA_OAUTH_AUDIENCE"),
            scope=env("TESLA_OAUTH_SCOPE", "openid offline_access vehicle_device_data vehicle_location"),
            handoff_file=env("TESLA_OAUTH_HANDOFF_FILE", DEFAULT_HANDOFF_FILE),
        )


class HandoffStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        return read_json(self.path)

    def is_valid(self, handoff=None):
        handoff = handoff if handoff is not None else self.load()
        access_token = handoff.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return False

        expires_at = handoff.get("expires_at")
        if expires_at is None:
            return False

        try:
            return time.time() < int(expires_at) - DEFAULT_HANDOFF_LEEWAY_SECONDS
        except (TypeError, ValueError):
            return False

    def fleet_api_base(self, handoff=None):
        handoff = handoff if handoff is not None else self.load()
        base = handoff.get("fleet_api_base")
        if isinstance(base, str) and base:
            try:
                return normalize_fleet_api_base(base)
            except OAuthError:
                return None
        return None

    def access_token(self):
        handoff = self.load()
        if not self.is_valid(handoff):
            return None
        token = handoff.get("access_token")
        if isinstance(token, str) and token:
            return token
        return None


class TokenStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        return read_json(self.path)

    def save(self, token):
        write_secret_json(self.path, token)

    def has_refresh_token(self):
        value = self.load().get("refresh_token")
        return isinstance(value, str) and len(value) > 0


class TeslaOAuthManager:
    LOGIN_URL_TTL_SECONDS = 900
    TOKEN_REFRESH_LEEWAY_SECONDS = 120

    def __init__(self, settings):
        self.settings = settings
        self.store = TokenStore(settings.token_cache_file)
        self.handoff = HandoffStore(settings.handoff_file)
        self.uses_handoff = False

    def has_handoff(self):
        return self.handoff.is_valid()

    def uses_integration_handoff(self):
        return self.uses_handoff or self.has_handoff()

    def effective_fleet_api_base(self):
        handoff_base = self.handoff.fleet_api_base()
        if handoff_base:
            return handoff_base
        return fleet_api_base(self.settings.audience)

    def get_access_token_from_handoff(self, quiet=False):
        access_token = self.handoff.access_token()
        if not access_token:
            return None

        self.uses_handoff = True
        if not quiet:
            log_success(
                "Tesla OAuth access token loaded from tesla_fleet_stream",
                f"Handoff file: {self.settings.handoff_file}",
            )
        return access_token

    def _token_kwargs(self):
        kwargs = {}
        if self.settings.audience:
            kwargs["audience"] = self.settings.audience
        return kwargs

    def _session(self, token=None):
        def update_token(current_token, refresh_token=None, access_token=None):
            if refresh_token:
                current_token["refresh_token"] = refresh_token
            if access_token:
                current_token["access_token"] = access_token
            current_token["obtained_at"] = int(time.time())
            self.store.save(current_token)

        return OAuth2Session(
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret,
            scope=self.settings.scope,
            redirect_uri=self.settings.redirect_uri,
            token=token,
            update_token=update_token,
        )

    def require_app_credentials(self):
        if not self.settings.client_id or not self.settings.client_secret:
            raise OAuthError("Tesla OAuth app credentials are not fully configured")

    def create_authorization_url(self):
        self.require_app_credentials()

        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = create_s256_code_challenge(verifier)

        client = self._session()
        uri, _state = client.create_authorization_url(
            self.settings.authorize_url,
            state=state,
            code_challenge=challenge,
            code_challenge_method="S256",
            **self._token_kwargs(),
        )

        write_secret_json(
            self.settings.state_file,
            {
                "state": state,
                "code_verifier": verifier,
                "redirect_uri": self.settings.redirect_uri,
                "created_at": int(time.time()),
            },
        )
        return uri

    def exchange_code(self, code, verifier):
        self.require_app_credentials()

        client = self._session()
        token = client.fetch_token(
            self.settings.token_url,
            code=code,
            grant_type="authorization_code",
            code_verifier=verifier,
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret,
            **self._token_kwargs(),
        )
        if not isinstance(token.get("access_token"), str):
            raise OAuthError("token exchange response did not include access_token")
        if not isinstance(token.get("refresh_token"), str):
            raise OAuthError("token exchange response did not include refresh_token")

        token["obtained_at"] = int(time.time())
        self.store.save(token)
        return token

    def _token_valid(self, token, leeway):
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return False

        obtained_at = int(token.get("obtained_at", 0))
        expires_in = int(token.get("expires_in", 0))
        if obtained_at <= 0 or expires_in <= 0:
            return False

        return time.time() < obtained_at + expires_in - leeway

    def refresh(self, token=None):
        self.require_app_credentials()

        token = token or self.store.load()
        refresh_token = token.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise OAuthError("no cached refresh token")

        client = self._session(token=token)
        refreshed = client.refresh_token(
            self.settings.token_url,
            refresh_token=refresh_token,
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret,
            **self._token_kwargs(),
        )
        refreshed["obtained_at"] = int(time.time())
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        self.store.save(refreshed)
        return refreshed

    def get_access_token(self, quiet=False):
        handoff_token = self.get_access_token_from_handoff(quiet=quiet)
        if handoff_token:
            return handoff_token

        self.require_app_credentials()

        token = self.store.load()
        if not token.get("refresh_token"):
            raise OAuthError("no cached refresh token")

        if self._token_valid(token, self.TOKEN_REFRESH_LEEWAY_SECONDS):
            if not quiet:
                log_success(
                    "Tesla OAuth access token is still valid",
                    f"Using cached token from {self.settings.token_cache_file}",
                )
            return token["access_token"]

        refreshed = self.refresh(token)
        if not quiet:
            log_success(
                "Tesla OAuth access token refreshed",
                f"Updated token cache at {self.settings.token_cache_file}",
            )
        return refreshed["access_token"]

    def verify_tokens(self):
        if self.has_handoff():
            access_token = self.get_access_token_from_handoff()
            if not access_token:
                raise OAuthError("handoff access token is missing or expired")

            log_success(
                "Tesla OAuth access token loaded from tesla_fleet_stream",
                f"Handoff file: {self.settings.handoff_file}",
            )
            self.list_vehicle_vins(access_token)
            log_success(
                "Tesla OAuth handoff token is valid",
                f"Fleet API base: {self.effective_fleet_api_base()}",
            )
            return True

        token = self.store.load()
        access_token = token.get("access_token")
        refresh_token = token.get("refresh_token")

        if not isinstance(access_token, str) or not access_token:
            raise OAuthError("access_token is missing from token cache")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise OAuthError("refresh_token is missing from token cache")

        log_success(
            "Tesla OAuth access_token and refresh_token are present",
            f"Token cache: {self.settings.token_cache_file}",
        )

        self.get_access_token()
        log_success(
            "Tesla OAuth tokens are valid",
            "Access token is usable; refresh succeeded when the cached token was expired",
        )
        return True

    def list_vehicle_vins(self, access_token):
        response = requests.get(
            f"{self.effective_fleet_api_base()}/api/1/vehicles",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        vehicles = payload.get("response")
        if not isinstance(vehicles, list):
            raise OAuthError("Fleet API /api/1/vehicles returned an unexpected response")

        vins = []
        for vehicle in vehicles:
            if isinstance(vehicle, dict):
                vin = vehicle.get("vin")
                if isinstance(vin, str) and vin:
                    vins.append(vin)

        if not vins:
            raise OAuthError("Fleet API returned no vehicles for this account")

        return vins


def serve(settings):
    manager = TeslaOAuthManager(settings)

    if manager.has_handoff():
        log_success(
            "Tesla OAuth is managed by Home Assistant",
            f"Using access token from {settings.handoff_file}; callback service not needed",
        )
        while True:
            time.sleep(3600)

    log_success(
        "Tesla OAuth callback service started",
        f"Listening on {settings.bind_host}:{settings.bind_port}{settings.callback_path}",
    )

    if not settings.client_id or not settings.client_secret:
        warn_next_step(
            "Tesla OAuth is not configured for legacy add-on OAuth",
            "Complete OAuth in the tesla_fleet_stream integration in Home Assistant",
        )
    elif manager.store.has_refresh_token():
        log_success(
            "Tesla OAuth refresh token is cached",
            f"Token cache: {settings.token_cache_file}",
        )
    else:
        auth_url = manager.create_authorization_url()
        details = [
            f"Callback expected at: {settings.redirect_uri}",
            "Make sure this exact redirect URI is configured in the Tesla developer app",
        ]
        if settings.redirect_uri == MY_AUTH_CALLBACK_PATH:
            gateway_host = env("GATEWAY_HOST")
            gateway_port = env("GATEWAY_TLS_PORT", "443")
            if gateway_host:
                if gateway_port == "443":
                    my_home_url = f"https://{gateway_host}/"
                else:
                    my_home_url = f"https://{gateway_host}:{gateway_port}/"
                details.append(
                    f"Set My Home Assistant to {my_home_url} so the OAuth redirect reaches this gateway listener"
                )
        warn_next_step(
            "Tesla OAuth user authorization is not complete",
            f"Open this Tesla login URL and approve access: {auth_url}",
            details,
        )

    class Handler(BaseHTTPRequestHandler):
        server_version = "TeslaOAuth/1.0"

        def log_message(self, fmt, *args):
            parsed = urlparse(self.path)
            log_notice(
                "OAuth callback HTTP request",
                f"{self.command} {parsed.path or '/'}",
            )

        def send_text(self, status, body):
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def send_html(self, status, body):
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != settings.callback_path:
                self.send_text(404, "Not found\n")
                return

            query = parse_qs(parsed.query)
            code = query.get("code", [""])[0]
            state = query.get("state", [""])[0]
            error = query.get("error", [""])[0]

            if error:
                warn_next_step(
                    "Tesla OAuth callback returned an error",
                    "Restart the add-on to generate a fresh login URL, then retry authorization",
                    [f"Tesla error: {error}"],
                )
                self.send_text(400, "Tesla OAuth returned an error. Check add-on logs.\n")
                return

            state_payload = read_json(settings.state_file)
            if not code or not state or state != state_payload.get("state"):
                warn_next_step(
                    "OAuth callback was rejected because state or code was missing or invalid",
                    "Restart the add-on and use the latest Tesla login URL from the logs",
                )
                self.send_text(400, "OAuth callback rejected. Restart the add-on and use the latest login URL.\n")
                return

            created_at = int(state_payload.get("created_at", 0))
            if created_at <= 0 or time.time() - created_at > manager.LOGIN_URL_TTL_SECONDS:
                warn_next_step(
                    "OAuth callback was rejected because the login URL expired",
                    "Restart the add-on and use the latest Tesla login URL within 15 minutes",
                )
                self.send_text(400, "OAuth login URL expired. Restart the add-on and use the latest login URL.\n")
                return

            try:
                manager.exchange_code(code, state_payload["code_verifier"])
                Path(settings.state_file).unlink(missing_ok=True)
            except OAuthError as error:
                warn_next_step(
                    "Tesla OAuth token exchange failed",
                    "Verify Client ID, Client Secret, redirect URI, Fleet API region, scopes, and Tesla developer app settings",
                    [str(error)],
                )
                self.send_text(502, "Token exchange failed. Check add-on logs.\n")
                return
            except Exception as error:
                warn_next_step(
                    "Tesla OAuth token exchange failed",
                    "Verify Client ID, Client Secret, redirect URI, Fleet API region, scopes, and Tesla developer app settings",
                    [str(error)],
                )
                self.send_text(502, "Token exchange failed. Check add-on logs.\n")
                return

            log_success(
                "Tesla OAuth tokens stored",
                f"Token cache: {settings.token_cache_file}; token values were not logged",
            )
            self.send_html(
                200,
                "<script>window.close()</script>\n"
                "<p>Tesla OAuth completed. You can close this page.</p>\n",
            )

    server = ThreadingHTTPServer((settings.bind_host, settings.bind_port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def print_access_token(settings, quiet=False):
    manager = TeslaOAuthManager(settings)
    try:
        access_token = manager.get_access_token(quiet=quiet)
    except OAuthError as error:
        if str(error) == "handoff access token is missing or expired":
            warn_next_step(
                "Tesla OAuth access token from tesla_fleet_stream is missing or expired",
                "Complete OAuth in the tesla_fleet_stream integration in Home Assistant",
                [f"Expected handoff file: {settings.handoff_file}"],
            )
        elif str(error) == "Tesla OAuth app credentials are not fully configured":
            warn_next_step(
                "Tesla OAuth is not configured for legacy add-on token refresh",
                "Complete OAuth in the tesla_fleet_stream integration in Home Assistant",
                [
                    "Application Credentials stay in Home Assistant; the add-on reads gateway_handoff.json",
                ],
            )
        elif str(error) == "no cached refresh token":
            warn_next_step(
                "No Tesla OAuth refresh token is cached for legacy add-on OAuth",
                "Complete OAuth in the tesla_fleet_stream integration in Home Assistant",
                [f"Expected handoff file: {settings.handoff_file}"],
            )
        else:
            warn_next_step(
                "Tesla OAuth access token could not be obtained",
                "Complete OAuth again or verify Tesla developer app settings",
                [str(error)],
            )
        return 1
    except Exception as error:
        warn_next_step(
            "Tesla OAuth token refresh failed",
            "Verify Client ID, Client Secret, Fleet API region, and granted scopes; complete OAuth again if the cached refresh token was revoked",
            [str(error)],
        )
        return 1

    print(access_token)
    return 0


def verify_tokens(settings):
    manager = TeslaOAuthManager(settings)
    try:
        manager.verify_tokens()
    except OAuthError as error:
        if str(error) == "handoff access token is missing or expired":
            warn_next_step(
                "Tesla OAuth access token from tesla_fleet_stream is missing or expired",
                "Complete OAuth in the tesla_fleet_stream integration in Home Assistant",
                [f"Expected handoff file: {settings.handoff_file}"],
            )
        elif str(error) == "Tesla OAuth app credentials are not fully configured":
            warn_next_step(
                "Tesla OAuth is not configured for legacy add-on token refresh",
                "Complete OAuth in the tesla_fleet_stream integration in Home Assistant",
                [
                    "Application Credentials stay in Home Assistant; the add-on reads gateway_handoff.json",
                ],
            )
        elif str(error) in {
            "access_token is missing from token cache",
            "refresh_token is missing from token cache",
            "no cached refresh token",
        }:
            warn_next_step(
                "Tesla OAuth tokens are missing from the token cache",
                "Complete OAuth in the tesla_fleet_stream integration",
                [f"Expected token cache: {settings.token_cache_file}"],
            )
        elif str(error) == "Fleet API returned no vehicles for this account":
            warn_next_step(
                "Tesla OAuth tokens are valid but no vehicles were returned",
                "Verify the Tesla account has vehicles and Fleet API region matches your Tesla developer app",
            )
        else:
            warn_next_step(
                "Tesla OAuth token verification failed",
                "Complete OAuth again or verify Tesla developer app settings and Fleet API region",
                [str(error)],
            )
        return 1
    except requests.HTTPError as error:
        warn_next_step(
            "Tesla Fleet API rejected the OAuth access token",
            "Verify Fleet API region matches your Tesla developer app region and granted scopes",
            [str(error)],
        )
        return 1
    except Exception as error:
        warn_next_step(
            "Tesla OAuth token verification failed",
            "Verify Client ID, Client Secret, audience, and granted scopes; complete OAuth again if the refresh token was revoked",
            [str(error)],
        )
        return 1

    return 0


def prepare_telemetry_config(settings):
    request_file = Path(env("FLEET_TELEMETRY_REQUEST_FILE", "/addon_config/fleet_telemetry_config.json"))
    endpoint_host = env("TESLA_TELEMETRY_HOST") or env("TESLA_ENDPOINT_HOST")
    endpoint_port = int(env("TESLA_ENDPOINT_HTTPS_PORT", "443") or "443")
    ca_file = env("EDGE_TLS_CERT", "/ssl/fullchain.pem")

    if not endpoint_host:
        warn_next_step(
            "Tesla telemetry host is not configured",
            "Set domain in add-on options and ensure telemetry.<domain> resolves to this gateway",
        )
        return 1

    desired_fields = load_configured_telemetry_fields()

    if request_file.is_file():
        existing = read_json(request_file)
        vins = existing.get("vins")
        config = existing.get("config", {})
        hostname = config.get("hostname")
        port = config.get("port")
        if (
            isinstance(vins, list)
            and vins
            and all(isinstance(vin, str) and vin for vin in vins)
            and hostname == endpoint_host
            and str(port) == str(endpoint_port)
        ):
            try:
                vins = apply_vin_allowlist(vins)
            except OAuthError as error:
                warn_next_step(
                    "Fleet Telemetry request file could not be reconciled",
                    "Update vin_allowlist or delete the request file and restart the add-on",
                    [str(error)],
                )
                return 1

            existing_fields = config.get("fields")
            if not isinstance(existing_fields, dict):
                existing_fields = {}
            if existing_fields == desired_fields and existing.get("vins") == vins:
                log_success(
                    "Fleet Telemetry request file already matches add-on options",
                    f"Using {request_file} with {len(vins)} VIN(s) and "
                    f"{len(desired_fields)} field(s) for {endpoint_host}:{endpoint_port}",
                )
                return 0

            # Any option change (intervals, resend, field set, or VIN allowlist)
            # is written on startup.
            config["fields"] = desired_fields
            payload = {"vins": vins, "config": config}
            try:
                write_json_file(request_file, payload)
            except OSError as error:
                warn_next_step(
                    "Fleet Telemetry request file could not be updated",
                    f"Ensure the add-on can write to {request_file.parent}",
                    [str(error)],
                )
                return 1
            log_success(
                "Fleet Telemetry request file reconciled from add-on options",
                f"Applied {len(desired_fields)} configured field(s) and "
                f"{len(vins)} VIN(s) for {endpoint_host}:{endpoint_port}",
            )
            return 0

    manager = TeslaOAuthManager(settings)
    try:
        access_token = manager.get_access_token()
        vins = apply_vin_allowlist(manager.list_vehicle_vins(access_token))
        with Path(ca_file).open("r", encoding="utf-8") as file:
            ca = file.read()
        payload = {
            "vins": vins,
            "config": {
                "hostname": endpoint_host,
                "port": endpoint_port,
                "ca": ca,
                "fields": dict(desired_fields),
            },
        }
        write_json_file(request_file, payload)

        if not request_file.is_file():
            raise OSError(f"Fleet Telemetry request file was not persisted at {request_file}")
    except OAuthError as error:
        warn_next_step(
            "Fleet Telemetry request file could not be generated",
            "Verify Tesla OAuth tokens and app credentials, then restart the add-on",
            [str(error)],
        )
        return 1
    except requests.HTTPError as error:
        warn_next_step(
            "Fleet Telemetry request file could not be generated from Fleet API vehicle list",
            "Verify Fleet API region matches your Tesla developer app region",
            [str(error)],
        )
        return 1
    except OSError as error:
        warn_next_step(
            "Fleet Telemetry request file could not be written",
            f"Ensure the add-on can write to {request_file.parent}",
            [str(error)],
        )
        return 1
    except Exception as error:
        warn_next_step(
            "Fleet Telemetry request file could not be generated",
            "Check preceding OAuth and Fleet API logs, then restart the add-on",
            [str(error)],
        )
        return 1

    log_success(
        "Fleet Telemetry request file generated",
        f"Wrote {len(vins)} VIN(s) for {endpoint_host}:{endpoint_port} to {request_file}",
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description="Tesla OAuth manager for Tesla Fleet Gateway")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="Run the OAuth callback HTTP service")
    token_parser = subparsers.add_parser("token", help="Print a valid access token to stdout")
    token_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the access token without informational logs",
    )
    subparsers.add_parser("verify", help="Verify cached OAuth tokens and refresh when needed")
    subparsers.add_parser(
        "prepare-telemetry-config",
        help="Generate fleet_telemetry_config.json when it is missing",
    )

    args = parser.parse_args()
    settings = Settings.from_env()

    if args.command == "serve":
        try:
            serve(settings)
        except Exception as error:
            log_error(
                f"Tesla OAuth callback service failed: {error}",
                "Check tesla_oauth callback options, port availability, and preceding startup logs",
            )
            return 1
        return 0

    if args.command == "token":
        return print_access_token(settings, quiet=args.quiet)

    if args.command == "verify":
        return verify_tokens(settings)

    if args.command == "prepare-telemetry-config":
        return prepare_telemetry_config(settings)

    return 1


if __name__ == "__main__":
    sys.exit(main())
