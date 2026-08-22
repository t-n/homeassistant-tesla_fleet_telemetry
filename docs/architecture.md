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
| Power (live) | `PackVoltage` + `PackCurrent` | HV pack kW (negative while discharging) |
| Consumption (live) | pack power + `VehicleSpeed` | Instant Wh/km while moving |
| Consumption average (live) | `Odometer` + (`LifetimeEnergyUsed` or `EnergyRemaining`) | Wh/km for the current drive session |

Derived entities are created lazily (not at VIN discovery) once their inputs have been seen.

### Telemetry intervals for derived consumption

Fleet Telemetry `interval_seconds` is a **minimum** gap between change-based updates.
Derived sensors combine the latest cached values, so mismatched intervals skew the result
(e.g. fresh pack current with a 10 s-old speed).

| Derived sensor | Inputs that should share an interval |
|----------------|--------------------------------------|
| Power / Consumption (live) | `PackVoltage`, `PackCurrent`, `VehicleSpeed` |
| Consumption average (live) | `Odometer` with `LifetimeEnergyUsed` (preferred) or `EnergyRemaining` |

Defaults use **10 s** for all of those. For higher-resolution live Wh/km, set
`PackVoltage`, `PackCurrent`, and `VehicleSpeed` to the same lower value (e.g. all `1`).
Do not lower only the pack fields.
