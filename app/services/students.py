"""Read-only student questions: search, card, duplicates, 'where did she go?'."""

from app.domain.errors import NotFound
from app.domain.models import Actor, Role, StudentStatus
from app.repositories.interfaces import UnitOfWork, UnitOfWorkFactory

from .common import school_names
from .names import clean_search_text
from .permissions import can_access_class, can_access_student, scope_for
from .views import HistoryEvent, StudentDetail, StudentFinding, StudentHit


async def build_events(uow: UnitOfWork, actor: Actor, student_id: int) -> list[HistoryEvent]:
    """A student's history, with class names hidden when the viewer may not see that class."""
    visible_names: dict[int, str | None] = {}

    async def visible_class(info: dict | None) -> str | None:
        class_id = (info or {}).get("class_id")
        if class_id is None:
            return None
        if class_id not in visible_names:
            cls = await uow.classes.get(class_id)
            visible_names[class_id] = cls.name if cls and can_access_class(actor, cls) else None
        return visible_names[class_id]

    return [
        HistoryEvent(e.action, e.at, await visible_class(e.before), await visible_class(e.after))
        for e in await uow.history.list_for_entity("student", student_id)
    ]


class StudentService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow = uow_factory

    async def get_student(self, actor: Actor, student_id: int) -> StudentDetail:
        async with self._uow() as uow:
            student = await uow.students.get(student_id)
            if student is None or not can_access_student(actor, student):
                raise NotFound("No such student in your lists")
            names = await school_names(uow, actor)
            return StudentDetail(student, names.get(student.school_id), await build_events(uow, actor, student.id))

    async def search(self, actor: Actor, name: str, include_inactive: bool = False) -> list[StudentHit]:
        text = clean_search_text(name)
        async with self._uow() as uow:
            found = await uow.students.search(text, scope_for(actor), include_inactive=include_inactive)
            names = await school_names(uow, actor)
            return [StudentHit(s, names.get(s.school_id)) for s in found]

    async def find_duplicates(self, actor: Actor) -> list[list[StudentHit]]:
        async with self._uow() as uow:
            groups = await uow.students.find_duplicate_groups(scope_for(actor))
            names = await school_names(uow, actor)
            return [[StudentHit(s, names.get(s.school_id)) for s in group] for group in groups]

    async def investigate_missing_student(self, actor: Actor, name: str) -> list[StudentFinding]:
        """Where did this student go? Looks at the current lists (including deactivated
        records) and at transfers out of the user's classes. Only reveals what the user is
        allowed to see: a student moved to a class they can't see is reported as 'moved out'
        without naming the new class."""
        text = clean_search_text(name)
        scope = scope_for(actor)
        findings: list[StudentFinding] = []
        async with self._uow() as uow:
            seen: set[int] = set()
            for student in await uow.students.search(text, scope, include_inactive=True):
                seen.add(student.id)
                state = "active" if student.status == StudentStatus.ACTIVE else "deactivated"
                events = await build_events(uow, actor, student.id)
                findings.append(StudentFinding(student.id, student.full_name, state, student.class_name, events))

            if actor.role != Role.SUPERADMIN:  # a superadmin's search above already sees everyone
                for entry in await uow.history.list_transfers_out(scope):
                    if entry.entity_id in seen:
                        continue
                    student = await uow.students.get(entry.entity_id)
                    if student is None or text.casefold() not in student.full_name.casefold():
                        continue
                    seen.add(student.id)
                    events = await build_events(uow, actor, student.id)
                    findings.append(
                        StudentFinding(student.id, student.full_name, "moved_out_of_your_access", None, events)
                    )
        return findings
