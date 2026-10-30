from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agent.agent import Agent
from app.auth.tokens import read_token
from app.domain.errors import AuthenticationFailed, PermissionDenied
from app.domain.models import Actor
from app.services import Services

bearer = HTTPBearer(auto_error=False, description="Token from POST /auth/login")


def get_services(request: Request) -> Services:
    return request.app.state.services


async def current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    services: Services = Depends(get_services),
) -> Actor:
    """Who is calling. The token only names the user; role, school and classes are
    loaded from the database on every request."""
    if credentials is None:
        raise AuthenticationFailed("Missing token")
    try:
        return await services.actors.load(read_token(credentials.credentials))
    except PermissionDenied:  # the account was removed after the token was issued
        raise AuthenticationFailed("This account is not active") from None


def get_agent(request: Request) -> Agent:
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="The agent is not configured")
    return agent
