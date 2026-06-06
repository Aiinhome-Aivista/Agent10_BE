from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings
from pydantic import validator
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Q2P-Platform"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # MySQL
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_DB: str = "q2p_db"
    MYSQL_USER: str = "q2p_user"
    MYSQL_PASSWORD: str

    # ChromaDB (local)
    CHROMA_PERSIST_DIR: str = "./chroma_store"
    CHROMA_COLLECTION_NAME: str = "q2p_knowledge"

    # ArangoDB
    ARANGODB_HOST: str = "localhost"
    ARANGODB_PORT: int = 8529
    ARANGODB_DB: str = "q2p_graph"
    ARANGODB_USER: str = "root"
    ARANGODB_PASSWORD: str = "arangopassword"

    # LLM (Local Mistral)
    LLM_BASE_URL: str = "http://localhost/api/generate"
    LLM_MODEL: str = "mistral:latest"
    LLM_TIMEOUT: int = 120
    LLM_MAX_RETRY: int = 3

    # SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_FROM_EMAIL: str = "noreply@q2p.com"

    # OTP
    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_RETRY: int = 3
    OTP_MAX_RESEND: int = 5

    # Escalation
    ESCALATION_INTERVAL_MINUTES: int = 10
    ESCALATION_MAX_LEVEL: int = 3

    # File Storage
    FILE_UPLOAD_PATH: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 20

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_PATH: str = "./logs"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+asyncmy://{quote_plus(self.MYSQL_USER)}:{quote_plus(self.MYSQL_PASSWORD)}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.MYSQL_USER)}:{quote_plus(self.MYSQL_PASSWORD)}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
        )

    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
