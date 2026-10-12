import json
from pathlib import Path
from typing import Any, Dict, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = (_BACKEND_DIR / "profitguard_dev.db").as_posix()
_DEFAULT_DB_URL = f"sqlite+pysqlite:///{_DEFAULT_DB_PATH}"


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    APP_NAME: str = "ProfitGuard AI"
    API_V1_STR: str = "/api/v1"

    # Database URLs
    # Defaults to SQLite for local lightweight testing / unit tests, overridden by env var for PostgreSQL
    DATABASE_URL: str = _DEFAULT_DB_URL
    MIGRATION_DATABASE_URL: str = _DEFAULT_DB_URL

    # Authentication
    JWT_SECRET_KEY: str = "dev-secret-key-do-not-use-in-production-min-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AES-256-GCM Encryption Keys
    # Mapping of version -> 32-byte (64 hex characters) key
    ACTIVE_ENCRYPTION_KEY_VERSION: str = "v1"
    ENCRYPTION_KEYS: Dict[str, str] = Field(
        default_factory=lambda: {
            "v1": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        }
    )

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Redis URL (placeholder for workers)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Shopify Integration Settings
    SHOPIFY_API_VERSION: str = "2024-01"
    SHOPIFY_WEBHOOK_SECRET: str | None = None
    SHOPIFY_CLIENT_ID: str | None = None
    SHOPIFY_CLIENT_SECRET: str | None = None

    # ML Inference & Decisioning Settings (Phase 4C)
    # Operating Modes: SHADOW | LIVE_ASSISTED | DISABLED
    ML_OPERATING_MODE: str = "SHADOW"
    # Model-Readiness Gate: synthetic-trained model cannot trigger autonomous cancellations
    ML_MODEL_APPROVED_FOR_CONSEQUENTIAL_ACTIONS: bool = False
    ML_DECISION_POLICY_VERSION: str = "v1.1-ml-assisted"

    # Meta WhatsApp Business Cloud API Settings
    WHATSAPP_API_VERSION: str = "v20.0"
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: str | None = None
    WHATSAPP_ACCESS_TOKEN: str | None = None
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str | None = "profitguard_whatsapp_verify_token_default"
    WHATSAPP_APP_SECRET: str | None = None
    # Operating Modes: MOCK | META_TEST | LIVE
    WHATSAPP_OPERATING_MODE: str = "MOCK"
    WHATSAPP_REQUEST_TIMEOUT_SECONDS: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ENCRYPTION_KEYS", mode="before")
    @classmethod
    def parse_encryption_keys(cls, v: Any) -> Dict[str, str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                # If single hex string provided, default to v1
                return {"v1": v}
        if isinstance(v, dict):
            return v
        return {"v1": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()
