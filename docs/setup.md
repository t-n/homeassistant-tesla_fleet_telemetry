# Setup

This setup assumes the official `tesla_fleet` integration is already configured
(including `/config/tesla_fleet.key` and virtual-key pairing).

1. Install **Tesla Fleet Gateway** add-on.
2. Configure `domain`, `mqtt.topic_base`, and `region` (NA/EU/CN).
3. Ensure TLS cert covers both `<domain>` and `telemetry.<domain>` (Let's Encrypt add-on recommended). Set `advanced.certfile` / `advanced.keyfile` only if your files are not `/ssl/fullchain.pem` and `/ssl/privkey.pem`.
4. Forward WAN `:443` to add-on `advanced.tls_port` (default `1443`).
5. Install/add `tesla_fleet_stream` and reuse Tesla application credentials.
6. Enable `hosts.telemetry_enabled` after registering `telemetry.<domain>` in the Tesla developer app.

If the public PEM is missing, the add-on derives it from `/config/tesla_fleet.key` into `/share/tesla/.well-known/...`. It will not invent a new private key (Home Assistant config is read-only to the add-on).
