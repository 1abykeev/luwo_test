from typing import Protocol

from app.domain.models import User


class UserRepository(Protocol):
    """Login accounts. Used by auth and to build the Actor for each request."""

    async def get(self, user_id: int) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...
