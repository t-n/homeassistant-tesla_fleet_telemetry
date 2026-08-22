# Tesla Fleet Gateway

Beta add-on that hosts your Tesla **public key (PEM)** and receives **Fleet Telemetry** over mTLS, then publishes decoded data to MQTT for the companion **`tesla_fleet_stream`** integration.

This add-on does **not** replace Home Assistant or the official **`tesla_fleet`** integration. It only exposes Tesla-specific endpoints on your public domain.

## Prerequisites

1. Official Home Assistant **`tesla_fleet`** already set up (virtual key / `tesla_fleet.key` present).
2. A public hostname with a valid TLS certificate covering **`<domain>`** and **`telemetry.<domain>`** (Let's Encrypt recommended).
3. Router or reverse-proxy forwarding **WAN `:443`** to this add-on's TLS listener (default **`1443`**).
4. An MQTT broker (Home Assistant Mosquitto add-on is fine).
5. Companion integration **`tesla_fleet_stream`** for OAuth handoff and live entities.

## Quick start

1. Finish official **`tesla_fleet`** setup (credentials, `/config/tesla_fleet.key`, virtual key).
2. Install this add-on; set **Domain** and **MQTT**; leave **Telemetry subdomain** off; confirm the public PEM.
3. Install **`tesla_fleet_stream`**, set **Fleet API region**, complete OAuth (handoff for this add-on).
4. Pair the virtual key if needed: `https://tesla.com/_ak/<domain>`.
5. Register **`telemetry.<domain>`** in the Tesla developer app, enable **Telemetry subdomain** in **Hosts**, restart the add-on.

Open the **Documentation** tab for full setup, options, security notes, and troubleshooting.
