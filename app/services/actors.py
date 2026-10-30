from dataclasses import dataclass

from app.domain.errors import PermissionDenied
from app.domain.models import Actor, Role
from app.repositories.interfaces import UnitOfWorkFactory


@dataclass(frozen=True)
class Profile:
    user_id: int
    full_name: str
    role: Role
    school_name: str | None
    class_names: list[str]  # classes a teacher leads


class ActorService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow = uow_factory

    async def load(self, user_id: int) -> Actor:
        """Build the Actor from the database. Called on every request: role, school and
        classes are never taken from the token or from chat text."""
        async with self._uow() as uow:
            user = await uow.users.get(user_id)
            if user is None or not user.is_active:
                raise PermissionDenied("This account is not active")
            class_ids: frozenset[int] = frozenset()
            if user.role == Role.TEACHER:
                class_ids = frozenset(c.id for c in await uow.classes.list_led_by(user.id))
            return Actor(
                user_id=user.id,
                full_name=user.full_name,
                role=user.role,
                school_id=user.school_id,
                class_ids=class_ids,
            )

    async def profile(self, actor: Actor) -> Profile:
        async with self._uow() as uow:
            school = await uow.schools.get(actor.school_id) if actor.school_id else None
            classes = [await uow.classes.get(class_id) for class_id in actor.class_ids]
            class_names = sorted(c.name for c in classes if c)
            return Profile(actor.user_id, actor.full_name, actor.role, school.name if school else None, class_names)
