from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIB = 1024 * 1024
_S3_MAX_PARTS = 10_000


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is required inside the container
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = []
    docs_enabled: bool | None = None


class PostgresSettings(BaseModel):
    dsn: SecretStr
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=5, ge=0)
    pool_timeout_s: float = Field(default=5.0, gt=0)
    connect_timeout_s: float = Field(default=5.0, gt=0)
    statement_timeout_ms: int = Field(default=15_000, ge=0)

    @field_validator("dsn")
    @classmethod
    def _require_asyncpg_driver(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError(
                "must be a 'postgresql+asyncpg://user:password@host:port/db' URL"
            )
        return value


class AwsSettings(BaseModel):
    region: str = "eu-central-1"
    endpoint_url: str | None = None  # set only for local S3-compatible storage (RustFS)
    s3_addressing_style: Literal["auto", "virtual", "path"] = "virtual"
    connect_timeout_s: float = Field(default=5.0, gt=0)
    read_timeout_s: float = Field(default=30.0, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)


class StorageSettings(BaseModel):
    bucket: str = Field(min_length=3, max_length=63)
    # Host that clients use for presigned URLs when it differs from aws.endpoint_url
    # (docker compose: the API reaches rustfs:9000, browsers reach localhost:9000).
    public_endpoint_url: str | None = None


class UploadSettings(BaseModel):
    max_size_bytes: int = Field(default=2 * 1024 * _MIB, gt=0)
    part_size_bytes: int = Field(default=16 * _MIB, ge=5 * _MIB, le=5 * 1024 * _MIB)
    # Presigned URLs stop working when the signing credentials expire (1 h sessions).
    url_ttl_s: int = Field(default=900, ge=60, le=3600)
    allowed_content_types: list[str] = [
        "audio/aac",
        "audio/flac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/wave",
        "audio/webm",
        "audio/x-flac",
        "audio/x-m4a",
        "audio/x-wav",
    ]

    @model_validator(mode="after")
    def _fits_s3_part_limit(self) -> UploadSettings:
        if -(-self.max_size_bytes // self.part_size_bytes) > _S3_MAX_PARTS:
            raise ValueError(
                f"max_size_bytes / part_size_bytes exceeds {_S3_MAX_PARTS} parts"
            )
        return self


class MessagingSettings(BaseModel):
    endpoint_url: str | None = None  # SQS-compatible endpoint (ElasticMQ); empty on AWS
    pipeline_events_queue: str = "audio-platform-dev-pipeline-events"
    vad_tasks_queue: str = "audio-platform-dev-vad-tasks"
    wait_time_s: int = Field(default=20, ge=0, le=20)
    # Workers extend this lease while busy, so it only bounds crash recovery time.
    visibility_timeout_s: int = Field(default=60, ge=10, le=43_200)
    # Must stay below the queues' redrive maxReceiveCount: the last attempt records
    # the failure itself instead of leaving the message to the DLQ.
    max_attempts: int = Field(default=3, ge=1, le=10)
    # Upper bound per message: the lease stops being extended and the message is
    # retried, so a hung handler cannot hold it forever.
    handler_timeout_s: int = Field(default=3600, ge=1)
    relay_batch_size: int = Field(default=50, ge=1, le=500)
    relay_interval_s: float = Field(default=1.0, gt=0)
    outbox_retention_days: int = Field(default=7, ge=1)
    outbox_cleanup_interval_s: int = Field(default=3600, ge=1)


class ProcessingSettings(BaseModel):
    max_duration_s: int = Field(default=4 * 3600, gt=0)
    # Decoding and VAD run in a child process that is killed after this long.
    analysis_timeout_s: int = Field(default=1800, ge=1)
    vad_threshold: float = Field(default=0.5, gt=0, lt=1)
    vad_min_speech_ms: int = Field(default=250, ge=0)
    vad_min_silence_ms: int = Field(default=100, ge=0)
    vad_speech_pad_ms: int = Field(default=30, ge=0)


class AuthSettings(BaseModel):
    mode: Literal["dev_header"] = "dev_header"


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
    upload: UploadSettings = UploadSettings()
    auth: AuthSettings = AuthSettings()
    messaging: MessagingSettings = MessagingSettings()
    processing: ProcessingSettings = ProcessingSettings()

    model_config = SettingsConfigDict(
        env_prefix="AUDIO_",
        env_nested_delimiter="__",
        env_file=(_REPO_ROOT / ".env",),
        env_ignore_empty=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _handler_outlives_analysis(self) -> Settings:
        if self.messaging.handler_timeout_s <= self.processing.analysis_timeout_s:
            raise ValueError(
                "messaging.handler_timeout_s must exceed processing.analysis_timeout_s"
            )
        return self

    @model_validator(mode="after")
    def _no_dev_auth_in_prod(self) -> Settings:
        if self.env == "prod" and self.auth.mode == "dev_header":
            raise ValueError(
                "auth.mode 'dev_header' trusts a client header: not for prod"
            )
        return self

    @property
    def docs_enabled(self) -> bool:
        if self.api.docs_enabled is not None:
            return self.api.docs_enabled

        return self.env != "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
