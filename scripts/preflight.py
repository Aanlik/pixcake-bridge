#!/usr/bin/env python3
"""Validate resolved Compose without printing secrets. Run before deployment."""
import ipaddress
import json
import subprocess


def validate(compose):
    services = compose["services"]
    for name in services:
        image = services[name]["image"]
        if "@sha256:" not in image:
            tag = image.rsplit(":", 1)[-1]
            if ":" not in image or tag.lower() in {"latest", "stable", "main", "beta"}:
                raise ValueError(f"{name} 镜像必须锁定明确版本或 digest")
    bridge = services.get("bridge", services["picpeak"])
    for port in bridge.get("ports", []):
        if "bridge" not in services and int(port.get("target", 0)) != 8080:
            continue
        ip = ipaddress.ip_address(port.get("host_ip", "0.0.0.0"))
        if ip.is_unspecified or not (ip.is_private or ip.is_loopback):
            raise ValueError("Bridge 仅能绑定局域网/本机 IP，禁止公网或 0.0.0.0")
    volumes = bridge["volumes"]
    raw = [v for v in volumes if v.get("target", "").startswith("/raw/")]
    if not raw or any(not v.get("read_only") for v in raw):
        raise ValueError("Bridge 的 RAW 挂载必须只读")
    if any(v.get("target") in {"/raw", "/photos", "/projects"} and not v.get("read_only") for v in volumes):
        raise ValueError("禁止把整个摄影项目可写挂载给 Bridge")
    proofs = [v for v in services["picpeak"]["volumes"] if v.get("target", "").startswith("/external-media/")]
    if not proofs or any(not v.get("read_only") for v in proofs):
        raise ValueError("PicPeak PROOF 挂载必须只读")
    return True


if __name__ == "__main__":
    value = subprocess.check_output(["docker", "compose", "config", "--format", "json"], text=True)
    validate(json.loads(value))
    print("部署检查通过：镜像版本锁定、Bridge 仅局域网、RAW/PROOF 只读")
