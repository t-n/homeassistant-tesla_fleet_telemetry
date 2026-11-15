# Architecture

`tesla_fleet_gateway` receives Tesla Fleet Telemetry over mTLS and publishes decoded messages to MQTT.
`tesla_fleet_stream` subscribes to MQTT and creates Home Assistant entities.

The integration exports short-lived token handoff data for the add-on at:
`/config/tesla_fleet_stream/gateway_handoff.json`

## Drive energy sensors

Raw Fleet Telemetry fields `EnergyRemaining`, `Odometer`, `PackVoltage`, `PackCurrent`, and
`LifetimeEnergyUsed` are supported in the add-on defaults and mapped by the integration.
`LifetimeEnergyUsedDrive` is Semi-only and is not supported.

When the required inputs arrive over MQTT, the integration also creates derived sensors:

| Sensor | Requires | Meaning |
|--------|----------|---------|
| Power (live) | `PackVoltage` + `PackCurrent` | HV pack kW (REST sign: negative charging/regen, positive driving) |
| Consumption (live) | pack power + `VehicleSpeed` | Instant Wh/km while moving; `0` when parked/stopped |
| Consumption average (live) | `Odometer` + (`LifetimeEnergyUsed` or `EnergyRemaining`) | Wh/km for the current **trip** (open while `Gear` is D/R/N; falls back to driver-seat + brief stop grace); `0` when the trip ends |

Derived entities are created lazily (not at VIN discovery) once their inputs have been seen.

### When new fields appear in Home Assistant

Enabling a field in add-on **Telemetry fields** only asks Tesla to stream it. After you
**save and restart** the add-on (so config is pushed):

1. The vehicle must be **awake** and connected to Fleet Telemetry.
2. Mapped `tesla_fleet_stream` entities update (or are created) on the **first MQTT
   sample**. Tesla’s default is change-only, so a steady value may not arrive until it
   changes — set `resend_interval_seconds` if you need a periodic sample.
3. **Derived** sensors (Power, Consumption, Consumption average) appear only after
   their required inputs have been received and a sample can be computed.
4. Fields with no integration mapping still show on MQTT but never become HA entities.

### Telemetry intervals for derived consumption

Fleet Telemetry `interval_seconds` is a **minimum** gap between change-based updates.
Derived sensors combine the latest cached values, so mismatched intervals skew the result
(e.g. fresh pack current with a 10 s-old speed).

| Derived sensor | Inputs that should share an interval |
|----------------|--------------------------------------|
| Power / Consumption (live) | `PackVoltage`, `PackCurrent`, `VehicleSpeed` |
| Consumption average (live) | `Odometer` with `LifetimeEnergyUsed` (preferred) or `EnergyRemaining` |

**Preferred (firmware ~2026.26.6+):** use `include_fields` on the parent so companions
arrive in the **same** payload (even if unchanged). Defaults do this:

- `VehicleSpeed.include_fields`: `PackVoltage`, `PackCurrent`
- `Odometer.include_fields`: `LifetimeEnergyUsed`, `EnergyRemaining`

Pack/energy fields remain top-level as well so they can still update when the parent
is quiet (e.g. parked). On older firmware, `include_fields` is ignored — keep matching
`interval_seconds` as before.

Defaults use **10 s** for those parents. For higher-resolution live Wh/km, lower the
parent interval (and keep companions via `include_fields` or the same interval).
Do not lower only the pack fields on older firmware.

## TPMS and vehicle alerts

- **TPMS (`V` stream):** `TpmsPressureFl/Fr/Rl/Rr` (bar), `TpmsRcpFrontValue/RearValue` (recommended cold pressure, bar), and `TpmsSoftWarningFl/Fr/Rl/Rr` / `TpmsHardWarningFl/Fr/Rl/Rr` (problem binary sensors) are enabled in the add-on defaults and mapped by the integration. Note that TPMS sensors inside the wheels only broadcast while driving or shortly after motion.
- **Vehicle alerts (`alerts` stream):** The add-on configures `"alert_types": ["service", "customer", "service-fix"]` in `fleet_telemetry_config.json` and publishes vehicle alerts to `<topic_base>/<VIN>/alerts/<alert_name>/current` and `/history`. The integration subscribes to `<topic_base>/+/alerts/#` and exposes:
  - **Low washer fluid (live)** (`binary_sensor`, problem) — turns `on` when a washer fluid alert (e.g. `VCFRONT_a185_washerFluidLow`) is active and `off` when cleared.
  - **Active alerts (live)** (`sensor`, diagnostic) — count of currently active vehicle alerts, with `active_alerts`, `last_alert`, `last_alert_started_at`, `last_alert_ended_at`, and `last_alert_audiences` attributes.
