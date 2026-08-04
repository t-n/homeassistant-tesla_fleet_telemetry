#!/usr/bin/with-contenv bashio

set -euo pipefail

exec python3 /usr/local/bin/tesla_oauth.py token
