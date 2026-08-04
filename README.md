# Home Assistant Tesla Fleet Telemetry

Public monorepo for:

- `tesla_fleet_gateway` Home Assistant add-on (Fleet Telemetry gateway + PEM hosting)
- `tesla_fleet_stream` custom integration (live MQTT entities in Home Assistant)

## Prerequisite

This project assumes the official Home Assistant `tesla_fleet` integration is already configured and working.

## Known issue (HA 2026.8+)

`tesla_fleet_stream` currently uses a deprecated device-linking pattern (`attach_to_existing_device`) that relied on shared identifiers across config entries. From Home Assistant 2026.8, devices are restricted to one config entry, so this behavior will be replaced in a future release.

## Install

### 1) Add-on

1. Add this repository URL in Home Assistant add-on store:
   `https://github.com/t-n/homeassistant-tesla_fleet_telemetry`
2. Install **Tesla Fleet Gateway**.
3. Configure domain, MQTT, and TLS settings.

### 2) Integration

1. Install `tesla_fleet_stream` from HACS (or copy `custom_components/tesla_fleet_stream`).
2. Add integration from **Settings -> Devices & services**.
3. Reuse Tesla Fleet app credentials in the config flow when prompted.

## Documentation

- `docs/setup.md`
- `docs/pem-hosting.md`
- `docs/troubleshooting.md`
- `docs/architecture.md`
