# Contributing

## Scope

This repository contains both the Home Assistant add-on (`tesla_fleet_gateway`) and custom integration (`tesla_fleet_stream`).

## Development

- Keep user docs concise and setup-focused.
- Avoid hardcoded hostnames, VINs, or local mount paths.
- Keep telemetry field support aligned between add-on schema and integration descriptions/translations.

## Validation

- Add-on: validate config schema and shell scripts.
- Integration: validate with `hassfest` and static checks.

## Private ops scripts

Host-specific deploy/debug scripts live in `../ha-devtools/` and are not part of this repository.
