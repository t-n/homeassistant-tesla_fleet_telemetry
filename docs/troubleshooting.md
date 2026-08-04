# Troubleshooting

- **No telemetry data**: verify vehicle is awake, MQTT reachable, and telemetry host enabled.
- **`missing_key`**: pair virtual key via `https://tesla.com/_ak/<domain>`.
- **TLS SAN warning**: cert must include `telemetry.<domain>`.
- **Handshake noise**: scanner traffic is expected; `SUPPRESS_TLS_HANDSHAKE_ERROR_LOGGING=true` is enabled.
- **Fleet API region mismatch**: set correct region/base URL.
- **Firmware**: vehicle firmware should support Fleet Telemetry (2023.20.6+ baseline).
