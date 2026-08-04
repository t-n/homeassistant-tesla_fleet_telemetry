# Tesla Fleet Gateway

> **Beta / work in progress.** Expect breaking changes and rough edges. Use at your own risk.

This add-on is an extension to the official Home Assistant **`tesla_fleet`** integration. It:

- Serves your Tesla third-party **public key (PEM)** on your domain
- Terminates **Fleet Telemetry** (mTLS) on `telemetry.<domain>`
- Publishes decoded telemetry to **MQTT**

Home Assistant entities come from the companion custom integration **`tesla_fleet_stream`**, not from this add-on alone.

The add-on exposes only Tesla-specific traffic on your public domain. It does not replace or expose Home Assistant itself.

## Prerequisites

Before installing:

1. **Official `tesla_fleet`** configured and working, including virtual-key pairing and a private key at `/config/tesla_fleet.key`.
2. A Tesla developer app for your domain (Client ID / Client Secret used in Home Assistant Application Credentials).
3. A public DNS name you control, for example `tesla.example.com`.
4. TLS certificates that include **both** `<domain>` and `telemetry.<domain>` (Let's Encrypt add-on recommended; default paths `/ssl/fullchain.pem` and `/ssl/privkey.pem`).
5. Ability to forward **WAN port 443** to this host's add-on TLS port (default **1443**).
6. MQTT broker reachable from the add-on (default `core-mosquitto`).
7. Vehicle firmware that supports Fleet Telemetry (roughly **2023.20.6+**; some options need newer firmware).

## How the pieces fit together

| Piece | Role |
|-------|------|
| Official **`tesla_fleet`** | App credentials, private key, baseline vehicle/API setup |
| **This add-on** | Public PEM hosting + Fleet Telemetry gateway → MQTT |
| **`tesla_fleet_stream`** | Tesla OAuth in HA, short-lived token handoff to the add-on, live MQTT entities |

## Security

- **Client ID and Client Secret** stay in Home Assistant Application Credentials. Do **not** put them in add-on options.
- The integration exports a short-lived **access token** to `/config/tesla_fleet_stream/gateway_handoff.json` (mode `0600`).
- The add-on does **not** refresh tokens. When the handoff expires, re-authenticate in **`tesla_fleet_stream`**.
- Treat the handoff file like any secret on disk (Samba, backups, snapshots).
- Only the **public** PEM is served on the internet. The private key stays under Home Assistant config.

## Files

| File | Location | Notes |
|------|----------|--------|
| Private key | `/config/tesla_fleet.key` | From official `tesla_fleet`; add-on mounts config read-only |
| Public PEM | `/share/tesla/.well-known/appspecific/com.tesla.3p.public-key.pem` | Derived from the private key if missing |
| OAuth handoff | `/config/tesla_fleet_stream/gateway_handoff.json` | Written by the integration |
| Telemetry config | `/addon_configs/<slug>_tesla_fleet_gateway/fleet_telemetry_config.json` | Generated/reconciled by the add-on |

The add-on will **not** invent a new private key. If `/config/tesla_fleet.key` is missing, fix official `tesla_fleet` first (or place a matching EC private key there).

## Network and TLS

1. Set **Domain** in add-on options to your public hostname (not the `tesla.example.com` placeholder).
2. Forward **`your-domain:443`** → add-on **Gateway TLS port** (default **1443**), or terminate TLS on a reverse proxy and route:
   - `<domain>` → PEM / well-known paths
   - `telemetry.<domain>` → Fleet Telemetry (mTLS) to this gateway
3. Certificate SANs must include **`telemetry.<domain>`** before enabling vehicle telemetry.

**LAN testing:** if local DNS points your domain at the Home Assistant LAN IP, `https://your-domain/` on port 443 may not hit the add-on. Test with the listener port (for example `https://your-domain:1443/.well-known/...`) or via the public WAN path.

If you already use an NGINX SSL proxy (or similar) for the same Tesla domain on WAN 443, only **one** service can own that endpoint. Either let this add-on own Tesla PEM + telemetry routing, or front both with a reverse proxy that SNI/path-routes correctly.

## Setup

### 1. Tesla developer app

Reuse or create a Tesla developer app for your domain:

- Client ID / Client Secret → Home Assistant Application Credentials (same as official **`tesla_fleet`**)
- Domain registered in the app
- Redirect URI: `https://my.home-assistant.io/redirect/oauth`

Set **Fleet API region** (`na` / `eu` / `cn`) in add-on options as a fallback when the handoff file is not present yet.

### 2. Configure and start the add-on

Minimum options:

- **Domain** — public hostname
- **Region** — matches your Tesla developer app / account region
- **MQTT** — broker (`core-mosquitto` by default), topic base (default `tesla/telemetry`), credentials if required
- **Hosts → PEM enabled** — usually on
- **Hosts → Telemetry enabled** — leave **off** until the telemetry subdomain is registered and TLS is ready
- **Advanced** — TLS port, cert/key paths under `/ssl/` if not using the Let's Encrypt defaults

Start the add-on and read the logs. Look for **ACTION REQUIRED** blocks when something needs attention.

### 3. Confirm the public PEM

Open (from the internet or via the gateway port):

```text
https://<domain>/.well-known/appspecific/com.tesla.3p.public-key.pem
```

If the file was missing, the add-on derives it from `/config/tesla_fleet.key` into `/share/tesla/...`.

### 4. Install `tesla_fleet_stream` and complete OAuth

1. Install the custom integration (HACS or copy `custom_components/tesla_fleet_stream`).
2. Add it under **Settings → Devices & services**.
3. Reuse Tesla Application Credentials from **`tesla_fleet`** when prompted.
4. Finish OAuth via the standard `my.home-assistant.io` redirect.

The integration writes `gateway_handoff.json`. The add-on picks it up automatically. You never enter the Client Secret in add-on options.

### 5. Pair the virtual key

On a phone with the Tesla app:

```text
https://tesla.com/_ak/<your-domain>
```

### 6. Enable telemetry

1. Register **`telemetry.<domain>`** in the Tesla developer app and confirm TLS/PEM reachability for that host.
2. In add-on **Hosts**, enable **Telemetry subdomain (mTLS streaming)**.
3. Restart the add-on. When OAuth handoff is valid, it applies Fleet Telemetry config to allowlisted vehicles (or all vehicles if the allowlist is empty).

Optional: set **VIN allowlist** to limit which vehicles receive the telemetry config.

### 7. Telemetry fields (optional)

**Telemetry fields** controls which signals are requested from the vehicle:

- `interval_seconds` — minimum seconds between sends **when the value changes**
- `resend_interval_seconds` — optional periodic resend even when unchanged (firmware **2024.44.32+**; counts toward Fleet Telemetry billing). Omit for change-only.

Leave the list empty to use the built-in defaults. Fields that `tesla_fleet_stream` does not map still appear on MQTT but may not create entities.

### 8. Verify

1. Wake the vehicle (sleeping cars stream nothing).
2. Watch MQTT under your topic base.
3. Confirm entities under **`tesla_fleet_stream`**.

## Options reference

| Option | Purpose |
|--------|---------|
| `domain` | Public hostname for PEM and telemetry subdomains |
| `region` | Fleet API region fallback: `na`, `eu`, or `cn` |
| `mqtt.*` | Broker, topic base, optional username/password |
| `hosts.pem_enabled` | Serve public PEM on `<domain>` |
| `hosts.telemetry_enabled` | Accept Fleet Telemetry on `telemetry.<domain>` |
| `advanced.tls_port` | Local TLS listen port (default `1443`) |
| `advanced.certfile` / `keyfile` | Must be under `/ssl/` |
| `advanced.telemetry_host` | Override telemetry hostname if needed |
| `vin_allowlist` | Optional list of VINs to configure |
| `telemetry_fields` | Fields and intervals pushed to Tesla |

## Troubleshooting

| Problem | What to check |
|---------|----------------|
| Public key not reachable | WAN 443 → gateway TLS port; cert covers `<domain>`; PEM hosting enabled |
| OAuth / token errors | Re-authenticate **`tesla_fleet_stream`**; handoff must include a non-expired access token |
| Handoff expired | Re-auth the integration — the add-on does not refresh tokens |
| No telemetry data | Wake the vehicle; virtual key paired; MQTT reachable; `hosts.telemetry_enabled` on after subdomain registration |
| Stream drops after restart | Watchdog may wake/re-apply after disconnects; check logs for recovery messages |
| Fleet API errors | Region / `fleet_api_base` in handoff matches your Tesla app registration |
| `missing_key` | Pair virtual key via `https://tesla.com/_ak/<domain>` |
| TLS SAN warning | Certificate must include `telemetry.<domain>` |
| Scanner / browser noise on telemetry host | `client didn't provide a certificate` from non-vehicle clients is normal |
| Private key missing | Official `tesla_fleet` must create `/config/tesla_fleet.key`; the add-on will not generate one |
| Placeholder domain / incomplete setup | Logs show **ACTION REQUIRED** once, then the add-on **stops**. Fix options and start again |

Logs use **ACTION REQUIRED** blocks with concrete next steps when the add-on detects a blocking condition.
