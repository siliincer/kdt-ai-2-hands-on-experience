"""Reject unintended publicly published ports in merged EC2 Compose output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PUBLIC_HOSTS = {None, "", "0.0.0.0", "::"}
ALLOWED_PUBLIC_PORTS = {("nginx", 80)}


def public_bindings(config: dict) -> set[tuple[str, int]]:
    bindings: set[tuple[str, int]] = set()
    for service_name, service in config.get("services", {}).items():
        for port in service.get("ports", []):
            if port.get("host_ip") in PUBLIC_HOSTS:
                bindings.add((service_name, int(port["published"])))
    return bindings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    unexpected = public_bindings(config) - ALLOWED_PUBLIC_PORTS
    if unexpected:
        for service, port in sorted(unexpected):
            print(f"ERROR: unexpected public port: {service}:{port}")
        return 1
    print("EC2 Compose public port validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
