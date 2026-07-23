from scripts.validate_ec2_compose import public_bindings


def test_public_bindings_only_reports_non_loopback_ports():
    config = {
        "services": {
            "nginx": {"ports": [{"host_ip": "0.0.0.0", "published": "80"}]},
            "backend": {"ports": [{"host_ip": "127.0.0.1", "published": 8000}]},
            "redis": {"ports": [{"published": 6379}]},
        }
    }

    assert public_bindings(config) == {("nginx", 80), ("redis", 6379)}
