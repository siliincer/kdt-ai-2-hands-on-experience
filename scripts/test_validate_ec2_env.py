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


def test_database_user_must_match_postgres_user():
    values = _valid_environment()
    values["COMPOSE_DATABASE_URL"] = (
        "postgresql://wrong:database-secret-123456@postgres:5432/financial_agent"
    )

    assert "COMPOSE_DATABASE_URL user must match POSTGRES_USER" in (
        validate_environment(values)
    )


def test_database_port_must_be_5432():
    values = _valid_environment()
    values["COMPOSE_DATABASE_URL"] = (
        "postgresql://app:database-secret-123456@postgres:5433/financial_agent"
    )

    assert "COMPOSE_DATABASE_URL port must be 5432 for EC2 Compose" in (
        validate_environment(values)
    )


def test_invalid_database_port_is_reported():
    values = _valid_environment()
    values["COMPOSE_DATABASE_URL"] = (
        "postgresql://app:database-secret-123456@postgres:not-a-port/financial_agent"
    )

    assert "COMPOSE_DATABASE_URL port must be 5432 for EC2 Compose" in (
        validate_environment(values)
    )


def test_database_name_must_match_postgres_db():
    values = _valid_environment()
    values["COMPOSE_DATABASE_URL"] = (
        "postgresql://app:database-secret-123456@postgres:5432/wrongdb"
    )

    assert "COMPOSE_DATABASE_URL database must match POSTGRES_DB" in (
        validate_environment(values)
    )


def test_external_financial_service_override_is_rejected():
    values = _valid_environment()
    values["COMPOSE_FINANCIAL_CLIENT"] = "http"
    values["COMPOSE_MOCK_FINANCIAL_SERVICE_URL"] = "http://example.invalid:8002"

    assert (
        "COMPOSE_MOCK_FINANCIAL_SERVICE_URL must use mock-financial-service:8002"
        in validate_environment(values)
    )


def test_non_http_financial_client_override_is_rejected():
    values = _valid_environment()
    values["COMPOSE_FINANCIAL_CLIENT"] = "mock"

    assert "COMPOSE_FINANCIAL_CLIENT must be http for EC2 Compose" in (
        validate_environment(values)
    )
