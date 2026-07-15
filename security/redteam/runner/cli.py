"""Command-line entry point for a single local red-team scenario."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import httpx
from pydantic import ValidationError

from security.redteam.config import RedTeamConfig, load_config, load_scenario
from security.redteam.models import Verdict
from security.redteam.runner.attacker import OllamaAttackGenerator
from security.redteam.runner.client import AgentClient, RequestBudget
from security.redteam.runner.managed_agent import ManagedAgentError, managed_agent
from security.redteam.runner.reporter import write_report
from security.redteam.runner.service import SafetyPolicyError, run_scenario

REDTEAM_ROOT = Path(__file__).resolve().parents[1]
EXIT_CODES = {
    Verdict.PASS: 0,
    Verdict.FAIL: 1,
    Verdict.ERROR: 2,
}


def _scenario_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", value):
        raise argparse.ArgumentTypeError(
            "scenario must contain lowercase letters and _"
        )
    return value


def _model_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value):
        raise argparse.ArgumentTypeError("model contains unsupported characters")
    return value


def _with_model(config: RedTeamConfig, model: str | None) -> RedTeamConfig:
    if model is None:
        return config
    return config.model_copy(
        update={
            "adaptive_attack": config.adaptive_attack.model_copy(
                update={"model": model}
            ),
            "safety": config.safety.model_copy(update={"required_ollama_model": model}),
        }
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local red-team scenario")
    parser.add_argument(
        "scenario",
        type=_scenario_name,
        help="scenario name, for example prompt_injection",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REDTEAM_ROOT / "config.example.yaml",
    )
    parser.add_argument("--user-id", default="user_001")
    parser.add_argument("--output-dir", type=Path, default=REDTEAM_ROOT / "reports")
    parser.add_argument(
        "--model",
        type=_model_name,
        help="installed local Ollama model used for both generator and Target",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    scenario_path = REDTEAM_ROOT / "scenarios" / f"{args.scenario}.yaml"
    try:
        config = _with_model(load_config(args.config), args.model)
        scenario = load_scenario(scenario_path)
        budget = RequestBudget(config.execution.max_requests_per_run)
        with managed_agent(config, budget):
            with AgentClient(config.target, budget) as client:
                with OllamaAttackGenerator(
                    config.adaptive_attack,
                    budget,
                ) as attacker:
                    result = run_scenario(
                        config, scenario, client, args.user_id, attacker
                    )
        paths = write_report(result, args.output_dir, config.safety.redact_fields)
    except (
        FileNotFoundError,
        ValidationError,
        ValueError,
        SafetyPolicyError,
        ManagedAgentError,
        httpx.HTTPError,
        RuntimeError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2

    print(f"{result.verdict}: {result.scenario_name}")
    print(f"Reports: {paths[0]} {paths[1]}")
    return EXIT_CODES[result.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
