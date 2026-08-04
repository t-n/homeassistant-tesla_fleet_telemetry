# PEM hosting models

## NGINX SSL proxy add-on already in use

The gateway add-on and NGINX proxy cannot both own the same Tesla domain on WAN port 443.
Use one endpoint owner for Tesla PEM + telemetry routing.

## External PEM host

If PEM is hosted externally, telemetry still requires a domain with valid TLS and routing to this gateway.

## Own reverse proxy

Use SNI/path routing so:
- `<domain>` serves PEM/OAuth callback
- `telemetry.<domain>` routes mTLS stream to fleet-telemetry
