"""Structured logging: every log line is one JSON object, and the conversation id, user id and request
id that are bound for the current request appear on every line automatically (contextvars).

Our own logs (structlog) and the logs of libraries (the standard `logging` module) go through the same
pipeline, so nothing comes out in a different format."""

import logging
import sys
from typing import TextIO

import structlog


def configure_logging(level: str = "INFO", json: bool = True, stream: TextIO | None = None) -> None:
    shared = [
        structlog.contextvars.merge_contextvars,  # conversation_id, user_id, request_id of this request
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,  # lets tests reconfigure
    )
    renderer = structlog.processors.JSONRenderer(ensure_ascii=False) if json else structlog.dev.ConsoleRenderer()
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,  # for records from the standard logging module
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    # The HTTP client logs one line per call to the model provider; our own "llm" metrics and "chat_request"
    # lines say the same with more detail, so keep libraries at WARNING and above.
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # uvicorn's own access line is replaced by our "http_request" line, which has the route and request id
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def get_logger(name: str = "luwo") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
