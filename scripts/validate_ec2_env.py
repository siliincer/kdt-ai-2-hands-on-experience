"""Validate EC2 deployment secrets without printing their values."""

from __future__ import annotations

import argparse
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED_SECRET_LENGTHS = {
    "POSTGRES_PASSWORD": 16,
    "JWT_SECRET_KEY": 32,
    "AGENT_WEBHOOK_SECRET": 32,
}
KNOWN_PLACEHOLDERS = {
    "change-me",
    "change-me-agent-webhook",
    "change-me-in-local",
    "changeme",
    "mypassword",
    "password",
}


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
    DATABASE_URL_MISSING = "COMPOSE_DATABASE_URL is missing or empty"
    DATABASE_URL_SCHEME = "COMPOSE_DATABASE_URL must use a PostgreSQL scheme"
    DATABASE_URL_PARTS = "COMPOSE_DATABASE_URL must include host, user, and password"
    DATABASE_URL_PASSWORD = "COMPOSE_DATABASE_URL password must match POSTGRES_PASSWORD"
    DATABASE_URL_HOST = "COMPOSE_DATABASE_URL host must be postgres for EC2 Compose"
    DATABASE_URL_USER = "COMPOSE_DATABASE_URL user must match POSTGRES_USER"
    DATABASE_URL_PORT = "COMPOSE_DATABASE_URL port must be 5432 for EC2 Compose"
    DATABASE_URL_NAME = "COMPOSE_DATABASE_URL database must match POSTGRES_DB"
    FINANCIAL_CLIENT = "COMPOSE_FINANCIAL_CLIENT must be http for EC2 Compose"
    FINANCIAL_SERVICE_URL = (
        "COMPOSE_MOCK_FINANCIAL_SERVICE_URL must use mock-financial-service:8002"
    )


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
    except ValueError:
        errors.append(ValidationError.DATABASE_URL_PARTS)
        return errors
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
        errors.append(ValidationError.DATABASE_URL_SCHEME)
    if not parsed.hostname or not parsed.username or parsed.password is None:
        errors.append(ValidationError.DATABASE_URL_PARTS)
    elif unquote(parsed.password) != values.get("POSTGRES_PASSWORD", ""):
        errors.append(ValidationError.DATABASE_URL_PASSWORD)
    if parsed.hostname != "postgres":
        errors.append(ValidationError.DATABASE_URL_HOST)
    expected_user = values.get("POSTGRES_USER", "app").strip() or "app"
    if unquote(parsed.username or "") != expected_user:
        errors.append(ValidationError.DATABASE_URL_USER)
    try:
        database_port = parsed.port
    except ValueError:
        database_port = None
    if database_port != 5432:
        errors.append(ValidationError.DATABASE_URL_PORT)
    expected_database = (
        values.get("POSTGRES_DB", "financial_agent").strip() or "financial_agent"
    )
    if unquote(parsed.path.removeprefix("/")) != expected_database:
        errors.append(ValidationError.DATABASE_URL_NAME)

    financial_client = values.get("COMPOSE_FINANCIAL_CLIENT", "").strip()
    if financial_client and financial_client != "http":
        errors.append(ValidationError.FINANCIAL_CLIENT)
    financial_url = values.get("COMPOSE_MOCK_FINANCIAL_SERVICE_URL", "").strip()
    if financial_url and financial_url != "http://mock-financial-service:8002":
        errors.append(ValidationError.FINANCIAL_SERVICE_URL)
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
