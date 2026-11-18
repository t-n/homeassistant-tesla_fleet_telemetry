# Changelog

All notable changes to the **Tesla Fleet Gateway** add-on are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.8] - 2026-11-18

### Added
- `CHANGELOG.md` so Home Assistant Supervisor can show release notes in the add-on Changelog tab

## [0.6.7] - 2026-11-18

### Security
- Disable nginx HTTP/2 on the edge listener as a temporary [nginx2root](https://www.circl.lu/pub/tr-105/) mitigation (CVE-2026-123007 / CVE-2026-123633) until Alpine / Home Assistant base ships a patched nginx

### Notes
- PEM hosting and OAuth continue over HTTPS with HTTP/1.1
- Fleet Telemetry mTLS stream passthrough is unchanged and does not use HTTP/2
- Re-enable HTTP/2 only after the packaged nginx includes the upstream fixes

## [0.6.6] - 2026-11-15

### Fixed
- Surface Tesla `Unknown field` errors from `fleet_telemetry_config` apply and skip useless retries on permanent HTTP 4xx responses

### Changed
- Document proto `Field` validation before adding telemetry field names

## [0.6.5] - 2026-08-25

### Added
- `Gear` in default telemetry fields and schema so the gateway can stream shift state for trip-scoped consumption

### Notes
- Companion `tesla_fleet_stream` release adds trip-scoped consumption average and a `Gear (live)` sensor

## [0.6.0] - 2026-08-22

### Added
- Energy-related Fleet Telemetry defaults: `EnergyRemaining`, `Odometer`, `PackVoltage`, `PackCurrent`, `LifetimeEnergyUsed`
- Optional `include_fields` companions (for example pack V/I with speed; firmware ~2026.26.6+)

### Changed
- Fleet API **region** is configured only in `tesla_fleet_stream`; the add-on reads it from OAuth handoff (no separate add-on region option)
- Clearer MQTT defaults (blank broker → `127.0.0.1` on host network)
- Default telemetry hosting off until intentionally enabled after PEM / OAuth

### Fixed
- Make `include_fields` optional in the options schema so existing installs still start

## [0.5.0] - 2026-08-04

### Added
- First public release of Tesla Fleet Gateway: PEM hosting, Fleet Telemetry mTLS edge, MQTT publish
- Works with the companion `tesla_fleet_stream` integration for live Home Assistant entities

### Notes
- Requires official Home Assistant `tesla_fleet`, a public domain with TLS, and MQTT
- Beta: expect breaking changes
