"""Application settings: the only module that reads the environment.

Env vars follow ``AUDIO_<GROUP>__<FIELD>``, e.g. ``AUDIO_POSTGRES__DSN``.
AWS credentials are deliberately absent: the S3 client uses the default AWS credential chain.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is required inside the container
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = []
    docs_enabled: bool | None = None  # None: enabled everywhere except prod


class PostgresSettings(BaseModel):
    dsn: SecretStr  # REQUIRED; contains the DB password
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=5, ge=0)
    pool_timeout_s: float = Field(default=5.0, gt=0)
    connect_timeout_s: float = Field(default=5.0, gt=0)
    statement_timeout_ms: int = Field(default=15_000, ge=0)

    @field_validator("dsn")
    @classmethod
    def _require_asyncpg_driver(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("must be a 'postgresql+asyncpg://user:password@host:port/db' URL")
        return value


class AwsSettings(BaseModel):
    region: str = "eu-central-1"
    endpoint_url: str | None = None  # set only for local S3-compatible storage (RustFS)
    s3_addressing_style: Literal["auto", "virtual", "path"] = "auto"
    connect_timeout_s: float = Field(default=5.0, gt=0)
    read_timeout_s: float = Field(default=30.0, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)


class StorageSettings(BaseModel):
    bucket: str = Field(min_length=3, max_length=63)  # REQUIRED; audio recordings bucket


class Settings(BaseSettings):
    env: Literal["dev", "test", "prod"] = "dev"
    service_name: str = "audio-platform"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    health_check_timeout_s: float = Field(default=2.0, gt=0)

    api: ApiSettings = ApiSettings()
    postgres: PostgresSettings
    aws: AwsSettings = AwsSettings()
    storage: StorageSettings

    model_config = SettingsConfigDict(
        env_prefix="AUDIO_",
        env_nested_delimiter="__",
        env_file=(_REPO_ROOT / ".env",),
        env_ignore_empty=True,  # a blank value means "unset": blank secrets fail as missing
        extra="ignore",
    )

    @property
    def docs_enabled(self) -> bool:
        if self.api.docs_enabled is not None:
            return self.api.docs_enabled
        return self.env != "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required fields come from the environment
