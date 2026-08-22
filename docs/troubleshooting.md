# Troubleshooting

- **No telemetry data**: verify vehicle is awake, MQTT reachable, and telemetry host enabled.
- **New field missing in HA**: save/restart the add-on after editing Telemetry fields; wait for the car to stream a sample (change-only fields may wait until the value changes unless `resend_interval_seconds` is set). Derived sensors need their inputs first — see `docs/architecture.md`.
- **`missing_key`**: pair virtual key via `https://tesla.com/_ak/<domain>`.
- **TLS SAN warning**: cert must include `telemetry.<domain>`.
- **Handshake noise**: scanner traffic is expected; `SUPPRESS_TLS_HANDSHAKE_ERROR_LOGGING=true` is enabled.
- **Fleet API region mismatch**: set Region (`eu`/`na`/`cn`) in **`tesla_fleet_stream`** options (not the add-on), reload, restart the gateway.
- **Firmware**: vehicle firmware should support Fleet Telemetry (2023.20.6+ baseline).
- **Install order**: official `tesla_fleet` → add-on (PEM) → `tesla_fleet_stream` (OAuth) → enable telemetry — see `docs/setup.md`.
