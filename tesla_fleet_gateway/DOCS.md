# Tesla Fleet Gateway

This add-on is an extension to the official `tesla_fleet` integration.

## Prerequisite

Official `tesla_fleet` integration must already be configured.

## Key points

- Keeps Tesla app credentials in Home Assistant Application Credentials.
- Reads token handoff from `tesla_fleet_stream`.
- Publishes telemetry to MQTT for live entities.

Refer to repository `docs/` for setup and troubleshooting.
