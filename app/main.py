from fastapi import FastAPI

from app.api import auth_routes
from app.api.errors import install_error_handlers
from app.container import build_app_services
from app.services import Services

DESCRIPTION = """
AI support agent for Luwo: helps teachers and school administrators keep lists of students,
teachers and classes up to date through a chat.

**Try it:** `POST /auth/login` with a demo account, press **Authorize** and paste the token.
"""


def create_app(services: Services | None = None) -> FastAPI:
    app = FastAPI(title="Luwo list-support agent", version="0.1.0", description=DESCRIPTION)
    app.state.services = services or build_app_services()
    install_error_handlers(app)
    app.include_router(auth_routes.router)

    @app.get("/health", tags=["system"], summary="Is the server up?")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
