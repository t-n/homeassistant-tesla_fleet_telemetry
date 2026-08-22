# Setup

First-time order matters. The official integration owns credentials and the private
key; the add-on hosts PEM/telemetry; the custom integration owns OAuth handoff and
live entities.

## Install order

1. **Official `tesla_fleet`** — configure it first (Application Credentials, vehicles,
   `/config/tesla_fleet.key`, virtual-key pairing when prompted).
2. **DNS + TLS** — hostname for `<domain>` and `telemetry.<domain>`; certificate SANs
   for both (Let's Encrypt add-on recommended).
3. **Tesla Fleet Gateway add-on** — install, set `domain` and MQTT, keep
   **Telemetry subdomain** off, start, confirm the public PEM is reachable.
4. **`tesla_fleet_stream`** — install (HACS custom repo or copy), add the integration,
   set **Fleet API region** (`eu`/`na`/`cn`), complete OAuth (writes
   `gateway_handoff.json` for the add-on).
5. **Virtual key** (if not already paired) — `https://tesla.com/_ak/<domain>`.
6. **Enable telemetry** — register `telemetry.<domain>` in the Tesla developer app,
   then turn on **Hosts → Telemetry subdomain** and restart the add-on.
7. **Verify** — wake the vehicle; check MQTT and `tesla_fleet_stream` entities.

Forward WAN `:443` to add-on `advanced.tls_port` (default `1443`) before expecting
public PEM or vehicle mTLS to work.

If the public PEM is missing, the add-on derives it from `/config/tesla_fleet.key`
into `/share/tesla/.well-known/...`. It will not invent a new private key.

## After adding telemetry fields

Save add-on options and restart so the field list is pushed to Tesla. Entities are
not created the moment you add a field — see `docs/architecture.md` and the add-on
**Telemetry fields** option description.
