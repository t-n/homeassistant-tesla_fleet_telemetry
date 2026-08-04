# Architecture

`tesla_fleet_gateway` receives Tesla Fleet Telemetry over mTLS and publishes decoded messages to MQTT.
`tesla_fleet_stream` subscribes to MQTT and creates Home Assistant entities.

The integration exports short-lived token handoff data for the add-on at:
`/config/tesla_fleet_stream/gateway_handoff.json`
