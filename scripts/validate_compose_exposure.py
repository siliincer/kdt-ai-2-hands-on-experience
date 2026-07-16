"""Validate that an EC2 Compose config exposes only nginx HTTP publicly."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_EXPECTED_PUBLIC_BINDING = ("nginx", 8080, "80")


def validate_exposure(config: Mapping[str, object]) -> list[str]:
    services = config.get("services")
    if not isinstance(services, dict):
        return ["Compose config must contain a services mapping"]

    errors: list[str] = []
    expected_binding_found = False
    for service_name, raw_service in services.items():
        if not isinstance(service_name, str) or not isinstance(raw_service, dict):
            continue
        if raw_service.get("network_mode") == "host":
            errors.append(f"host network mode is forbidden: {service_name}")
        ports = raw_service.get("ports", [])
        if not isinstance(ports, list):
            continue
        for port in ports:
            if not isinstance(port, dict):
                continue
            host_ip = port.get("host_ip")
            if isinstance(host_ip, str) and host_ip in _LOOPBACK_HOSTS:
                continue

            binding = (service_name, port.get("target"), port.get("published"))
            if binding == _EXPECTED_PUBLIC_BINDING:
                expected_binding_found = True
                continue
            errors.append(
                f"unexpected public port: {service_name} "
                f"{port.get('published')}->{port.get('target')}"
            )

    if not expected_binding_found:
        errors.append("required public port is missing: nginx 80->8080")
    return errors


def main() -> int:
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"Invalid Compose JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(config, dict):
        print("Compose config must be a JSON object", file=sys.stderr)
        return 2

    errors = validate_exposure(config)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("EC2 Compose public exposure is limited to nginx host 80")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
