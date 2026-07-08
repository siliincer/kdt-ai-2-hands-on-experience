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

    # .env 파일 로드 설정 (pydantic v2 방식)
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,  # 대소문자 구분 없이 환경변수 로드
    )


# 전역 설정 객체 생성
settings = Settings()

print("환경 변수 로드 완료")  # TODO: loguru 로거로 교체
