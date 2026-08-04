# Setup

This setup assumes the official `tesla_fleet` integration is already configured.

1. Install **Tesla Fleet Gateway** add-on.
2. Configure `domain`, `mqtt.topic_base`, and `region`.
3. Ensure TLS cert covers both `<domain>` and `telemetry.<domain>` (Let's Encrypt add-on recommended).
4. Forward WAN `:443` to add-on `advanced.tls_port` (default `1443`).
5. Install/add `tesla_fleet_stream` integration and reuse Tesla application credentials.
6. Enable `hosts.telemetry_enabled` after telemetry hostname registration in Tesla developer app.

If PEM is missing, the add-on derives it from `/config/tesla_fleet.key` when available.
