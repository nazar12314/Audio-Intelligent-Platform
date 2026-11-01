import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from audio_platform.core.logging import LogEvent, configure_logging, get_logger
from tests.conftest import make_settings


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def test_json_log_line_carries_context_and_redacts_secrets(
    restore_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(
        make_settings(log_format="json")
    )  # in the test body: capsys swaps sys.stdout only here
    structlog.contextvars.bind_contextvars(request_id="req-42")

    get_logger("test").info(
        LogEvent.APP_STARTING,
        dsn="postgresql+asyncpg://u:p@db/x",
        note="https://a:b@host/",
    )

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "app.starting"
    assert line["request_id"] == "req-42"
    assert line["level"] == "info"
    assert line["dsn"] == "***"
    assert line["note"] == "https://***@host/"


def test_stdlib_loggers_go_through_the_same_pipeline(
    restore_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_format="json"))
    logging.getLogger("sqlalchemy.engine").warning("pool exhausted")

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (line["event"], line["logger"], line["level"]) == (
        "pool exhausted",
        "sqlalchemy.engine",
        "warning",
    )


SECRET_DSN = "postgresql+asyncpg://app:Sup3rSecret@db:5432/x"


def _fail_with_secret_in_locals_and_message() -> None:
    dsn = SECRET_DSN  # a frame local, like a driver holding its connection string
    raise ConnectionError(f"cannot connect to {dsn}")


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_exception_logs_never_contain_secrets_from_locals_or_messages(
    restore_logging: None, capsys: pytest.CaptureFixture[str], log_format: str
) -> None:
    configure_logging(make_settings(log_format=log_format))

    try:
        _fail_with_secret_in_locals_and_message()
    except ConnectionError:
        get_logger("test").exception(LogEvent.HTTP_UNHANDLED_ERROR)

    out = capsys.readouterr().out
    assert "Sup3rSecret" not in out
    assert "ConnectionError" in out  # the traceback itself is still logged
    assert "_fail_with_secret_in_locals_and_message" in out


def test_stdlib_exception_logs_are_redacted_too(
    restore_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_format="json"))

    try:
        _fail_with_secret_in_locals_and_message()
    except ConnectionError:
        logging.getLogger("sqlalchemy.pool").exception("connection failed")

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "Sup3rSecret" not in json.dumps(line)
    assert line["exception"][0]["exc_type"] == "ConnectionError"
    assert all("locals" not in frame for frame in line["exception"][0]["frames"])
