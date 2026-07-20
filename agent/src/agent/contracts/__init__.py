"""Agent가 외부 시스템과 주고받는 데이터 계약."""

from agent.contracts.backend import AgentToolEnvelope, AgentWebhookRequest

__all__ = ["AgentToolEnvelope", "AgentWebhookRequest"]
