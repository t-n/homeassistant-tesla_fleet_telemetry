# Contributing

## Scope

This repository contains both the Home Assistant add-on (`tesla_fleet_gateway`) and custom integration (`tesla_fleet_stream`).

## Before you start

- **[AGENTS.md](AGENTS.md)** — technical layout, architecture, field/entity sync rules
- **[AI_POLICY.md](AI_POLICY.md)** — AI / LLM contribution rules (human-in-the-loop)

## Development

- Keep user docs concise and setup-focused.
- Avoid hardcoded hostnames, VINs, or local mount paths.
- Keep telemetry field support aligned between add-on schema and integration descriptions/translations.
- Prefer matching official `tesla_fleet` entity naming (see AGENTS.md).
- Before adding telemetry fields, confirm the exact `Field` enum name in Tesla’s `vehicle_data.proto` (see AGENTS.md). Invented names cause HTTP 400 `Unknown field` and reject the entire config.

## Validation

- Add-on: validate config schema and shell scripts.
- Integration: validate with `hassfest` and static checks (see CI workflows).

## Pull requests

You must be able to explain every change you submit. Do not open issues or PRs via autonomous agents. See **[AI_POLICY.md](AI_POLICY.md)**.
