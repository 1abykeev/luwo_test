import hmac

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.agent.agent import Agent
from app.api import analytics_routes, auth_routes, chat_routes
from app.api.errors import install_error_handlers
from app.config import settings
from app.container import build_app
from app.observability import metrics
from app.observability.logging import configure_logging
from app.observability.request_log import InMemoryRequestLogStore, RequestLogStore
from app.services import Services

DESCRIPTION = """
AI support agent for Luwo: helps teachers and school administrators keep lists of students,
teachers and classes up to date through a chat.

**Try it:** `POST /auth/login` with a demo account, press **Authorize** and paste the token.
"""


TAGS = [
    {"name": "auth", "description": "Log in and see who the server thinks you are."},
    {"name": "chat", "description": "Talk to the agent. Everything the mobile app does goes through here."},
    {"name": "analytics", "description": "What people ask the agent and how it went (superadmin)."},
    {"name": "system", "description": "Health checks."},
]


def create_app(
    services: Services | None = None, agent: Agent | None = None, request_log: RequestLogStore | None = None
) -> FastAPI:
    """Pass `services` and `agent` in tests; without them everything is built from the settings."""
    app = FastAPI(title="Luwo list-support agent", version="0.3.0", description=DESCRIPTION, openapi_tags=TAGS)
    if services is None:
        configure_logging(settings.log_level, settings.log_json)  # the real server: JSON logs
        services, agent, request_log = build_app()
    app.state.services = services
    app.state.agent = agent
    app.state.request_log = request_log or InMemoryRequestLogStore()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"], allow_credentials=False,
    )
    app.add_middleware(metrics.MetricsMiddleware)  # outermost: measures everything, even rejected requests
    metrics.install_db_metrics()
    install_error_handlers(app)
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(analytics_routes.router)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics(request: Request) -> Response:
        if settings.metrics_token:
            given = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not hmac.compare_digest(given, settings.metrics_token):
                return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        body, content_type = metrics.render()
        return Response(body, media_type=content_type)

    @app.get("/health", tags=["system"], summary="Is the server up?")
    async def health() -> dict:
        return {"status": "ok"}

    return app


_app: FastAPI | None = None


def __getattr__(name: str):
    """`uvicorn app.main:app` still works, but the application (database pool, model client, JSON logging)
    is only built when the server asks for it, never as a side effect of `import app.main`."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
