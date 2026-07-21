"""Backend HTTP Client 공통 설정."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class BackendClientConfig(BaseModel):
    """Agent가 Backend에 요청을 보낼 때 사용하는 공통 설정."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    agent_service_token: SecretStr
    agent_webhook_secret: SecretStr
    connect_timeout_seconds: float = Field(default=3.0, gt=0)
    request_timeout_seconds: float = Field(default=10.0, gt=0)
    retry_backoff_seconds: float = Field(default=0.1, ge=0)
    max_retries: int = Field(default=1, ge=0, le=1)
