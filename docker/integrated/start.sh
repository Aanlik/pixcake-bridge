#!/bin/sh
set -eu
# Adopt only Bridge state, never customer photograph directories.
mkdir -p /bridge-data
chown -R "${BRIDGE_UID:-1001}:${BRIDGE_GID:-1001}" /bridge-data
export PIXCAKE_BRIDGE_PASSWORD="${BRIDGE_ADMIN_PASSWORD:-}"
exec supervisord -c /opt/integrated/supervisord.conf
