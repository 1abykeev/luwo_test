from fastapi import FastAPI

from app.agent.agent import Agent
from app.api import auth_routes, chat_routes
from app.api.errors import install_error_handlers
from app.container import build_app
from app.services import Services

DESCRIPTION = """
AI support agent for Luwo: helps teachers and school administrators keep lists of students,
teachers and classes up to date through a chat.

**Try it:** `POST /auth/login` with a demo account, press **Authorize** and paste the token.
"""


TAGS = [
    {"name": "auth", "description": "Log in and see who the server thinks you are."},
    {"name": "chat", "description": "Talk to the agent. Everything the mobile app does goes through here."},
    {"name": "system", "description": "Health checks."},
]


def create_app(services: Services | None = None, agent: Agent | None = None) -> FastAPI:
    """Pass `services` and `agent` in tests; without them everything is built from the settings."""
    app = FastAPI(title="Luwo list-support agent", version="0.2.0", description=DESCRIPTION, openapi_tags=TAGS)
    if services is None:
        services, agent = build_app()
    app.state.services = services
    app.state.agent = agent
    install_error_handlers(app)
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)

    @app.get("/health", tags=["system"], summary="Is the server up?")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
