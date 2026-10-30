"""The permission table from the task, as code. Every rule lives here and nowhere else.

The agent never calls these: services do, so a wrong decision by the model cannot
widen access."""

from app.domain.errors import PermissionDenied
from app.domain.models import Actor, Role, SchoolClass, Scope, Student


def scope_for(actor: Actor) -> Scope:
    """What a search may look at."""
    if actor.role == Role.TEACHER:
        return Scope(school_id=actor.school_id, class_ids=actor.class_ids)
    if actor.role == Role.SCHOOL_ADMIN:
        return Scope(school_id=actor.school_id)
    return Scope()


def can_access_class(actor: Actor, cls: SchoolClass) -> bool:
    if actor.role == Role.TEACHER:
        return cls.id in actor.class_ids
    if actor.role == Role.SCHOOL_ADMIN:
        return cls.school_id == actor.school_id
    return True


def can_access_student(actor: Actor, student: Student) -> bool:
    if actor.role == Role.TEACHER:
        return student.class_id in actor.class_ids
    if actor.role == Role.SCHOOL_ADMIN:
        return student.school_id == actor.school_id
    return True


def require_teacher_management(actor: Actor) -> None:
    if actor.role == Role.TEACHER:
        raise PermissionDenied("Only school administrators and superadmins can manage teachers")


def require_superadmin(actor: Actor, what: str) -> None:
    if actor.role != Role.SUPERADMIN:
        raise PermissionDenied(f"Only a superadmin can {what}")
