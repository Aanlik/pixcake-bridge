#!/bin/sh
set -eu
if [ "${BRIDGE_ENABLED:-false}" != true ]; then
  echo 'Bridge 未启用：完成 PicPeak 初始化并配置 Public API Token 后，设 BRIDGE_ENABLED=true 并重建容器。'
  exec sleep infinity
fi
exec su-exec 1001:1001 /opt/bridge/venv/bin/uvicorn pixcake_bridge.app:app --host 0.0.0.0 --port 8080 --workers 1 --no-access-log
