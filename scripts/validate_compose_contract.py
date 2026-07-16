"""Validate cross-service contracts in a rendered deployment Compose config."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping

_FINANCIAL_SERVICE_URL = "http://mock-financial-service:8002"


def validate_contract(config: Mapping[str, object]) -> list[str]:
    services = config.get("services")
    if not isinstance(services, dict):
        return ["Compose config must contain a services mapping"]

    errors: list[str] = []
    backend = services.get("backend")
    if not isinstance(backend, dict):
        return ["Compose config must contain the backend service"]

    environment = backend.get("environment")
    if not isinstance(environment, dict):
        errors.append("backend environment must be a mapping")
    else:
        if environment.get("APP_ENV") not in {"prod", "production"}:
            errors.append("backend APP_ENV must disable development logging")
        if environment.get("FINANCIAL_CLIENT") != "http":
            errors.append("backend FINANCIAL_CLIENT must be http")
        if environment.get("MOCK_FINANCIAL_SERVICE_URL") != _FINANCIAL_SERVICE_URL:
            errors.append(
                "backend MOCK_FINANCIAL_SERVICE_URL must use Compose service DNS"
            )

    depends_on = backend.get("depends_on")
    financial_dependency = (
        depends_on.get("mock-financial-service")
        if isinstance(depends_on, dict)
        else None
    )
    if (
        not isinstance(financial_dependency, dict)
        or financial_dependency.get("condition") != "service_healthy"
    ):
        errors.append("backend must wait for a healthy mock-financial-service")

    financial_service = services.get("mock-financial-service")
    if not isinstance(financial_service, dict):
        errors.append("Compose config must contain mock-financial-service")
        return errors

    if financial_service.get("working_dir") != "/data":
        errors.append("mock-financial-service working_dir must be /data")
    volumes = financial_service.get("volumes")
    volume_targets: set[object] = set()
    if isinstance(volumes, list):
        volume_targets = {
            volume.get("target") for volume in volumes if isinstance(volume, dict)
        }
    if "/data" not in volume_targets:
        errors.append("mock-financial-service must persist /data in a volume")

    agent = services.get("agent")
    if not isinstance(agent, dict):
        errors.append("Compose config must contain the agent service")
        return errors
    agent_environment = agent.get("environment")
    if not isinstance(agent_environment, dict):
        errors.append("agent environment must be a mapping")
    else:
        if agent_environment.get("BANK_CLIENT") != "local":
            errors.append(
                "agent BANK_CLIENT must remain local until APIs are compatible"
            )
        if "MOCK_FINANCIAL_SERVICE_URL" in agent_environment:
            errors.append(
                "agent must not claim unsupported mock-financial-service integration"
            )
    agent_depends_on = agent.get("depends_on")
    if (isinstance(agent_depends_on, dict) and "backend" in agent_depends_on) or (
        isinstance(agent_depends_on, list) and "backend" in agent_depends_on
    ):
        errors.append("agent must remain independent from backend startup")

    nginx = services.get("nginx")
    if not isinstance(nginx, dict):
        errors.append("Compose config must contain the nginx service")
        return errors
    if nginx.get("read_only") is not True:
        errors.append("nginx root filesystem must be read-only")
    security_opt = nginx.get("security_opt")
    if (
        not isinstance(security_opt, list)
        or "no-new-privileges:true" not in security_opt
    ):
        errors.append("nginx must enable no-new-privileges")
    cap_drop = nginx.get("cap_drop")
    if not isinstance(cap_drop, list) or "ALL" not in cap_drop:
        errors.append("nginx must drop all Linux capabilities")
    tmpfs = nginx.get("tmpfs")
    tmp_size: str | None = None
    if isinstance(tmpfs, list):
        for mount in tmpfs:
            if not isinstance(mount, str):
                continue
            target, separator, raw_options = mount.partition(":")
            if target != "/tmp" or not separator:
                continue
            options = dict(
                option.split("=", 1)
                for option in raw_options.split(",")
                if "=" in option
            )
            tmp_size = options.get("size")
            break
    if tmp_size != "64m":
        errors.append("nginx /tmp tmpfs size must be exactly 64m")
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

    errors = validate_contract(config)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Deployment Compose service contracts are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
