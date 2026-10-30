import asyncio

from app.domain.errors import AuthenticationFailed
from app.domain.models import User
from app.repositories.interfaces import UnitOfWorkFactory

from .passwords import hash_password, verify_password
from .tokens import create_token

# Checked when the email is unknown, so "no such user" takes as long as "wrong password".
_DUMMY_HASH = hash_password("not-a-real-password")


class AuthService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow = uow_factory

    async def login(self, email: str, password: str) -> tuple[str, User]:
        async with self._uow() as uow:
            user = await uow.users.get_by_email(email.strip().lower())

        password_hash = user.password_hash if user and user.password_hash else _DUMMY_HASH
        # bcrypt is slow on purpose (about 0.2 s); in a thread it cannot freeze every other request
        password_ok = await asyncio.to_thread(verify_password, password, password_hash)
        # One message for every failure: unknown email, wrong password, removed account.
        if not (user and user.password_hash and password_ok and user.is_active):
            raise AuthenticationFailed("Wrong email or password")
        return create_token(user.id), user
