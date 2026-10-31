import pytest
from pydantic import ValidationError

from audio_platform.core.config import Settings
from tests.conftest import TEST_DSN, make_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AUDIO_POSTGRES__DSN", "AUDIO_STORAGE__BUCKET", "AUDIO_ENV", "AUDIO_API__DOCS_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def test_settings_require_postgres_dsn() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, storage={"bucket": "b-recordings"})
    assert any(err["loc"][0] == "postgres" for err in exc_info.value.errors())


def test_settings_reject_dsn_without_asyncpg_driver() -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        make_settings(postgres={"dsn": "postgresql://u:p@localhost/db"})


def test_blank_secret_in_env_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_POSTGRES__DSN", "")
    monkeypatch.setenv("AUDIO_STORAGE__BUCKET", "b-recordings")
    with pytest.raises(ValidationError, match="postgres"):
        Settings(_env_file=None)


def test_settings_load_nested_groups_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_POSTGRES__DSN", TEST_DSN)
    monkeypatch.setenv("AUDIO_POSTGRES__POOL_SIZE", "3")
    monkeypatch.setenv("AUDIO_STORAGE__BUCKET", "env-recordings")
    monkeypatch.setenv("AUDIO_API__CORS_ORIGINS", '["http://a.test"]')

    settings = Settings(_env_file=None)

    assert settings.postgres.pool_size == 3
    assert settings.storage.bucket == "env-recordings"
    assert settings.api.cors_origins == ["http://a.test"]


def test_dsn_is_not_exposed_in_repr() -> None:
    assert "test:test" not in repr(make_settings())


@pytest.mark.parametrize(
    ("env", "explicit", "expected"),
    [("dev", None, True), ("prod", None, False), ("prod", True, True), ("dev", False, False)],
)
def test_docs_enabled_defaults_to_off_only_in_prod(env: str, explicit: bool | None, expected: bool) -> None:
    assert make_settings(env=env, api={"docs_enabled": explicit}).docs_enabled is expected
