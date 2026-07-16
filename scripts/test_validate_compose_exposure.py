from scripts.validate_compose_exposure import validate_exposure


def test_accepts_nginx_public_port_and_loopback_services():
    config = {
        "services": {
            "nginx": {"ports": [{"target": 8080, "published": "80"}]},
            "redis": {
                "ports": [{"host_ip": "127.0.0.1", "target": 6379, "published": "6379"}]
            },
        }
    }

    assert validate_exposure(config) == []


def test_rejects_non_nginx_public_port():
    config = {
        "services": {
            "nginx": {"ports": [{"target": 8080, "published": "80"}]},
            "redis": {"ports": [{"target": 6379, "published": "6379"}]},
        }
    }

    assert validate_exposure(config) == ["unexpected public port: redis 6379->6379"]


def test_requires_nginx_public_port():
    config = {
        "services": {
            "nginx": {
                "ports": [{"host_ip": "127.0.0.1", "target": 80, "published": "8080"}]
            }
        }
    }

    assert validate_exposure(config) == [
        "required public port is missing: nginx 80->8080"
    ]


def test_rejects_host_network_mode():
    config = {
        "services": {
            "nginx": {"ports": [{"target": 8080, "published": "80"}]},
            "backend": {"network_mode": "host"},
        }
    }

    assert validate_exposure(config) == ["host network mode is forbidden: backend"]
