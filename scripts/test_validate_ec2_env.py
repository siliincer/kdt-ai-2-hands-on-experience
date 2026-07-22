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
        "LLM_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://10.0.1.20:11434",
        "OLLAMA_MODEL": "exaone3.5:7.8b",
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


def test_ollama_deployment_values_are_required():
    values = _valid_environment()
    values["LLM_PROVIDER"] = "openai"
    values["OLLAMA_BASE_URL"] = ""
    values["OLLAMA_MODEL"] = ""

    errors = validate_environment(values)

    assert "LLM_PROVIDER must be ollama for the EC2 model-host deployment" in errors
    assert "OLLAMA_BASE_URL is missing or empty" in errors
    assert "OLLAMA_MODEL is missing or empty" in errors


def test_ollama_url_must_target_private_model_host():
    for invalid_url in (
        "http://localhost:11434",
        "http://host.docker.internal:11434",
        "http://203.0.113.10:11434",
        "http://ollama.example.com:11434",
        "https://10.0.1.20:11434",
        "http://user:password@10.0.1.20:11434",
        "http://10.0.1.20:11434/api",
    ):
        values = _valid_environment()
        values["OLLAMA_BASE_URL"] = invalid_url

        assert validate_environment(values), invalid_url


def test_private_dns_model_host_is_allowed():
    values = _valid_environment()
    values["OLLAMA_BASE_URL"] = (
        "http://ip-10-0-1-20.ap-northeast-2.compute.internal:11434"
    )

    assert validate_environment(values) == []
