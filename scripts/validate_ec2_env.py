"""Validate EC2 deployment secrets without printing their values."""

from __future__ import annotations

import argparse
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


def validate_environment(values: dict[str, str]) -> list[str]:
    errors = []
    for key, minimum_length in REQUIRED_SECRET_LENGTHS.items():
        value = values.get(key, "").strip()
        if not value:
            errors.append(f"{key} is missing or empty")
        elif value.lower() in KNOWN_PLACEHOLDERS:
            errors.append(f"{key} uses a known placeholder")
        elif len(value) < minimum_length:
            errors.append(f"{key} must be at least {minimum_length} characters")

    database_url = values.get("COMPOSE_DATABASE_URL", "").strip()
    if not database_url:
        errors.append("COMPOSE_DATABASE_URL is missing or empty")
        return errors

    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
        errors.append("COMPOSE_DATABASE_URL must use a PostgreSQL scheme")
    if not parsed.hostname or not parsed.username or parsed.password is None:
        errors.append("COMPOSE_DATABASE_URL must include host, user, and password")
    elif unquote(parsed.password) != values.get("POSTGRES_PASSWORD", ""):
        errors.append("COMPOSE_DATABASE_URL password must match POSTGRES_PASSWORD")
    if parsed.hostname != "postgres":
        errors.append("COMPOSE_DATABASE_URL host must be postgres for EC2 Compose")
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
            print(f"ERROR: {error}")
        return 1
    print("EC2 environment validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
