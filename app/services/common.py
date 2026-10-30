from app.domain.models import Actor, Role
from app.repositories.interfaces import UnitOfWork


async def school_names(uow: UnitOfWork, actor: Actor) -> dict[int, str]:
    """Only the schools this person may know about."""
    if actor.role == Role.SUPERADMIN:
        return {s.id: s.name for s in await uow.schools.list_all()}
    school = await uow.schools.get(actor.school_id)
    return {school.id: school.name} if school else {}
