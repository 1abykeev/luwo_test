"""Every data-changing operation, written as an Action with two steps:

  plan()   checks permissions and rules, and describes what WOULD happen. Changes nothing.
  apply()  does the change and writes the history rows. Always called right after plan(),
           inside one transaction, so a change is re-checked at the moment it runs.

ChangeService (changes.py) wires these into propose -> confirm."""

from dataclasses import dataclass, field

from app.domain.errors import Conflict, InvalidRequest, NotFound, PermissionDenied
from app.domain.models import Actor, ChangeEntry, Role, Student, StudentStatus, Teacher
from app.repositories.interfaces import UnitOfWork

from .names import clean_person_name, name_key, search_variants
from .permissions import can_access_class, can_access_student, require_teacher_management, scope_for

MAX_STUDENTS_PER_TRANSFER = 60


@dataclass(frozen=True)
class Plan:
    summary: str  # short English description, kept for the audit trail
    details: dict  # structured facts; the agent and the app phrase these in the user's language
    params: dict  # cleaned parameters that get stored and later applied
    warnings: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ActionContext:
    source: str  # "agent" or "user"
    conversation_id: str | None


# ---------- helpers ----------

def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InvalidRequest(f"{name} must be a number")
    try:
        return int(value)
    except ValueError:
        raise InvalidRequest(f"{name} must be a number") from None


def _student_brief(s: Student) -> dict:
    return {"id": s.id, "full_name": s.full_name, "class": s.class_name, "status": s.status.value}


def _teacher_brief(t: Teacher) -> dict:
    return {"id": t.id, "full_name": t.full_name}


async def _require_class(uow: UnitOfWork, actor: Actor, raw_id: object):
    cls = await uow.classes.get(_int(raw_id, "class_id"))
    # Another school's class is reported as "not found", so ids can't be used to probe other schools.
    if cls is None or (actor.role != Role.SUPERADMIN and cls.school_id != actor.school_id):
        raise NotFound("No such class")
    if not can_access_class(actor, cls):
        raise PermissionDenied(f"Class {cls.name} is not one of your classes")
    return cls


async def _require_student(uow: UnitOfWork, actor: Actor, raw_id: object) -> Student:
    student = await uow.students.get(_int(raw_id, "student_id"))
    if student is None or not can_access_student(actor, student):
        raise NotFound("No such student in your lists")
    return student


async def _require_teacher(uow: UnitOfWork, actor: Actor, raw_id: object) -> Teacher:
    require_teacher_management(actor)
    teacher = await uow.teachers.get(_int(raw_id, "teacher_id"))
    if teacher is None or (actor.role != Role.SUPERADMIN and teacher.school_id != actor.school_id):
        raise NotFound("No such teacher")
    return teacher


async def _school_name(uow: UnitOfWork, school_id: int) -> str:
    school = await uow.schools.get(school_id)
    return school.name if school else ""


async def _log(
    uow: UnitOfWork, actor: Actor, ctx: ActionContext, action: str, entity_type: str,
    entity_id: int, school_id: int | None, before: dict | None, after: dict | None,
) -> None:
    await uow.history.add(
        ChangeEntry(
            action=action, entity_type=entity_type, entity_id=entity_id, school_id=school_id,
            actor_user_id=actor.user_id, source=ctx.source, before=before, after=after,
            conversation_id=ctx.conversation_id,
        )
    )


def _class_state(class_id: int, class_name: str, **extra) -> dict:
    return {"class_id": class_id, "class_name": class_name, **extra}


# ---------- student actions ----------

class AddStudent:
    name = "add_student"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        full_name = clean_person_name(params.get("full_name"))
        cls = await _require_class(uow, actor, params.get("class_id"))
        allow_duplicate = bool(params.get("allow_duplicate"))

        found = {}
        for variant in search_variants(full_name):
            for s in await uow.students.search(variant, scope_for(actor), include_inactive=True):
                found[s.id] = s
        same_name = [s for s in found.values() if name_key(s.full_name) == name_key(full_name)]
        in_class = [s for s in same_name if s.class_id == cls.id]
        if in_class and not allow_duplicate:
            raise Conflict(
                f"A student named {full_name} already exists in {cls.name}",
                details={"existing": [_student_brief(s) for s in in_class]},
            )
        elsewhere = [s for s in same_name if s.class_id != cls.id]
        warnings = (
            [{"code": "same_name_elsewhere", "students": [_student_brief(s) for s in elsewhere]}]
            if elsewhere else []
        )
        return Plan(
            summary=f"Add student {full_name} to class {cls.name}",
            details={
                "action": self.name, "student_name": full_name, "class": cls.name,
                "school": await _school_name(uow, cls.school_id),
            },
            params={"class_id": cls.id, "full_name": full_name, "allow_duplicate": allow_duplicate},
            warnings=warnings,
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        cls = await uow.classes.get(plan.params["class_id"])
        student = await uow.students.add(
            school_id=cls.school_id, class_id=cls.id, full_name=plan.params["full_name"]
        )
        await _log(uow, actor, ctx, "student_added", "student", student.id, cls.school_id, None,
                   _class_state(cls.id, cls.name, status="active"))
        return {"student": _student_brief(student)}


class RemoveStudent:
    """Remove = deactivate. The record stays, so history and 'where did she go' keep working."""

    name = "remove_student"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        student = await _require_student(uow, actor, params.get("student_id"))
        if student.status == StudentStatus.INACTIVE:
            raise Conflict(f"{student.full_name} is already removed from {student.class_name}")
        return Plan(
            summary=f"Remove student {student.full_name} from class {student.class_name}",
            details={"action": self.name, "student": _student_brief(student)},
            params={"student_id": student.id},
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        student = await uow.students.get(plan.params["student_id"])
        before = _class_state(student.class_id, student.class_name, status="active")
        updated = await uow.students.set_status(student.id, StudentStatus.INACTIVE)
        await _log(uow, actor, ctx, "student_deactivated", "student", student.id, student.school_id,
                   before, _class_state(student.class_id, student.class_name, status="inactive"))
        return {"student": _student_brief(updated)}


class RestoreStudent:
    name = "restore_student"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        student = await _require_student(uow, actor, params.get("student_id"))
        if student.status == StudentStatus.ACTIVE:
            raise Conflict(f"{student.full_name} is already active in {student.class_name}")
        return Plan(
            summary=f"Restore student {student.full_name} in class {student.class_name}",
            details={"action": self.name, "student": _student_brief(student)},
            params={"student_id": student.id},
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        student = await uow.students.get(plan.params["student_id"])
        updated = await uow.students.set_status(student.id, StudentStatus.ACTIVE)
        await _log(uow, actor, ctx, "student_restored", "student", student.id, student.school_id,
                   _class_state(student.class_id, student.class_name, status="inactive"),
                   _class_state(student.class_id, student.class_name, status="active"))
        return {"student": _student_brief(updated)}


class TransferStudents:
    """One or many students to one class, confirmed once."""

    name = "transfer_students"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        raw_ids = params.get("student_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise InvalidRequest("student_ids must be a non-empty list")
        ids = list(dict.fromkeys(_int(i, "student_id") for i in raw_ids))
        if len(ids) > MAX_STUDENTS_PER_TRANSFER:
            raise InvalidRequest(f"At most {MAX_STUDENTS_PER_TRANSFER} students can be moved at once")

        target = await _require_class(uow, actor, params.get("to_class_id"))
        students = [await _require_student(uow, actor, i) for i in ids]

        inactive = [s for s in students if s.status == StudentStatus.INACTIVE]
        if inactive:
            raise Conflict("Removed students can't be transferred; restore them first",
                           details={"students": [_student_brief(s) for s in inactive]})
        already_there = [s for s in students if s.class_id == target.id]
        if already_there:
            raise Conflict(f"Already in class {target.name}",
                           details={"students": [_student_brief(s) for s in already_there]})

        names = ", ".join(s.full_name for s in students)
        return Plan(
            summary=f"Move {names} to class {target.name}",
            details={
                "action": self.name, "to_class": target.name,
                "school": await _school_name(uow, target.school_id),
                "students": [_student_brief(s) for s in students],
            },
            params={"student_ids": ids, "to_class_id": target.id},
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        target = await uow.classes.get(plan.params["to_class_id"])
        moved = []
        for student_id in plan.params["student_ids"]:
            student = await uow.students.get(student_id)
            before = _class_state(student.class_id, student.class_name)
            updated = await uow.students.move_to_class(student_id, target.id)
            # The history row belongs to the school the student LEFT (that school's staff look it up).
            await _log(uow, actor, ctx, "student_transferred", "student", student_id, student.school_id,
                       before, _class_state(target.id, target.name))
            moved.append({**_student_brief(updated), "from_class": before["class_name"]})
        return {"moved": moved, "to_class": target.name}


# ---------- teacher actions ----------

class AddTeacher:
    name = "add_teacher"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        require_teacher_management(actor)
        raw_school = params.get("school_id")
        if actor.role == Role.SCHOOL_ADMIN:
            if raw_school is not None and _int(raw_school, "school_id") != actor.school_id:
                raise PermissionDenied("You can only add teachers to your own school")
            school_id = actor.school_id
        elif raw_school is None:
            raise InvalidRequest("school_id is required: which school is the teacher for?")
        else:
            school_id = _int(raw_school, "school_id")
        school = await uow.schools.get(school_id)
        if school is None:
            raise NotFound("No such school")

        full_name = clean_person_name(params.get("full_name"))
        allow_duplicate = bool(params.get("allow_duplicate"))
        found_teachers = {}
        for variant in search_variants(full_name):
            for t in await uow.teachers.find_by_name(variant, school.id):
                found_teachers[t.id] = t
        same_name = [t for t in found_teachers.values() if t.is_active and name_key(t.full_name) == name_key(full_name)]
        if same_name and not allow_duplicate:
            raise Conflict(f"A teacher named {full_name} already works at {school.name}",
                           details={"existing": [_teacher_brief(t) for t in same_name]})

        classes = []
        for raw_id in params.get("class_ids") or []:
            cls = await uow.classes.get(_int(raw_id, "class_id"))
            if cls is None or cls.school_id != school.id:
                raise InvalidRequest("Every class must belong to the same school as the teacher")
            classes.append(cls)
        class_names = [c.name for c in classes]
        return Plan(
            summary=f"Add teacher {full_name} to {school.name}"
            + (f" and assign classes {', '.join(class_names)}" if classes else ""),
            details={"action": self.name, "teacher_name": full_name, "school": school.name,
                     "classes": class_names},
            params={"school_id": school.id, "full_name": full_name, "allow_duplicate": allow_duplicate,
                    "class_ids": [c.id for c in classes]},
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        p = plan.params
        teacher = await uow.teachers.add(school_id=p["school_id"], full_name=p["full_name"])
        await _log(uow, actor, ctx, "teacher_added", "teacher", teacher.id, p["school_id"], None,
                   {"is_active": True})
        assigned = []
        for class_id in p["class_ids"]:
            cls = await uow.classes.get(class_id)
            await uow.teachers.assign(teacher.id, class_id)
            await _log(uow, actor, ctx, "teacher_assigned", "teacher", teacher.id, p["school_id"], None,
                       _class_state(cls.id, cls.name))
            assigned.append(cls.name)
        return {"teacher": _teacher_brief(teacher), "assigned_classes": assigned}


class RemoveTeacher:
    name = "remove_teacher"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        teacher = await _require_teacher(uow, actor, params.get("teacher_id"))
        if not teacher.is_active:
            raise Conflict(f"{teacher.full_name} is already removed")
        led = await uow.classes.list_led_by(teacher.id)
        others = await uow.teachers.list_for_classes([c.id for c in led])
        orphaned = [c.name for c in led if len(others[c.id]) <= 1]
        return Plan(
            summary=f"Remove teacher {teacher.full_name}",
            details={"action": self.name, "teacher": _teacher_brief(teacher), "classes": [c.name for c in led]},
            params={"teacher_id": teacher.id},
            warnings=[{"code": "classes_left_without_teacher", "classes": orphaned}] if orphaned else [],
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        teacher = await uow.teachers.get(plan.params["teacher_id"])
        unassigned = []
        for cls in await uow.classes.list_led_by(teacher.id):
            await uow.teachers.unassign(teacher.id, cls.id)
            await _log(uow, actor, ctx, "teacher_unassigned", "teacher", teacher.id, teacher.school_id,
                       _class_state(cls.id, cls.name), None)
            unassigned.append(cls.name)
        updated = await uow.teachers.set_active(teacher.id, False)
        await _log(uow, actor, ctx, "teacher_removed", "teacher", teacher.id, teacher.school_id,
                   {"is_active": True}, {"is_active": False})
        return {"teacher": _teacher_brief(updated), "unassigned_classes": unassigned}


class _TeacherClassChange:
    """Shared checks for assigning and unassigning."""

    async def _check(self, uow: UnitOfWork, actor: Actor, params: dict):
        teacher = await _require_teacher(uow, actor, params.get("teacher_id"))
        if not teacher.is_active:
            raise Conflict(f"{teacher.full_name} has been removed and can't be assigned")
        cls = await uow.classes.get(_int(params.get("class_id"), "class_id"))
        if cls is None or (actor.role != Role.SUPERADMIN and cls.school_id != actor.school_id):
            raise NotFound("No such class")
        if cls.school_id != teacher.school_id:
            raise InvalidRequest("The teacher and the class belong to different schools")
        assigned = any(c.id == cls.id for c in await uow.classes.list_led_by(teacher.id))
        return teacher, cls, assigned


class AssignTeacher(_TeacherClassChange):
    name = "assign_teacher"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        teacher, cls, assigned = await self._check(uow, actor, params)
        if assigned:
            raise Conflict(f"{teacher.full_name} already leads class {cls.name}")
        return Plan(
            summary=f"Assign teacher {teacher.full_name} to class {cls.name}",
            details={"action": self.name, "teacher": _teacher_brief(teacher), "class": cls.name},
            params={"teacher_id": teacher.id, "class_id": cls.id},
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        teacher = await uow.teachers.get(plan.params["teacher_id"])
        cls = await uow.classes.get(plan.params["class_id"])
        await uow.teachers.assign(teacher.id, cls.id)
        await _log(uow, actor, ctx, "teacher_assigned", "teacher", teacher.id, teacher.school_id,
                   None, _class_state(cls.id, cls.name))
        return {"teacher": _teacher_brief(teacher), "class": cls.name}


class UnassignTeacher(_TeacherClassChange):
    name = "unassign_teacher"

    async def plan(self, uow: UnitOfWork, actor: Actor, params: dict) -> Plan:
        teacher, cls, assigned = await self._check(uow, actor, params)
        if not assigned:
            raise Conflict(f"{teacher.full_name} does not lead class {cls.name}")
        others = (await uow.teachers.list_for_classes([cls.id]))[cls.id]
        warnings = [{"code": "class_left_without_teacher", "class": cls.name}] if len(others) <= 1 else []
        return Plan(
            summary=f"Unassign teacher {teacher.full_name} from class {cls.name}",
            details={"action": self.name, "teacher": _teacher_brief(teacher), "class": cls.name},
            params={"teacher_id": teacher.id, "class_id": cls.id},
            warnings=warnings,
        )

    async def apply(self, uow: UnitOfWork, actor: Actor, plan: Plan, ctx: ActionContext) -> dict:
        teacher = await uow.teachers.get(plan.params["teacher_id"])
        cls = await uow.classes.get(plan.params["class_id"])
        await uow.teachers.unassign(teacher.id, cls.id)
        await _log(uow, actor, ctx, "teacher_unassigned", "teacher", teacher.id, teacher.school_id,
                   _class_state(cls.id, cls.name), None)
        return {"teacher": _teacher_brief(teacher), "class": cls.name}


ACTIONS = {
    a.name: a
    for a in [
        AddStudent(), RemoveStudent(), RestoreStudent(), TransferStudents(),
        AddTeacher(), RemoveTeacher(), AssignTeacher(), UnassignTeacher(),
    ]
}
