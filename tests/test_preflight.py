import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).parents[1] / "scripts/preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def compose():
    return {"services": {"picpeak": {"image": "picpeak-zh:3.134.1-zh.1", "volumes": [{"target": "/external-media/shoot", "read_only": True}]}, "bridge": {"image": "pixcake-bridge:0.1.0", "ports": [{"host_ip": "192.168.1.10"}], "volumes": [{"target": "/raw/shoot", "read_only": True}]}}}


def test_safe_deployment():
    assert preflight.validate(compose())


@pytest.mark.parametrize("ip", ["0.0.0.0", "::", "8.8.8.8"])
def test_bridge_public_bind_rejected(ip):
    cfg = compose()
    cfg["services"]["bridge"]["ports"][0]["host_ip"] = ip
    with pytest.raises(ValueError):
        preflight.validate(cfg)


@pytest.mark.parametrize("tag", ["latest", "stable", "main", "beta"])
def test_mutable_tags_rejected(tag):
    cfg = compose()
    cfg["services"]["picpeak"]["image"] = "picpeak-zh:" + tag
    with pytest.raises(ValueError):
        preflight.validate(cfg)


def test_raw_write_rejected():
    cfg = compose()
    cfg["services"]["bridge"]["volumes"][0]["read_only"] = False
    with pytest.raises(ValueError):
        preflight.validate(cfg)


def integrated():
    return {"services": {"picpeak": {
        "image": "picpeak-pixcake:3.134.1-zh.14-bridge.0.1.4",
        "ports": [{"host_ip": "192.168.1.12", "target": 3000}],
        "volumes": [
            {"target": "/external-media/Camera", "read_only": True},
            {"target": "/delivery", "read_only": False},
        ],
    }}}


def test_integrated_safe_deployment():
    assert preflight.validate(integrated())


def test_integrated_bridge_public_bind_rejected():
    cfg = integrated()
    cfg['services']['picpeak']['ports'][0]['host_ip'] = '0.0.0.0'
    with pytest.raises(ValueError):
        preflight.validate(cfg)


def test_integrated_bridge_port_must_not_be_published():
    cfg = integrated()
    cfg['services']['picpeak']['ports'].append({'host_ip': '192.168.1.12', 'target': 8080})
    with pytest.raises(ValueError):
        preflight.validate(cfg)


def test_integrated_camera_must_be_read_only():
    cfg = integrated()
    cfg['services']['picpeak']['volumes'][0]['read_only'] = False
    with pytest.raises(ValueError):
        preflight.validate(cfg)


def test_integrated_delivery_must_be_writable():
    cfg = integrated()
    cfg['services']['picpeak']['volumes'][1]['read_only'] = True
    with pytest.raises(ValueError):
        preflight.validate(cfg)
