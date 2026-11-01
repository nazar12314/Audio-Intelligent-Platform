import pytest

from tests.integration.conftest import alembic

pytestmark = pytest.mark.integration


def test_migrations_upgrade_downgrade_upgrade(migrated_dsn: str) -> None:
    alembic("downgrade", "base", dsn=migrated_dsn)
    alembic("upgrade", "head", dsn=migrated_dsn)


def test_models_match_the_migrations(migrated_dsn: str) -> None:
    alembic("check", dsn=migrated_dsn)
