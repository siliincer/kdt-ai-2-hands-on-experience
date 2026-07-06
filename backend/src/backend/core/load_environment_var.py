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
        default="postgresql+asyncpg://myuser:mypassword@postgres:5432/financial_agent",
        description="SQLAlchemy 비동기 연결 URL",
    )

    # Cache Configuration
    REDIS_URL: AnyUrl = AnyUrl("redis://redis:6379/0")
    # redis://[호스트이름]:[포트번호]/[데이터베이스_번호]

    # Agent Service Configuration
    AGENT_SERVICE_URL: str = Field(
        default="http://agent-service:8001",
        description="에이전트 서비스 주소 (docker compose 네트워크 alias 기준)",
    )

    # Auth Configuration
    JWT_SECRET_KEY: SecretStr = SecretStr("change-me-in-local")
    JWT_ALGORITHM: str = Field(default="HS256")
    # HMAC using SHA-256
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)

    # .env 파일 로드 설정 (pydantic v2 방식)
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# 전역 설정 객체 생성
settings = Settings()

print("환경 변수 로드 완료")  # TODO: loguru 로거로 교체
