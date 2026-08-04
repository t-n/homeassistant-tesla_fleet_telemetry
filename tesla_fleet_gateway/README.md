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

1. Set **Domain**, **Fleet API region**, and **MQTT** options, then start the add-on.
2. Confirm the public PEM is reachable at `https://<domain>/.well-known/appspecific/com.tesla.3p.public-key.pem`.
3. Install **`tesla_fleet_stream`**, reuse Tesla Application Credentials, and complete OAuth.
4. Pair the virtual key: `https://tesla.com/_ak/<domain>`.
5. Register **`telemetry.<domain>`** in the Tesla developer app, then enable **Telemetry subdomain** in **Hosts**.

Open the **Documentation** tab for full setup, options, security notes, and troubleshooting.
