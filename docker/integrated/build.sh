#!/bin/sh
set -eu
bridge_root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
picpeak_root=${PICPEAK_SOURCE:-"$bridge_root/../picpeak-zh"}
base=picpeak-zh:3.134.1-zh.18
stack=picpeak-pixcake:3.134.1-zh.18-bridge.0.1.6
platform=${PLATFORM:-linux/amd64}
docker build --platform "$platform" --build-arg VITE_DEFAULT_LANGUAGE=zh-CN -f "$picpeak_root/Dockerfile.aio" -t "$base" "$picpeak_root"
docker build --platform "$platform" --build-arg PICPEAK_BASE="$base" -f "$bridge_root/Dockerfile.integrated" -t "$stack" "$bridge_root"
