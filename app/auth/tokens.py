"""JWT creation and reading. The token carries only the user id: role, school and classes
are always loaded from the database, so nothing inside a token can grant access."""

from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.domain.errors import AuthenticationFailed

ALGORITHM = "HS256"


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def read_token(token: str) -> int:
    try:
        # algorithms is pinned, so a token claiming "alg: none" is rejected; "exp" is checked here too
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AuthenticationFailed("Invalid or expired token") from None
