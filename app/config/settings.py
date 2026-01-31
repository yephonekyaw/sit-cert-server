from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    ENVIRONMENT: str = "development"
    NAME: str = "<your-app-name>"
    VERSION: str = "<your-app-version>"
    API_PREFIX: str = "<your-api-prefix>"
    WEB_SOCKET_PREFIX: str = "<your-web-sockets-prefix>"
    WEBHOOK_PREFIX: str = "<your-webhook-prefix>"
    """Pydantic v2 doesn't support parsing List[str] from a plain comma-separated string by default anymore."""
    ALLOWED_HOSTS: Union[str, List[str]] = "<your-allowed-host-1,<your-allowed-host-2>>"
    LOG_LEVEL: str = "<your-log-level>"
    COOKIE_DOMAIN: str = "<your-cookie-domain>"

    # Ollama
    OLLAMA_BASE_URL: str = "<your-ollama-base-url>"
    OLLAMA_MODEL: str = "<your-ollama-model>"

    # Tesseract OCR
    TESSERACT_CMD: str = ""
    TESSDATA_PREFIX: str = ""

    # Database
    DATABASE_URL: str = "<your-database-url>"

    # Authentication & Security
    JWT_SECRET_KEY: str = "<your-jwt-secret-key>"
    JWT_ALGORITHM: str = "HS256"

    # MinIO Object Storage
    MINIO_ENDPOINT: str = "<your-minio-endpoint>"
    MINIO_ACCESS_KEY: str = "<your-minio-access-key>"
    MINIO_SECRET_KEY: str = "<your-minio-secret-key>"
    MINIO_BUCKET_NAME: str = "<your-minio-bucket-name>"
    MINIO_SECURE: bool = False

    # CITI Program Automation
    CITI_USERNAME: str = "<your-citi-username>"
    CITI_PASSWORD: str = "<your-citi-password>"
    CITI_HEADLESS: bool = True
    CITI_TIMEOUT: int = 30000

    # Redis & Celery
    REDIS_PASSWORD: str = "<your-redis-password>"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Line Messaging API
    LINE_SIGNING_KEY_PATH: str = "<path-to-your-line-signing-key-json>"
    LINE_KID: str = "<your-line-kid>"
    LINE_CHANNEL_ID: str = "<your-line-channel-id>"
    LINE_CHANNEL_SECRET: str = "<your-line-channel-secret>"

    # SIT brain base url
    SITBRAIN_BASE_URL: str = "<your-sitbrain-base-url>"

    @field_validator("ALLOWED_HOSTS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if not v:
            return []
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
