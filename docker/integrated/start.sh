#!/bin/sh
set -eu
# Adopt only Bridge state, never customer photograph directories.
mkdir -p /bridge-data
chown 1001:1001 /bridge-data
export PIXCAKE_BRIDGE_PASSWORD="${BRIDGE_ADMIN_PASSWORD:-}"
exec supervisord -c /opt/integrated/supervisord.conf
