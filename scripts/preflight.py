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
    integrated = "bridge" not in services
    if integrated:
        app = services["picpeak"]
        volumes = app.get("volumes", [])
        ports = app.get("ports", [])
        if any(int(port.get("target", 0)) == 8080 for port in ports):
            raise ValueError("一体化部署不得把 Bridge 8080 映射到宿主机")
        for port in ports:
            if int(port.get("target", 0)) != 3000:
                continue
            ip = ipaddress.ip_address(port.get("host_ip", "0.0.0.0"))
            if ip.is_unspecified or not (ip.is_private or ip.is_loopback):
                raise ValueError("PicPeak 只能绑定局域网/本机 IP，禁止公网或 0.0.0.0")
        camera = [v for v in volumes if v.get("target") == "/external-media/Camera"]
        if not camera or any(not v.get("read_only") for v in camera):
            raise ValueError("Camera 必须只读挂载给 PicPeak 和 Bridge")
        media = [v for v in volumes if v.get("target", "").startswith("/external-media/")]
        if any(not v.get("read_only") for v in media):
            raise ValueError("Proof/Camera 媒体挂载必须只读")
        delivery = [v for v in volumes if v.get("target") == "/delivery"]
        if not delivery or any(v.get("read_only") for v in delivery):
            raise ValueError("Bridge 交付目录必须可写挂载到 /delivery")
    else:
        bridge = services["bridge"]
        for port in bridge.get("ports", []):
            ip = ipaddress.ip_address(port.get("host_ip", "0.0.0.0"))
            if ip.is_unspecified or not (ip.is_private or ip.is_loopback):
                raise ValueError("Bridge 仅能绑定局域网/本机 IP，禁止公网或 0.0.0.0")
        volumes = bridge.get("volumes", [])
        raw = [v for v in volumes if v.get("target", "").startswith("/raw/")]
        if not raw or any(not v.get("read_only") for v in raw):
            raise ValueError("Bridge 的 RAW 挂载必须只读")
        if any(v.get("target") in {"/raw", "/photos", "/projects"} and not v.get("read_only") for v in volumes):
            raise ValueError("禁止把整个摄影项目可写挂载给 Bridge")
        proofs = [v for v in services["picpeak"].get("volumes", []) if v.get("target", "").startswith("/external-media/")]
        if not proofs or any(not v.get("read_only") for v in proofs):
            raise ValueError("PicPeak PROOF 挂载必须只读")
    return True


if __name__ == "__main__":
    value = subprocess.check_output(["docker", "compose", "config", "--format", "json"], text=True)
    validate(json.loads(value))
    print("部署检查通过：镜像版本锁定、应用仅局域网、原片只读、Bridge 交付目录可写")
