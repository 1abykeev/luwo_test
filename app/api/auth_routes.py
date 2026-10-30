from fastapi import APIRouter, Depends

from app.api.deps import current_actor, get_services
from app.api.schemas import ErrorResponse, LoginRequest, ProfileResponse, TokenResponse
from app.domain.models import Actor
from app.services import Services

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    summary="Log in with email and password",
    description="Returns a JWT. Send it as `Authorization: Bearer <token>` on every other request. "
    "Demo accounts and their password are listed in the README.",
    responses={401: {"model": ErrorResponse, "description": "Wrong email or password"}},
)
async def login(body: LoginRequest, services: Services = Depends(get_services)) -> TokenResponse:
    token, user = await services.auth.login(body.email, body.password)
    actor = await services.actors.load(user.id)
    profile = await services.actors.profile(actor)
    return TokenResponse(access_token=token, user=ProfileResponse(**profile.__dict__))


@router.get(
    "/me",
    summary="Who am I?",
    description="The role, school and classes as the server sees them (loaded from the database, "
    "never from the token).",
    responses={401: {"model": ErrorResponse}},
)
async def me(actor: Actor = Depends(current_actor), services: Services = Depends(get_services)) -> ProfileResponse:
    return ProfileResponse(**(await services.actors.profile(actor)).__dict__)
