from scripts.validate_ec2_env import validate_environment


def _valid_environment() -> dict[str, str]:
    password = "database-secret-123456"
    return {
        "POSTGRES_PASSWORD": password,
        "COMPOSE_DATABASE_URL": (
            f"postgresql://app:{password}@postgres:5432/financial_agent"
        ),
        "JWT_SECRET_KEY": "jwt-secret-" + "a" * 32,
        "AGENT_WEBHOOK_SECRET": "webhook-secret-" + "b" * 32,
    }


def test_valid_environment_passes():
    assert validate_environment(_valid_environment()) == []


def test_known_placeholders_are_rejected():
    values = _valid_environment()
    values["POSTGRES_PASSWORD"] = "change-me-in-local"
    values["JWT_SECRET_KEY"] = "change-me-in-local"
    values["AGENT_WEBHOOK_SECRET"] = "change-me-agent-webhook"
    values["COMPOSE_DATABASE_URL"] = (
        "postgresql://app:change-me-in-local@postgres:5432/financial_agent"
    )

    errors = validate_environment(values)

    assert any("POSTGRES_PASSWORD uses a known placeholder" in item for item in errors)
    assert any("JWT_SECRET_KEY uses a known placeholder" in item for item in errors)
    assert any(
        "AGENT_WEBHOOK_SECRET uses a known placeholder" in item for item in errors
    )


def test_database_password_must_match():
    values = _valid_environment()
    values["COMPOSE_DATABASE_URL"] = (
        "postgresql://app:different-secret-123456@postgres:5432/financial_agent"
    )

    assert "COMPOSE_DATABASE_URL password must match POSTGRES_PASSWORD" in (
        validate_environment(values)
    )
