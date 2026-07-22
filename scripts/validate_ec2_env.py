"""Validate EC2 deployment secrets without printing their values."""

from __future__ import annotations

import argparse
import ipaddress
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED_SECRET_LENGTHS = {
    "POSTGRES_PASSWORD": 16,
    "JWT_SECRET_KEY": 32,
    "AGENT_WEBHOOK_SECRET": 32,
    "AGENT_SERVICE_TOKEN": 32,
    "BACKEND_SERVICE_TOKEN": 32,
}
KNOWN_PLACEHOLDERS = {
    "change-me",
    "change-me-agent-webhook",
    "change-me-in-local",
    "change-me-agent-service-token",
    "change-me-backend-service-token",
    "changeme",
    "mypassword",
    "password",
}
PRIVATE_VPC_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class ValidationError(StrEnum):
    POSTGRES_PASSWORD_MISSING = "POSTGRES_PASSWORD is missing or empty"
    POSTGRES_PASSWORD_PLACEHOLDER = "POSTGRES_PASSWORD uses a known placeholder"
    POSTGRES_PASSWORD_SHORT = "POSTGRES_PASSWORD must be at least 16 characters"
    JWT_SECRET_KEY_MISSING = "JWT_SECRET_KEY is missing or empty"
    JWT_SECRET_KEY_PLACEHOLDER = "JWT_SECRET_KEY uses a known placeholder"
    JWT_SECRET_KEY_SHORT = "JWT_SECRET_KEY must be at least 32 characters"
    AGENT_WEBHOOK_SECRET_MISSING = "AGENT_WEBHOOK_SECRET is missing or empty"
    AGENT_WEBHOOK_SECRET_PLACEHOLDER = "AGENT_WEBHOOK_SECRET uses a known placeholder"
    AGENT_WEBHOOK_SECRET_SHORT = "AGENT_WEBHOOK_SECRET must be at least 32 characters"
    AGENT_SERVICE_TOKEN_MISSING = "AGENT_SERVICE_TOKEN is missing or empty"
    AGENT_SERVICE_TOKEN_PLACEHOLDER = "AGENT_SERVICE_TOKEN uses a known placeholder"
    AGENT_SERVICE_TOKEN_SHORT = "AGENT_SERVICE_TOKEN must be at least 32 characters"
    BACKEND_SERVICE_TOKEN_MISSING = "BACKEND_SERVICE_TOKEN is missing or empty"
    BACKEND_SERVICE_TOKEN_PLACEHOLDER = "BACKEND_SERVICE_TOKEN uses a known placeholder"
    BACKEND_SERVICE_TOKEN_SHORT = "BACKEND_SERVICE_TOKEN must be at least 32 characters"
    DATABASE_URL_MISSING = "COMPOSE_DATABASE_URL is missing or empty"
    DATABASE_URL_FORMAT = "COMPOSE_DATABASE_URL is not a valid URL"
    DATABASE_URL_SCHEME = "COMPOSE_DATABASE_URL must use a PostgreSQL scheme"
    DATABASE_URL_PARTS = "COMPOSE_DATABASE_URL must include host, user, and password"
    DATABASE_URL_PASSWORD = "COMPOSE_DATABASE_URL password must match POSTGRES_PASSWORD"
    DATABASE_URL_HOST = "COMPOSE_DATABASE_URL host must be postgres for EC2 Compose"
    LLM_PROVIDER = "LLM_PROVIDER must be ollama for the EC2 model-host deployment"
    OLLAMA_BASE_URL_MISSING = "OLLAMA_BASE_URL is missing or empty"
    OLLAMA_BASE_URL_FORMAT = (
        "OLLAMA_BASE_URL must be an HTTP URL with port 11434 and no credentials, "
        "query, or fragment"
    )
    OLLAMA_BASE_URL_LOCAL = (
        "OLLAMA_BASE_URL must target the separate model host, not localhost or "
        "host.docker.internal"
    )
    OLLAMA_BASE_URL_PUBLIC_IP = (
        "OLLAMA_BASE_URL IP address must be in an RFC1918 private VPC range"
    )
    OLLAMA_BASE_URL_PUBLIC_DNS = (
        "OLLAMA_BASE_URL hostname must be an AWS private DNS name ending in .internal"
    )
    OLLAMA_MODEL_MISSING = "OLLAMA_MODEL is missing or empty"


SECRET_ERRORS = {
    "POSTGRES_PASSWORD": (
        ValidationError.POSTGRES_PASSWORD_MISSING,
        ValidationError.POSTGRES_PASSWORD_PLACEHOLDER,
        ValidationError.POSTGRES_PASSWORD_SHORT,
    ),
    "JWT_SECRET_KEY": (
        ValidationError.JWT_SECRET_KEY_MISSING,
        ValidationError.JWT_SECRET_KEY_PLACEHOLDER,
        ValidationError.JWT_SECRET_KEY_SHORT,
    ),
    "AGENT_WEBHOOK_SECRET": (
        ValidationError.AGENT_WEBHOOK_SECRET_MISSING,
        ValidationError.AGENT_WEBHOOK_SECRET_PLACEHOLDER,
        ValidationError.AGENT_WEBHOOK_SECRET_SHORT,
    ),
    "AGENT_SERVICE_TOKEN": (
        ValidationError.AGENT_SERVICE_TOKEN_MISSING,
        ValidationError.AGENT_SERVICE_TOKEN_PLACEHOLDER,
        ValidationError.AGENT_SERVICE_TOKEN_SHORT,
    ),
    "BACKEND_SERVICE_TOKEN": (
        ValidationError.BACKEND_SERVICE_TOKEN_MISSING,
        ValidationError.BACKEND_SERVICE_TOKEN_PLACEHOLDER,
        ValidationError.BACKEND_SERVICE_TOKEN_SHORT,
    ),
}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def validate_environment(values: dict[str, str]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for key, minimum_length in REQUIRED_SECRET_LENGTHS.items():
        missing_error, placeholder_error, short_error = SECRET_ERRORS[key]
        value = values.get(key, "").strip()
        if not value:
            errors.append(missing_error)
        elif value.lower() in KNOWN_PLACEHOLDERS:
            errors.append(placeholder_error)
        elif len(value) < minimum_length:
            errors.append(short_error)

    database_url = values.get("COMPOSE_DATABASE_URL", "").strip()
    if not database_url:
        errors.append(ValidationError.DATABASE_URL_MISSING)
        return errors

    try:
        parsed = urlsplit(database_url)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        _ = parsed.port
    except ValueError:
        errors.append(ValidationError.DATABASE_URL_FORMAT)
    else:
        if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
            errors.append(ValidationError.DATABASE_URL_SCHEME)
        if not hostname or not username or password is None:
            errors.append(ValidationError.DATABASE_URL_PARTS)
        elif unquote(password) != values.get("POSTGRES_PASSWORD", ""):
            errors.append(ValidationError.DATABASE_URL_PASSWORD)
        if hostname != "postgres":
            errors.append(ValidationError.DATABASE_URL_HOST)

    if values.get("LLM_PROVIDER", "").strip().lower() != "ollama":
        errors.append(ValidationError.LLM_PROVIDER)

    ollama_url = values.get("OLLAMA_BASE_URL", "").strip()
    if not ollama_url:
        errors.append(ValidationError.OLLAMA_BASE_URL_MISSING)
    else:
        parsed_ollama = urlsplit(ollama_url)
        try:
            port = parsed_ollama.port
        except ValueError:
            port = None
        if (
            parsed_ollama.scheme != "http"
            or not parsed_ollama.hostname
            or port != 11434
            or parsed_ollama.username is not None
            or parsed_ollama.password is not None
            or parsed_ollama.path not in {"", "/"}
            or parsed_ollama.query
            or parsed_ollama.fragment
        ):
            errors.append(ValidationError.OLLAMA_BASE_URL_FORMAT)
        elif parsed_ollama.hostname.lower() in {
            "localhost",
            "host.docker.internal",
        }:
            errors.append(ValidationError.OLLAMA_BASE_URL_LOCAL)
        else:
            try:
                address = ipaddress.ip_address(parsed_ollama.hostname)
            except ValueError:
                if not parsed_ollama.hostname.lower().endswith(".internal"):
                    errors.append(ValidationError.OLLAMA_BASE_URL_PUBLIC_DNS)
            else:
                if not any(address in network for network in PRIVATE_VPC_NETWORKS):
                    errors.append(ValidationError.OLLAMA_BASE_URL_PUBLIC_IP)

    if not values.get("OLLAMA_MODEL", "").strip():
        errors.append(ValidationError.OLLAMA_MODEL_MISSING)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()

    if not args.env_file.is_file():
        print(f"ERROR: env file not found: {args.env_file}")
        return 1

    errors = validate_environment(load_env(args.env_file))
    if errors:
        for error in errors:
            print(f"ERROR: {error.value}")
        return 1
    print("EC2 environment validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
