import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from enum import StrEnum
from typing import Any

import structlog

from audio_platform.core.config import Settings


class LogEvent(StrEnum):
    """
    Stable event codes. Log business and lifecycle events with these, never with
    free text.
    """

    APP_STARTING = "app.starting"
    APP_STOPPED = "app.stopped"
    CONFIG_INVALID = "config.invalid"
    HTTP_REQUEST_COMPLETED = "http.request.completed"
    HTTP_UNHANDLED_ERROR = "http.unhandled_error"
    HEALTH_CHECK_FAILED = "health.check_failed"
    RECORDING_REGISTERED = "recordings.recording.registered"
    RECORDING_UPLOADED = "recordings.recording.uploaded"
    RECORDING_UPLOAD_FAILED = "recordings.recording.upload_failed"
    RECORDING_ABORTED = "recordings.recording.aborted"
    RECORDING_OBJECT_CLEANUP_FAILED = "recordings.object.cleanup_failed"
    OUTBOX_RELAY_FAILED = "messaging.outbox.relay_failed"
    CONSUMER_RECEIVE_FAILED = "messaging.consumer.receive_failed"
    MESSAGE_INVALID = "messaging.message.invalid"
    MESSAGE_HANDLING_FAILED = "messaging.message.handling_failed"
    MESSAGE_HANDLING_TIMED_OUT = "messaging.message.handling_timed_out"
    OUTBOX_PURGED = "messaging.outbox.purged"
    OUTBOX_ROW_UNPUBLISHABLE = "messaging.outbox.row_unpublishable"
    OUTBOX_CLEANUP_FAILED = "messaging.outbox.cleanup_failed"
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"
    PROCESSING_JOB_CREATED = "processing.job.created"
    PROCESSING_JOB_COMPLETED = "processing.job.completed"
    PROCESSING_JOB_FAILED = "processing.job.failed"
    VAD_STARTED = "processing.vad.started"
    VAD_COMPLETED = "processing.vad.completed"
    VAD_FAILED = "processing.vad.failed"
    VAD_RETRY_SCHEDULED = "processing.vad.retry_scheduled"


_SENSITIVE_KEY = re.compile(
    r"pass(word)?|secret|token|authorization|cookie|api[_-]?key|dsn|credential",
    re.IGNORECASE,
)
_URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<userinfo>[^/@\s]+)@", re.IGNORECASE
)
_MASK = "***"


def redact(value: Any, key: str | None = None) -> Any:
    """
    Mask secrets in a log value: sensitive keys, nested mappings, and credentials
    in URLs.
    """
    if key is not None and _SENSITIVE_KEY.search(key):
        return _MASK
    if isinstance(value, Mapping):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact(v) for v in value)
    if isinstance(value, str):
        return _URL_CREDENTIALS.sub(rf"\g<scheme>{_MASK}@", value)
    return value


def _redact_processor(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    return {k: (v if k == "event" else redact(v, k)) for k, v in event_dict.items()}


def configure_logging(settings: Settings) -> None:
    """
    Route both structlog and stdlib logging (uvicorn, sqlalchemy) through one
    JSON/console renderer.
    """
    # Exceptions are rendered without frame locals (structlog's defaults include
    # them, which would log DSNs and keys held in variables) and before redaction,
    # so credentials in exception messages are masked.
    exception_renderer: structlog.types.Processor
    renderer: structlog.types.Processor
    if settings.log_format == "json":
        exception_renderer = structlog.processors.ExceptionRenderer(
            structlog.tracebacks.ExceptionDictTransformer(show_locals=False)
        )
        renderer = structlog.processors.JSONRenderer()
    else:
        exception_renderer = structlog.processors.format_exc_info
        renderer = structlog.dev.ConsoleRenderer()

    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        exception_renderer,
        _redact_processor,
    ]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)

    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True

    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
