"""Times every SQL statement (the `luwo_db_query_duration_seconds` metric).

SQLAlchemy-specific, so it lives with the database code and not in `app/observability`: the agent and the
metrics module must be importable without any database library (see tests/test_layers.py)."""

import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.observability.metrics import db_query_seconds

_db_hooks_installed = False


def _operation(statement: str) -> str:
    word = statement.lstrip()[:12].split(" ", 1)[0].upper()
    return word if word in {"SELECT", "INSERT", "UPDATE", "DELETE"} else "OTHER"


def install_db_metrics() -> None:
    global _db_hooks_installed
    if _db_hooks_installed:
        return
    _db_hooks_installed = True

    @event.listens_for(Engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("luwo_query_started", []).append(time.perf_counter())

    @event.listens_for(Engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, executemany):
        started = conn.info.get("luwo_query_started")
        if started:
            db_query_seconds.labels(_operation(statement)).observe(time.perf_counter() - started.pop())

    @event.listens_for(Engine, "handle_error")
    def failed(exception_context):
        started = exception_context.connection.info.get("luwo_query_started") if exception_context.connection else None
        if started:
            started.pop()
