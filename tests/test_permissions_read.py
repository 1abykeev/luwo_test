"""The permission table from the task, row by row, for everything that only READS data."""

import pytest

from app.domain.errors import InvalidRequest, NotFound, PermissionDenied
from app.domain.models import Role
from tests.helpers import GYMNASIUM, LYCEUM, SCHOOL12, class_id, student_id


# ---- actor loading: role/school/classes come from the database ----

async def test_actor_is_built_from_the_database(actor):
    teacher = await actor("bakyt@luwo.test")
    assert teacher.role == Role.TEACHER
    assert teacher.class_ids == {class_id(LYCEUM, "3А"), class_id(LYCEUM, "3Б")}

    admin = await actor("admin1@luwo.test")
    assert admin.role == Role.SCHOOL_ADMIN and admin.class_ids == frozenset()

    root = await actor("root@luwo.test")
    assert root.role == Role.SUPERADMIN and root.school_id is None


async def test_removed_teacher_cannot_act(services):
    from tests.helpers import user_id

    with pytest.raises(PermissionDenied):
        await services.actors.load(user_id("gulmira@luwo.test"))


# ---- "View student list": own classes / own school / all schools ----

async def test_teacher_sees_own_class(services, actor):
    roster = await services.directory.get_roster(await actor("aigul@luwo.test"), "4А")
    names = {s.full_name for s in roster.students}
    assert "Амир Касымов" in names and "Амир Жумаев" in names
    assert "Эрмек Бакиров" not in names  # deactivated students are hidden by default
    assert roster.teachers is None  # a teacher may not view teacher assignments


async def test_teacher_cannot_view_another_class_of_the_same_school(services, actor):
    with pytest.raises(PermissionDenied):
        await services.directory.get_roster(await actor("aigul@luwo.test"), "4Б")


async def test_teacher_cannot_name_another_school(services, actor):
    with pytest.raises(PermissionDenied):
        await services.directory.get_roster(await actor("aigul@luwo.test"), "4А", school_name=GYMNASIUM)


async def test_teacher_can_name_their_own_school(services, actor):
    roster = await services.directory.get_roster(await actor("aigul@luwo.test"), "4А", school_name="лицей 1")
    assert roster.school_name == LYCEUM


async def test_admin_sees_every_class_of_own_school_with_teachers(services, actor):
    admin = await actor("admin1@luwo.test")
    roster = await services.directory.get_roster(admin, "4Б")
    assert [t.full_name for t in roster.teachers] == ["Нурлан Ибраев"]
    classes = await services.directory.list_classes(admin)
    assert [c.cls.name for c in classes] == ["3А", "3Б", "4А", "4Б"]


async def test_admin_cannot_see_another_school(services, actor):
    admin = await actor("admin1@luwo.test")
    with pytest.raises(PermissionDenied):
        await services.directory.get_roster(admin, "4А", school_name=GYMNASIUM)
    with pytest.raises(PermissionDenied):
        await services.directory.list_classes(admin, school_name=SCHOOL12)


async def test_superadmin_needs_a_school_when_the_class_name_is_ambiguous(services, actor):
    root = await actor("root@luwo.test")
    with pytest.raises(InvalidRequest) as error:
        await services.directory.get_roster(root, "4А")
    assert set(error.value.details["schools"]) == {LYCEUM, GYMNASIUM, SCHOOL12}

    roster = await services.directory.get_roster(root, "4А", school_name=GYMNASIUM)
    assert roster.school_name == GYMNASIUM


async def test_unknown_class_is_not_found(services, actor):
    with pytest.raises(NotFound):
        await services.directory.get_roster(await actor("admin1@luwo.test"), "9Я")


async def test_latin_class_names_work(services, actor):
    roster = await services.directory.get_roster(await actor("bakyt@luwo.test"), "3b")  # means 3Б
    assert roster.cls.name == "3Б"


async def test_a_teacher_sees_only_own_classes_in_the_class_list(services, actor):
    classes = await services.directory.list_classes(await actor("bakyt@luwo.test"))
    assert [c.cls.name for c in classes] == ["3А", "3Б"]
    assert all(c.teachers is None for c in classes)


# ---- teachers and schools lists ----

async def test_teachers_cannot_list_teachers_or_schools(services, actor):
    teacher = await actor("bakyt@luwo.test")
    with pytest.raises(PermissionDenied):
        await services.directory.list_teachers(teacher)
    with pytest.raises(PermissionDenied):
        await services.directory.list_schools(teacher)


async def test_admin_lists_own_school_teachers_but_not_schools(services, actor):
    admin = await actor("admin1@luwo.test")
    entries = await services.directory.list_teachers(admin)
    assert {e.teacher.full_name for e in entries} == {"Бакыт Осмонов", "Айгуль Садыкова", "Нурлан Ибраев"}
    assert "Гульмира Дюшеева" not in {e.teacher.full_name for e in entries}  # removed
    assert next(e for e in entries if e.teacher.full_name == "Бакыт Осмонов").class_names == ["3А", "3Б"]
    with pytest.raises(PermissionDenied):
        await services.directory.list_schools(admin)


async def test_superadmin_lists_everything(services, actor):
    root = await actor("root@luwo.test")
    assert len(await services.directory.list_schools(root)) == 3
    entries = await services.directory.list_teachers(root)
    assert {e.school_name for e in entries} == {LYCEUM, GYMNASIUM, SCHOOL12}


# ---- "Search students and duplicates": own classes / own school / all schools ----

async def test_search_is_limited_to_what_the_user_may_see(services, actor):
    async def names_found(email):
        hits = await services.students.search(await actor(email), "Амир")
        return sorted((h.student.full_name, h.school_name) for h in hits)

    assert await names_found("aigul@luwo.test") == [("Амир Жумаев", LYCEUM), ("Амир Касымов", LYCEUM)]
    assert await names_found("bakyt@luwo.test") == []  # no Amir in 3А / 3Б
    assert len(await names_found("admin1@luwo.test")) == 2  # school-wide, still not the Gymnasium
    assert len(await names_found("root@luwo.test")) == 4  # every school (incl. Амира)


async def test_search_is_case_insensitive_and_hides_inactive_by_default(services, actor):
    aigul = await actor("aigul@luwo.test")
    assert await services.students.search(aigul, "эрмек") == []
    hits = await services.students.search(aigul, "эрмек", include_inactive=True)
    assert [h.student.full_name for h in hits] == ["Эрмек Бакиров"]


async def test_duplicates_follow_the_same_scope(services, actor):
    async def groups(email):
        found = await services.students.find_duplicates(await actor(email))
        return sorted((g[0].student.full_name, len(g)) for g in found)

    assert await groups("aigul@luwo.test") == []  # two Амирs, but different surnames
    assert await groups("bakyt@luwo.test") == [("Алина Смирнова", 2)]  # 3А and 3Б
    assert await groups("admin1@luwo.test") == [("Алина Смирнова", 2)]  # the Gymnasium's Alina is invisible
    assert await groups("root@luwo.test") == [("Алина Смирнова", 3), ("Амир Касымов", 2)]


# ---- student card ----

async def test_student_card_respects_scope(services, actor):
    aigul = await actor("aigul@luwo.test")
    own = student_id(LYCEUM, "4А", "Амир Касымов")
    card = await services.students.get_student(aigul, own)
    assert card.student.full_name == "Амир Касымов" and card.school_name == LYCEUM

    with pytest.raises(NotFound):  # a student of the same school, but another teacher's class
        await services.students.get_student(aigul, student_id(LYCEUM, "3А", "Данияр Исаков"))
    with pytest.raises(NotFound):  # another school entirely
        await services.students.get_student(aigul, student_id(GYMNASIUM, "4А", "Амир Касымов"))


# ---- "A student disappeared from my list" ----

async def test_missing_student_moved_to_a_class_the_teacher_cannot_see(services, actor):
    # Алина Назарова was moved 4А -> 4Б; Айгуль leads 4А only.
    findings = await services.students.investigate_missing_student(await actor("aigul@luwo.test"), "Назарова")
    assert len(findings) == 1
    finding = findings[0]
    assert finding.state == "moved_out_of_your_access"
    assert finding.current_class is None  # must not reveal where she is now
    transfer = next(e for e in finding.events if e.action == "student_transferred")
    assert transfer.from_class == "4А" and transfer.to_class is None


async def test_missing_student_moved_between_the_teachers_own_classes(services, actor):
    # Алина Иманова was moved 3А -> 3Б; Бакыт leads both, so he may see everything.
    findings = await services.students.investigate_missing_student(await actor("bakyt@luwo.test"), "Иманова")
    assert [(f.state, f.current_class) for f in findings] == [("active", "3Б")]
    transfer = next(e for e in findings[0].events if e.action == "student_transferred")
    assert (transfer.from_class, transfer.to_class) == ("3А", "3Б")


async def test_missing_student_who_was_deactivated(services, actor):
    findings = await services.students.investigate_missing_student(await actor("aigul@luwo.test"), "Эрмек")
    assert [(f.state, f.current_class) for f in findings] == [("deactivated", "4А")]
    assert any(e.action == "student_deactivated" for e in findings[0].events)


async def test_admin_finds_a_transferred_student_in_their_school(services, actor):
    findings = await services.students.investigate_missing_student(await actor("admin1@luwo.test"), "Назарова")
    assert [(f.state, f.current_class) for f in findings] == [("active", "4Б")]


async def test_missing_student_search_does_not_leak_other_schools(services, actor):
    findings = await services.students.investigate_missing_student(await actor("aigul@luwo.test"), "Станислав")
    assert findings == []  # a deactivated student of the Gymnasium
