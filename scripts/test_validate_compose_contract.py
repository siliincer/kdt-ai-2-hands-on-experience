from pathlib import Path

import yaml

from scripts.validate_compose_contract import validate_contract

ROOT = Path(__file__).resolve().parents[1]


def _valid_config() -> dict:
    return {
        "services": {
            "backend": {
                "environment": {
                    "APP_ENV": "prod",
                    "FINANCIAL_CLIENT": "http",
                    "MOCK_FINANCIAL_SERVICE_URL": (
                        "http://mock-financial-service:8002"
                    ),
                },
                "depends_on": {
                    "mock-financial-service": {"condition": "service_healthy"}
                },
            },
            "mock-financial-service": {
                "working_dir": "/data",
                "volumes": [{"type": "volume", "target": "/data"}],
            },
            "agent": {
                "environment": {"BANK_CLIENT": "local"},
            },
            "nginx": {
                "read_only": True,
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "tmpfs": ["/tmp:mode=1777,size=64m"],
            },
        }
    }


def test_accepts_financial_http_and_persistent_ledger_contract():
    assert validate_contract(_valid_config()) == []


def test_rejects_disabled_financial_http_integration():
    config = _valid_config()
    config["services"]["backend"]["environment"]["FINANCIAL_CLIENT"] = "mock"

    assert validate_contract(config) == ["backend FINANCIAL_CLIENT must be http"]


def test_rejects_development_logging_in_deployment():
    config = _valid_config()
    config["services"]["backend"]["environment"]["APP_ENV"] = "local"

    assert validate_contract(config) == [
        "backend APP_ENV must disable development logging"
    ]


def test_rejects_ephemeral_financial_ledger():
    config = _valid_config()
    config["services"]["mock-financial-service"]["volumes"] = []

    assert validate_contract(config) == [
        "mock-financial-service must persist /data in a volume"
    ]


def test_rejects_agent_http_ledger_until_api_contract_is_compatible():
    config = _valid_config()
    config["services"]["agent"]["environment"]["BANK_CLIENT"] = "http"

    assert validate_contract(config) == [
        "agent BANK_CLIENT must remain local until APIs are compatible"
    ]


def test_rejects_unsupported_agent_financial_service_url():
    config = _valid_config()
    config["services"]["agent"]["environment"]["MOCK_FINANCIAL_SERVICE_URL"] = (
        "http://mock-financial-service:8002"
    )

    assert validate_contract(config) == [
        "agent must not claim unsupported mock-financial-service integration"
    ]


def test_rejects_agent_backend_startup_dependency():
    config = _valid_config()
    config["services"]["agent"]["depends_on"] = {
        "backend": {"condition": "service_healthy"}
    }

    assert validate_contract(config) == [
        "agent must remain independent from backend startup"
    ]


def test_rejects_nginx_without_runtime_hardening():
    config = _valid_config()
    config["services"]["nginx"] = {
        "read_only": False,
        "security_opt": [],
        "cap_drop": [],
        "tmpfs": [],
    }

    assert validate_contract(config) == [
        "nginx root filesystem must be read-only",
        "nginx must enable no-new-privileges",
        "nginx must drop all Linux capabilities",
        "nginx /tmp tmpfs size must be exactly 64m",
    ]


def test_rejects_invalid_nginx_tmpfs_sizes():
    for mount in (
        "/tmp:mode=1777",
        "/tmp:mode=1777,size=0",
        "/tmp:mode=1777,size=garbage",
        "/tmp:mode=1777,size=128m",
    ):
        config = _valid_config()
        config["services"]["nginx"]["tmpfs"] = [mount]

        assert validate_contract(config) == [
            "nginx /tmp tmpfs size must be exactly 64m"
        ]


def test_prod_compatibility_override_cannot_publish_or_restart_services():
    config = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())
    services = config["services"]

    assert "ports" not in services["nginx"]
    assert all("restart" not in service for service in services.values())
