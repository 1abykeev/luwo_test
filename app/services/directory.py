"""Read-only questions about schools, classes and teachers."""

from app.domain.errors import InvalidRequest, NotFound, PermissionDenied
from app.domain.models import Actor, Role, School, SchoolClass
from app.repositories.interfaces import UnitOfWork, UnitOfWorkFactory

from .common import school_names
from .names import class_name_candidates, normalize_school_name
from .permissions import can_access_class, require_superadmin, require_teacher_management
from .views import ClassRoster, ClassSummary, TeacherEntry


def _match_schools(schools: list[School], query: str) -> list[School]:
    """Exact match on the normalized name if there is one, otherwise 'contains'."""
    wanted = normalize_school_name(query)
    exact = [s for s in schools if normalize_school_name(s.name) == wanted]
    return exact or [s for s in schools if wanted and wanted in normalize_school_name(s.name)]


async def resolve_school_id(uow: UnitOfWork, actor: Actor, school_name: str | None) -> int | None:
    """Which school a request is about. None means 'all schools' (superadmin only)."""
    if actor.role != Role.SUPERADMIN:
        own = await uow.schools.get(actor.school_id)
        if school_name and not _match_schools([own], school_name):
            raise PermissionDenied(f"You only have access to your own school ({own.name})")
        return actor.school_id
    if not school_name:
        return None
    matches = _match_schools(await uow.schools.list_all(), school_name)
    if not matches:
        raise NotFound(f"No school matches '{school_name}'")
    if len(matches) > 1:
        raise InvalidRequest("Several schools match", details={"schools": [s.name for s in matches]})
    return matches[0].id


async def resolve_class(
    uow: UnitOfWork, actor: Actor, class_name: str, school_name: str | None = None
) -> SchoolClass:
    school_id = await resolve_school_id(uow, actor, school_name)
    school_ids = [school_id] if school_id is not None else [s.id for s in await uow.schools.list_all()]
    found: list[SchoolClass] = []
    for candidate in class_name_candidates(class_name):
        for sid in school_ids:
            cls = await uow.classes.find_by_name(sid, candidate)
            if cls:
                found.append(cls)
        if found:
            break
    if not found:
        raise NotFound(f"No class named {class_name} was found")
    if len(found) > 1:
        names = await school_names(uow, actor)
        raise InvalidRequest(
            "Several schools have a class with this name; say which school",
            details={"schools": [names[c.school_id] for c in found]},
        )
    if not can_access_class(actor, found[0]):
        raise PermissionDenied(f"Class {found[0].name} is not one of your classes")
    return found[0]


class DirectoryService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow = uow_factory

    async def find_class(self, actor: Actor, class_name: str, school_name: str | None = None) -> SchoolClass:
        async with self._uow() as uow:
            return await resolve_class(uow, actor, class_name, school_name)

    async def find_school_id(self, actor: Actor, school_name: str | None) -> int | None:
        """The school a name refers to. For teachers and admins this is always their own school;
        naming another school is refused. None = no school named (superadmin only)."""
        async with self._uow() as uow:
            return await resolve_school_id(uow, actor, school_name)

    async def get_roster(
        self, actor: Actor, class_name: str, school_name: str | None = None, include_inactive: bool = False
    ) -> ClassRoster:
        async with self._uow() as uow:
            cls = await resolve_class(uow, actor, class_name, school_name)
            students = await uow.students.list_by_class(cls.id, include_inactive=include_inactive)
            teachers = None
            if actor.role != Role.TEACHER:  # teachers may not view teacher assignments
                teachers = (await uow.teachers.list_for_classes([cls.id]))[cls.id]
            names = await school_names(uow, actor)
            return ClassRoster(cls, names.get(cls.school_id, ""), teachers, students)

    async def list_classes(self, actor: Actor, school_name: str | None = None) -> list[ClassSummary]:
        async with self._uow() as uow:
            school_id = await resolve_school_id(uow, actor, school_name)
            if actor.role == Role.TEACHER:
                classes = await uow.classes.list_led_by(actor.user_id)
            elif school_id is not None:
                classes = await uow.classes.list_by_school(school_id)
            else:
                classes = [c for s in await uow.schools.list_all() for c in await uow.classes.list_by_school(s.id)]

            teachers = None
            if actor.role != Role.TEACHER:
                teachers = await uow.teachers.list_for_classes([c.id for c in classes])
            names = await school_names(uow, actor)
            return [
                ClassSummary(
                    cls=c,
                    school_name=names.get(c.school_id, ""),
                    active_students=len(await uow.students.list_by_class(c.id)),
                    teachers=teachers[c.id] if teachers is not None else None,
                )
                for c in classes
            ]

    async def list_teachers(self, actor: Actor, school_name: str | None = None) -> list[TeacherEntry]:
        require_teacher_management(actor)
        async with self._uow() as uow:
            school_id = await resolve_school_id(uow, actor, school_name)
            school_ids = [school_id] if school_id is not None else [s.id for s in await uow.schools.list_all()]
            names = await school_names(uow, actor)
            entries = []
            for sid in school_ids:
                for teacher in await uow.teachers.list_by_school(sid):
                    led = await uow.classes.list_led_by(teacher.id)
                    entries.append(TeacherEntry(teacher, names[sid], [c.name for c in led]))
            return entries

    async def list_schools(self, actor: Actor) -> list[School]:
        require_superadmin(actor, "list all schools")
        async with self._uow() as uow:
            return await uow.schools.list_all()
