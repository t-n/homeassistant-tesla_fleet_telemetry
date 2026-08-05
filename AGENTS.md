# Agent Guide

Guidance for humans and AI coding agents working in this repository.

Also read **[AI_POLICY.md](AI_POLICY.md)** and **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Scope

Public monorepo for:

| Component | Path | Role |
|-----------|------|------|
| Add-on **`tesla_fleet_gateway`** | `tesla_fleet_gateway/` | PEM hosting, Fleet Telemetry mTLS gateway, MQTT publish |
| Integration **`tesla_fleet_stream`** | `custom_components/tesla_fleet_stream/` | OAuth in HA, token handoff, live MQTT entities |

The add-on receives vehicle streams and publishes to MQTT. The integration creates Home Assistant entities. Official core **`tesla_fleet`** remains a prerequisite for credentials, virtual key, and `/config/tesla_fleet.key`.

Do not confuse add-on **source** with runtime state under `/addon_configs/<slug>_tesla_fleet_gateway/` on a Home Assistant host.

## Documentation roles

| File | Audience | Purpose |
|------|----------|---------|
| **`README.md`** | End users | Install overview |
| **`tesla_fleet_gateway/README.md`**, **`DOCS.md`** | Add-on store / Documentation tab | Sparse setup and troubleshooting |
| **`docs/*.md`** | End users | Setup, architecture, PEM, troubleshooting |
| **`AGENTS.md`** | Developers / agents | Technical detail and working rules |
| **`AI_POLICY.md`** | Contributors | AI / LLM contribution rules |
| **`CONTRIBUTING.md`** | Contributors | Short contribution summary |

Keep user-facing docs sparse. No implementation dump, script tables, or deep architecture in README/DOCS — put that here or in `docs/architecture.md`.

## Repository layout

### Add-on (`tesla_fleet_gateway/`)

- **`config.yaml`** — user-facing options and schema (UI)
- **`rootfs/usr/local/bin/addon-defaults.sh`** — internal defaults not in the UI
- **`Dockerfile`** — multi-stage build (`fleet-telemetry`, `vehicle-command`)
- **`rootfs/etc/services.d/tesla_fleet_gateway/run`** — s6 entrypoint
- **`rootfs/usr/local/bin/render-config.sh`** — preflight, nginx generation, migrations
- **`rootfs/usr/local/bin/tesla_oauth.py`** — OAuth helpers, telemetry field materialization
- **`rootfs/usr/local/bin/apply-telemetry-config.sh`** / **`auto-apply-telemetry-config.sh`** — Fleet Telemetry apply
- **`translations/en.yaml`** — add-on option labels

nginx config is generated inline in **`render-config.sh`**, not from a separate template.

### Integration (`custom_components/tesla_fleet_stream/`)

- **`manifest.json`**, **`config_flow.py`**, **`coordinator.py`**, **`descriptions.py`**
- **`translations/en.json`**, **`translations/sv.json`** — entity display names
- **`strings.json`** — config flow / OAuth UI only (not entity names)

## Architecture (short)

Router forwards **`WAN:443 → LAN:<advanced.tls_port>`** (default `1443`). Vehicles always connect to **`telemetry.<domain>:443`**.

Same public IP, different backends by **SNI**:

| SNI | `hosts.telemetry_enabled` | Backend |
|-----|---------------------------|---------|
| `domain` | either | nginx HTTPS → PEM, OAuth callback |
| telemetry host | `false` | nginx HTTPS → PEM (app registration) |
| telemetry host | `true` | TCP passthrough → `fleet-telemetry` (vehicle mTLS) |

Enable telemetry passthrough only after the telemetry hostname is registered in the Tesla developer app. One SNI cannot serve PEM HTTPS and accept vehicle mTLS at the same time.

```text
Internet :443 → advanced.tls_port
  ├── domain → nginx HTTPS → PEM / OAuth
  └── telemetry.<domain> (passthrough on) → fleet-telemetry mTLS → MQTT
```

## Configuration model

**User-facing** options live in **`tesla_fleet_gateway/config.yaml`** `options` / `schema` only:

| Group | Purpose |
|-------|---------|
| **`domain`** | Public hostname for PEM and Tesla registration |
| **`region`** | `eu` / `na` / `cn` Fleet API fallback |
| **`mqtt`** | Broker, topic base, optional auth |
| **`hosts`** | `pem_enabled`, `telemetry_enabled` |
| **`advanced`** | TLS port, telemetry host override, cert paths, access log |
| **`telemetry_fields`** | Field name enum + optional `interval_seconds` |

**Internal** defaults belong in **`addon-defaults.sh`**, not the UI. When adding an option, prefer an internal constant unless users must set it.

Supervisor may keep stale option keys after schema changes. **`render-config.sh`** resolves new paths first, then legacy keys.

When **`hosts.telemetry_enabled`** is `true`, runtime enables mTLS passthrough, vehicle-command proxy, and auto-apply. When `false`, the telemetry hostname serves PEM only.

## Storage conventions

| Path | Contents |
|------|----------|
| `/config/tesla_fleet.key` | Vehicle-command private key (official `tesla_fleet`) |
| `/config/tesla_fleet_stream/gateway_handoff.json` | Short-lived access token + `fleet_api_base` (no refresh token) |
| `/share/tesla/.../com.tesla.3p.public-key.pem` | Public PEM only |
| `/addon_configs/<slug>_tesla_fleet_gateway/` | Private add-on state (telemetry request JSON, etc.) |

Keep Home Assistant itself private. Expose only PEM, telemetry, and OAuth callback paths. Keep the vehicle-command proxy on **`127.0.0.1`** unless there is an explicit design change.

## Entity and translation naming

Stream entities should match official **`tesla_fleet`** naming where an equivalent exists:

1. Reuse the official **`translation_key`** (even if the stream platform differs, e.g. lock → binary_sensor).
2. Copy English/Swedish display names from official sources, then append **` (live)`**.
3. Reuse official enum/state labels when present.
4. Invent a new key only when there is no official equivalent; keep `{api_group}_{field}` style.

**Sources (in order):**

1. Running HA entity registry for official `tesla_fleet` entities (best for localized names).
2. Core English source: [`tesla_fleet/strings.json`](https://github.com/home-assistant/core/blob/dev/homeassistant/components/tesla_fleet/strings.json).
3. Installed `tesla_fleet/translations/<lang>.json` on the HA host for non-English.
4. This repo: `descriptions.py` + `translations/*.json` (grep before adding duplicates).

**Rules:**

- Translation JSON paths use the **stream** platform (`entity.sensor.…`, `entity.binary_sensor.…`), not the official platform.
- Never guess Swedish from English; copy from registry or official `sv.json`.
- Every key in `en.json` must exist in `sv.json` (and vice versa).
- Do not rename existing entities to diverge from `tesla_fleet` without a deliberate breaking-change reason.

### Files to touch for a new field / entity

| Step | Where | What |
|------|-------|------|
| 1 | `descriptions.py` | Sensor / binary_sensor / device_tracker description |
| 2 | `translations/en.json` + `sv.json` | Names (+ state enums if needed) with ` (live)` |
| 3 | `tesla_fleet_gateway/config.yaml` | `telemetry_fields` default + schema enum |
| 4 | `tesla_oauth.py` | `SUPPORTED_TELEMETRY_FIELDS` / `DEFAULT_TELEMETRY_FIELDS` |
| 5 | Versions | Bump add-on `config.yaml` and/or integration `manifest.json`; update changelog / commit message |

Composite Tesla fields (e.g. `Location`, `DoorState`) are special-cased in the integration coordinator/parsers; one MQTT field may fan out to multiple entities.

## Working rules

- Keep telemetry field support aligned across add-on schema, `tesla_oauth.py`, and integration descriptions/translations.
- Keep option changes synchronized across `config.yaml`, `translations/en.yaml`, `addon-defaults.sh`, runtime scripts, and user docs when behavior changes.
- Avoid hardcoded hostnames, VINs, private IPs, or local mount paths in committed files.
- Do not commit secrets, runtime `/addon_configs` state, or one-off local test files.
- Prefer matching official `tesla_fleet` patterns over inventing parallel APIs.

## Secrets and logging

Never log or commit OAuth tokens, refresh tokens, client secrets, authorization codes, or PKCE verifiers. Treat `gateway_handoff.json` like any on-disk secret (`0600`).

Suggested log markers (add-on):

- Success: `✅ <short title>`
- User action: `⚠️ ACTION REQUIRED` then Problem / Next step
- Info: `ℹ️ <short title>`
- Multi-line detail: `⎢` / `⎣`

## Code practices

Borrowed from Home Assistant Core agent guidance:

- Comments explain **why** (non-obvious constraints, workarounds), never narrate what the next line does. No section-divider comments.
- Keep `try` blocks as small as possible; do not catch exceptions from code that is not expected to raise.
- When validation guarantees a key exists, prefer `data["key"]` over `.get("key")` so contract bugs surface.
- Prefer Gold/Platinum-quality Home Assistant integrations as examples when looking up patterns.
- Aim for typed, async HA patterns in the integration; use `async_redact_data` for diagnostics.

## Validation

CI runs hassfest / HACS validation for the integration and a basic add-on config presence check. Before opening a PR:

- Integration: ensure `manifest.json`, translations, and structure pass hassfest locally if you have it (`home-assistant/actions/hassfest` equivalent).
- Add-on: validate `config.yaml` schema changes carefully; exercise shell scripts on a test install when changing runtime behavior.
- Do not invent Core-only commands (`script/setup`, `prek`, etc.) — this is not `home-assistant/core`.

## Versioning

When shipping a behavior change:

1. Bump **`tesla_fleet_gateway/config.yaml`** `version` and/or **`custom_components/tesla_fleet_stream/manifest.json`** `version`.
2. Note the change for release (add-on changelog if present; otherwise commit message).
3. Update user docs if options, paths, ports, or onboarding changed.
4. Keep add-on and integration version bumps coherent when a field spans both.

Supervisor only picks up local add-on updates after the add-on **`version`** changes and the store is reloaded.
