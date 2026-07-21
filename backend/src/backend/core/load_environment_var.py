from dotenv import find_dotenv
from pydantic import AnyUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Configuration
    APP_ENV: str = Field(default="local", description="애플리케이션 실행 환경")
    LOG_LEVEL: str = Field(default="INFO", description="로그 출력 레벨")

    # Database Configuration
    POSTGRES_DB: str = Field(default="financial_agent")
    POSTGRES_USER: str = Field(default="myuser")
    POSTGRES_PASSWORD: SecretStr = SecretStr("mypassword")
    DATABASE_URL: str = Field(
        default="postgresql://myuser:mypassword@postgres:5432/financial_agent",
        description="SQLAlchemy 비동기 연결 URL",
    )

    # Cache Configuration
    REDIS_CACHE_URL: AnyUrl = AnyUrl("redis://redis:6379/0")
    REDIS_STREAM_URL: AnyUrl = AnyUrl("redis://redis:6380/0")
    # redis://[호스트이름]:[포트번호]/[데이터베이스_번호]

    # mock-financial-service(계정계/정보계) 연동 Configuration
    FINANCIAL_CLIENT: str = Field(
        default="mock",
        description="계정계 데이터 소스: mock(내장 픽스처) | http(실서비스 호출)",
    )
    MOCK_FINANCIAL_SERVICE_URL: str = Field(
        default="http://localhost:8002",
        description="mock-financial-service base URL (FINANCIAL_CLIENT=http일 때 사용)",
    )
    FINANCIAL_ANALYTICS_KEY: SecretStr = Field(
        default=SecretStr("analytics-demo-key"),
        description="정보계(analytics) 읽기 API 키 (X-Analytics-Key 헤더)",
    )
    # (D5) FINANCIAL_DEMO_* 3종(fallback account_id·데모 수취처) 삭제 —
    # 수취인은 recipient_candidates / 실행 이력 참조로 대체됨.

    # Auth Configuration
    JWT_SECRET_KEY: SecretStr = SecretStr("change-me-in-local")
    JWT_ALGORITHM: str = Field(default="HS256")
    # HMAC using SHA-256
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    SSE_TICKET_TTL_SECONDS: int = Field(
        default=120,
        description="SSE 연결용 일회성 티켓 유효 시간(초)",
    )

    # Agent Stream (Redis Streams 브릿지) Configuration
    AGENT_STREAM_BLOCK_MS: int = Field(
        default=15000,
        description="XREAD BLOCK 대기 시간(ms). 타임아웃마다 keep-alive를 보낸다.",
    )
    AGENT_STREAM_MAXLEN: int = Field(
        default=1000,
        description="XADD 시 스트림 최대 길이(근사 MAXLEN ~). 재연결 리플레이 상한.",
    )
    AGENT_STREAM_TTL_SECONDS: int = Field(
        default=3600,
        description="agent:stream:{chat_session_id} 키의 TTL(초).",
    )
    AGENT_WEBHOOK_SECRET: SecretStr = Field(
        default=SecretStr("change-me-agent-webhook"),
        description="Agent → 웹훅(POST /webhooks/agent) 호출 시 공유 시크릿.",
    )
    AGENT_SERVICE_TOKEN: SecretStr = Field(
        default=SecretStr("change-me-agent-service-token"),
        description=(
            "Agent → Backend Tool API(/api/v1/agent-tools/*) 호출 시 서비스 인증 "
            "Bearer 토큰. Webhook Secret과 반드시 분리한다(서비스 간 인증 전용)."
        ),
    )
    AGENT_SERVICE_URL: str = Field(
        default="http://localhost:8001",
        description=(
            "Backend → Agent 내부 실행 API(/internal/v1/executions*) base URL. "
            "실 Agent 연동(agent_client) 시 실행 시작·재개 요청에 사용한다."
        ),
    )
    BACKEND_SERVICE_TOKEN: SecretStr = Field(
        default=SecretStr("change-me-backend-service-token"),
        description=(
            "Backend → Agent 내부 실행 API 호출 시 서비스 인증 Bearer 토큰. "
            "Agent 가 os.getenv('BACKEND_SERVICE_TOKEN') 로 검증하므로 값을 공유한다. "
            "방향이 반대인 AGENT_SERVICE_TOKEN(Agent→BE)과 반드시 분리한다."
        ),
    )
    EXECUTION_CONTEXT_TTL_SECONDS: int = Field(
        default=1800,
        description="Execution Context 발급 시 기본 유효시간(초). 만료 후 재발급 필요.",
    )
    DEFAULT_EXECUTION_TIMEZONE: str = Field(
        default="Asia/Seoul",
        description="Execution Context 기본 타임존. 거래 합계 등 기간 경계 변환 기준.",
    )
    SSE_TICKET_RATE_LIMIT: str = Field(
        default="30/minute",
        description="GET /sse/ticket slowapi 제한 (IP당). 인증·DB 세션 생성 게이트.",
    )
    SSE_CONNECT_RATE_LIMIT: str = Field(
        default="60/minute",
        description="GET /sse/connect slowapi 제한 (IP당). 재연결에 여유를 둔다.",
    )

    # .env 파일 로드 설정 (pydantic v2 방식)
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,  # 대소문자 구분 없이 환경변수 로드
    )


# 전역 설정 객체 생성
settings = Settings()

print("환경 변수 로드 완료")  # TODO(BE): loguru 로거로 교체
