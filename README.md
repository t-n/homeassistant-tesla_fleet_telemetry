# Home Assistant Tesla Fleet Telemetry

**Beta / work in progress.** This project is experimental and mostly unsupported.
Expect breaking changes, incomplete docs, and rough edges. Use at your own risk;
do not rely on it for production-critical automations.

Public monorepo for:

- `tesla_fleet_gateway` Home Assistant add-on (Fleet Telemetry gateway + PEM hosting)
- `tesla_fleet_stream` custom integration (live MQTT entities in Home Assistant)

## Prerequisite

This project assumes the official Home Assistant `tesla_fleet` integration is already configured and working.

## Install

### 1) Add-on

1. Add this repository URL in Home Assistant add-on store:
   `https://github.com/t-n/homeassistant-tesla_fleet_telemetry`
2. Install **Tesla Fleet Gateway**.
3. Configure domain, MQTT, and TLS settings.

### 2) Integration (`tesla_fleet_stream`)

This integration is **not** in the default HACS store. Add it as a
[custom repository](https://www.hacs.xyz/docs/faq/custom_repositories/):

1. Open **HACS**.
2. Click the **⋮** menu (top right) → **Custom repositories**.
3. Repository URL: `https://github.com/t-n/homeassistant-tesla_fleet_telemetry`
4. Type: **Integration**
5. Click **Add**, then download **Tesla Fleet Stream** from HACS.
6. Restart Home Assistant.
7. Add the integration under **Settings → Devices & services**.
8. Reuse Tesla Fleet app credentials in the config flow when prompted.

Manual alternative: copy `custom_components/tesla_fleet_stream` into your HA `custom_components` folder.

## Documentation

- `docs/setup.md`
- `docs/pem-hosting.md`
- `docs/troubleshooting.md`
- `docs/architecture.md`

## Contributing / agents

- `AGENTS.md` — technical guide for developers and coding agents
- `AI_POLICY.md` — AI / LLM contribution rules
- `CONTRIBUTING.md` — short contribution summary
