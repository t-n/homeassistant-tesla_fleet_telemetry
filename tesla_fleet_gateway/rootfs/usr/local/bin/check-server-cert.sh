#!/usr/bin/env bash

set -euo pipefail

HOST="${1:-}"
PORT="${2:-443}"
CA_FILE="${3:-}"

if [ -z "$HOST" ]; then
    echo "usage: $0 <host> [port] [ca-file]" >&2
    exit 2
fi

if [ -n "$CA_FILE" ]; then
    openssl s_client -connect "${HOST}:${PORT}" -servername "$HOST" -verify_return_error -CAfile "$CA_FILE" </dev/null
else
    openssl s_client -connect "${HOST}:${PORT}" -servername "$HOST" -verify_return_error </dev/null
fi

