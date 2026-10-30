"""Changing data: permissions, the propose -> confirm flow, idempotency and history."""

import asyncio

import pytest

from app.domain.errors import Conflict, InvalidRequest, NotFound, PermissionDenied
from tests.helpers import GYMNASIUM, LYCEUM, class_id, school_id, student_id, teacher_id


async def roster_names(services, actor, class_name, **kwargs):
    roster = await services.directory.get_roster(actor, class_name, **kwargs)
    return {s.full_name for s in roster.students}


async def history_actions(services, actor, student):
    detail = await services.students.get_student(actor, student)
    return [e.action for e in detail.events]


# ---- the confirmation flow ----

async def test_proposing_changes_nothing(services, actor):
    aigul = await actor("aigul@luwo.test")
    proposal = await services.changes.propose(
        aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"}
    )
    assert proposal.token and "Новый Ученик" in proposal.summary
    assert "Новый Ученик" not in await roster_names(services, aigul, "4А")


async def test_confirming_applies_the_change_and_writes_history(services, actor):
    aigul = await actor("aigul@luwo.test")
    proposal = await services.changes.propose(
        aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"}
    )
    outcome = await services.changes.confirm(aigul, proposal.token)

    assert outcome.already_applied is False
    assert "Новый Ученик" in await roster_names(services, aigul, "4А")
    new_id = outcome.result["student"]["id"]
    assert await history_actions(services, aigul, new_id) == ["student_added"]


async def test_history_records_who_what_and_source(services, actor, uow_factory):
    aigul = await actor("aigul@luwo.test")
    proposal = await services.changes.propose(
        aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"},
        conversation_id="conv-1",
    )
    outcome = await services.changes.confirm(aigul, proposal.token)
    async with uow_factory() as uow:
        (entry,) = await uow.history.list_for_entity("student", outcome.result["student"]["id"])
    assert entry.actor_user_id == aigul.user_id
    assert entry.source == "agent" and entry.conversation_id == "conv-1"
    assert entry.after["class_name"] == "4А" and entry.before is None


async def test_confirming_twice_returns_the_first_result_and_changes_nothing_more(services, actor):
    aigul = await actor("aigul@luwo.test")
    proposal = await services.changes.propose(
        aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"}
    )
    first = await services.changes.confirm(aigul, proposal.token)
    second = await services.changes.confirm(aigul, proposal.token)

    assert second.already_applied is True and second.result == first.result
    hits = await services.students.search(aigul, "Новый Ученик")
    assert len(hits) == 1  # added once, not twice


async def test_simultaneous_confirms_add_exactly_one_student(services, actor):
    aigul = await actor("aigul@luwo.test")
    proposal = await services.changes.propose(
        aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"}
    )
    results = await asyncio.gather(
        *[services.changes.confirm(aigul, proposal.token) for _ in range(5)], return_exceptions=True
    )
    assert not [r for r in results if isinstance(r, Exception)]
    assert sum(not r.already_applied for r in results) == 1
    assert len(await services.students.search(aigul, "Новый Ученик")) == 1


async def test_cancelled_request_cannot_be_confirmed(services, actor):
    aigul = await actor("aigul@luwo.test")
    proposal = await services.changes.propose(
        aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"}
    )
    await services.changes.cancel(aigul, proposal.token)
    with pytest.raises(Conflict):
        await services.changes.confirm(aigul, proposal.token)
    assert await services.students.search(aigul, "Новый Ученик") == []


async def test_expired_request_cannot_be_confirmed(services, actor, clock):
    aigul = await actor("aigul@luwo.test")
    proposal = await services.changes.propose(
        aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"}
    )
    clock.advance(minutes=16)
    with pytest.raises(Conflict, match="expired"):
        await services.changes.confirm(aigul, proposal.token)


async def test_someone_elses_token_is_unknown(services, actor):
    proposal = await services.changes.propose(
        await actor("aigul@luwo.test"), "add_student",
        {"class_id": class_id(LYCEUM, "4А"), "full_name": "Новый Ученик"},
    )
    with pytest.raises(NotFound):
        await services.changes.confirm(await actor("admin1@luwo.test"), proposal.token)


async def test_garbage_token_and_unknown_action(services, actor):
    aigul = await actor("aigul@luwo.test")
    with pytest.raises(NotFound):
        await services.changes.confirm(aigul, "not-a-token")
    with pytest.raises(InvalidRequest):
        await services.changes.propose(aigul, "drop_database", {})


async def test_rules_are_checked_again_at_confirm_time(services, actor):
    admin = await actor("admin1@luwo.test")
    alina = student_id(LYCEUM, "3А", "Алина Смирнова")
    to_3b = {"student_ids": [alina], "to_class_id": class_id(LYCEUM, "3Б")}
    first = await services.changes.propose(admin, "transfer_students", to_3b)
    second = await services.changes.propose(admin, "transfer_students", to_3b)

    await services.changes.confirm(admin, first.token)
    with pytest.raises(Conflict):  # she is already in 3Б now
        await services.changes.confirm(admin, second.token)


# ---- adding students ----

async def test_teacher_cannot_add_to_a_class_that_is_not_theirs(services, actor):
    aigul = await actor("aigul@luwo.test")
    with pytest.raises(PermissionDenied):
        await services.changes.propose(
            aigul, "add_student", {"class_id": class_id(LYCEUM, "4Б"), "full_name": "Новый Ученик"}
        )
    with pytest.raises(NotFound):  # another school: indistinguishable from a class that doesn't exist
        await services.changes.propose(
            aigul, "add_student", {"class_id": class_id(GYMNASIUM, "4А"), "full_name": "Новый Ученик"}
        )


async def test_namesake_in_the_same_class_needs_a_decision(services, actor):
    aigul = await actor("aigul@luwo.test")
    params = {"class_id": class_id(LYCEUM, "4А"), "full_name": "Амир Касымов"}
    with pytest.raises(Conflict) as error:
        await services.changes.propose(aigul, "add_student", params)
    assert error.value.details["existing"][0]["full_name"] == "Амир Касымов"

    # "No, it is a different child": the agent asks again with allow_duplicate
    proposal = await services.changes.propose(aigul, "add_student", {**params, "allow_duplicate": True})
    await services.changes.confirm(aigul, proposal.token)
    assert len(await services.students.search(aigul, "Амир Касымов")) == 2


async def test_a_removed_student_with_the_same_name_is_reported(services, actor):
    aigul = await actor("aigul@luwo.test")
    with pytest.raises(Conflict) as error:
        await services.changes.propose(
            aigul, "add_student", {"class_id": class_id(LYCEUM, "4А"), "full_name": "Эрмек Бакиров"}
        )
    assert error.value.details["existing"][0]["status"] == "inactive"


async def test_same_name_in_another_class_is_only_a_warning(services, actor):
    bakyt = await actor("bakyt@luwo.test")
    proposal = await services.changes.propose(
        bakyt, "add_student", {"class_id": class_id(LYCEUM, "3А"), "full_name": "Эмир Сыдыков"}
    )  # exists in 3Б
    assert proposal.warnings[0]["code"] == "same_name_elsewhere"


async def test_invalid_names_are_rejected(services, actor):
    with pytest.raises(InvalidRequest):
        await services.changes.propose(
            await actor("aigul@luwo.test"), "add_student",
            {"class_id": class_id(LYCEUM, "4А"), "full_name": "x'; DROP TABLE students;--"},
        )


# ---- removing and restoring ----

async def test_remove_deactivates_and_keeps_the_record(services, actor):
    aigul = await actor("aigul@luwo.test")
    amir = student_id(LYCEUM, "4А", "Амир Жумаев")
    proposal = await services.changes.propose(aigul, "remove_student", {"student_id": amir})
    await services.changes.confirm(aigul, proposal.token)

    assert "Амир Жумаев" not in await roster_names(services, aigul, "4А")
    assert "Амир Жумаев" in await roster_names(services, aigul, "4А", include_inactive=True)
    assert await history_actions(services, aigul, amir) == ["student_added", "student_deactivated"]


async def test_cannot_remove_twice_or_outside_own_classes(services, actor):
    aigul = await actor("aigul@luwo.test")
    with pytest.raises(Conflict):
        await services.changes.propose(
            aigul, "remove_student", {"student_id": student_id(LYCEUM, "4А", "Эрмек Бакиров")}
        )
    with pytest.raises(NotFound):
        await services.changes.propose(
            aigul, "remove_student", {"student_id": student_id(LYCEUM, "3А", "Данияр Исаков")}
        )
    with pytest.raises(NotFound):
        await services.changes.propose(
            aigul, "remove_student", {"student_id": student_id(GYMNASIUM, "4А", "Ольга Новикова")}
        )


async def test_restore_brings_a_removed_student_back(services, actor):
    aigul = await actor("aigul@luwo.test")
    ermek = student_id(LYCEUM, "4А", "Эрмек Бакиров")
    proposal = await services.changes.propose(aigul, "restore_student", {"student_id": ermek})
    await services.changes.confirm(aigul, proposal.token)
    assert "Эрмек Бакиров" in await roster_names(services, aigul, "4А")
    with pytest.raises(Conflict):  # already active now
        await services.changes.propose(aigul, "restore_student", {"student_id": ermek})


# ---- transfers: own classes / own school / any ----

async def test_teacher_transfers_between_own_classes(services, actor):
    bakyt = await actor("bakyt@luwo.test")
    ruslan = student_id(LYCEUM, "3А", "Руслан Мамытов")
    proposal = await services.changes.propose(
        bakyt, "transfer_students", {"student_ids": [ruslan], "to_class_id": class_id(LYCEUM, "3Б")}
    )
    await services.changes.confirm(bakyt, proposal.token)
    assert "Руслан Мамытов" in await roster_names(services, bakyt, "3Б")
    assert "Руслан Мамытов" not in await roster_names(services, bakyt, "3А")


async def test_teacher_cannot_transfer_into_or_out_of_classes_that_are_not_theirs(services, actor):
    bakyt = await actor("bakyt@luwo.test")
    ruslan = student_id(LYCEUM, "3А", "Руслан Мамытов")
    with pytest.raises(PermissionDenied):  # destination is another teacher's class
        await services.changes.propose(
            bakyt, "transfer_students", {"student_ids": [ruslan], "to_class_id": class_id(LYCEUM, "4А")}
        )
    with pytest.raises(NotFound):  # the student is in a class that is not theirs
        await services.changes.propose(
            bakyt, "transfer_students",
            {"student_ids": [student_id(LYCEUM, "4А", "Бермет Алиева")], "to_class_id": class_id(LYCEUM, "3А")},
        )


async def test_admin_transfers_between_classes_of_own_school_only(services, actor):
    admin = await actor("admin1@luwo.test")
    ruslan = student_id(LYCEUM, "3А", "Руслан Мамытов")
    proposal = await services.changes.propose(
        admin, "transfer_students", {"student_ids": [ruslan], "to_class_id": class_id(LYCEUM, "4Б")}
    )
    await services.changes.confirm(admin, proposal.token)
    assert "Руслан Мамытов" in await roster_names(services, admin, "4Б")

    with pytest.raises(NotFound):  # a class of another school
        await services.changes.propose(
            admin, "transfer_students", {"student_ids": [ruslan], "to_class_id": class_id(GYMNASIUM, "3А")}
        )


async def test_superadmin_can_transfer_across_schools(services, actor):
    root = await actor("root@luwo.test")
    ruslan = student_id(LYCEUM, "3А", "Руслан Мамытов")
    proposal = await services.changes.propose(
        root, "transfer_students", {"student_ids": [ruslan], "to_class_id": class_id(GYMNASIUM, "3Б")}
    )
    await services.changes.confirm(root, proposal.token)

    card = await services.students.get_student(root, ruslan)
    assert card.school_name == GYMNASIUM and card.student.class_name == "3Б"
    lyceum_admin = await actor("admin1@luwo.test")
    with pytest.raises(NotFound):  # no longer in the Lyceum
        await services.students.get_student(lyceum_admin, ruslan)


async def test_move_the_remaining_students_of_a_class_in_one_confirmation(services, actor, uow_factory):
    admin = await actor("admin1@luwo.test")
    roster = await services.directory.get_roster(admin, "4А")
    ids = [s.id for s in roster.students]
    proposal = await services.changes.propose(
        admin, "transfer_students", {"student_ids": ids, "to_class_id": class_id(LYCEUM, "4Б")}
    )
    outcome = await services.changes.confirm(admin, proposal.token)

    assert len(outcome.result["moved"]) == len(ids)
    assert await roster_names(services, admin, "4А") == set()
    async with uow_factory() as uow:
        for student in ids:
            actions = [e.action for e in await uow.history.list_for_entity("student", student)]
            assert actions.count("student_transferred") >= 1


async def test_transfer_rejects_nonsense(services, actor):
    admin = await actor("admin1@luwo.test")
    alina = student_id(LYCEUM, "3А", "Алина Смирнова")
    to_3b = class_id(LYCEUM, "3Б")
    with pytest.raises(Conflict):  # same class
        await services.changes.propose(
            admin, "transfer_students", {"student_ids": [alina], "to_class_id": class_id(LYCEUM, "3А")}
        )
    with pytest.raises(Conflict):  # a removed student
        await services.changes.propose(
            admin, "transfer_students",
            {"student_ids": [student_id(LYCEUM, "4А", "Эрмек Бакиров")], "to_class_id": to_3b},
        )
    with pytest.raises(InvalidRequest):
        await services.changes.propose(admin, "transfer_students", {"student_ids": [], "to_class_id": to_3b})
    with pytest.raises(InvalidRequest):
        await services.changes.propose(admin, "transfer_students", {"student_ids": ["abc"], "to_class_id": to_3b})


# ---- teachers: admin and superadmin only ----

async def test_teachers_cannot_manage_teachers(services, actor):
    bakyt = await actor("bakyt@luwo.test")
    for action, params in [
        ("add_teacher", {"full_name": "Новый Учитель"}),
        ("remove_teacher", {"teacher_id": teacher_id("aigul@luwo.test")}),
        ("assign_teacher", {"teacher_id": teacher_id("bakyt@luwo.test"), "class_id": class_id(LYCEUM, "4А")}),
    ]:
        with pytest.raises(PermissionDenied):
            await services.changes.propose(bakyt, action, params)


async def test_admin_adds_a_teacher_and_assigns_a_class_in_one_step(services, actor):
    admin = await actor("admin3@luwo.test")  # Школа №12: 4Б has no teacher
    proposal = await services.changes.propose(
        admin, "add_teacher", {"full_name": "Новый Учитель", "class_ids": [class_id("Школа №12", "4Б")]}
    )
    outcome = await services.changes.confirm(admin, proposal.token)

    assert outcome.result["assigned_classes"] == ["4Б"]
    roster = await services.directory.get_roster(admin, "4Б")
    assert [t.full_name for t in roster.teachers] == ["Новый Учитель"]


async def test_admin_cannot_add_a_teacher_to_another_school(services, actor):
    admin = await actor("admin1@luwo.test")
    with pytest.raises(PermissionDenied):
        await services.changes.propose(
            admin, "add_teacher", {"full_name": "Новый Учитель", "school_id": school_id(GYMNASIUM)}
        )


async def test_superadmin_must_say_which_school_for_a_new_teacher(services, actor):
    root = await actor("root@luwo.test")
    with pytest.raises(InvalidRequest):
        await services.changes.propose(root, "add_teacher", {"full_name": "Новый Учитель"})
    proposal = await services.changes.propose(
        root, "add_teacher", {"full_name": "Новый Учитель", "school_id": school_id(GYMNASIUM)}
    )
    assert proposal.details["school"] == GYMNASIUM


async def test_duplicate_teacher_name_needs_a_decision(services, actor):
    with pytest.raises(Conflict):
        await services.changes.propose(
            await actor("admin1@luwo.test"), "add_teacher", {"full_name": "Бакыт Осмонов"}
        )


async def test_admin_cannot_touch_teachers_or_classes_of_another_school(services, actor):
    admin = await actor("admin1@luwo.test")
    with pytest.raises(NotFound):
        await services.changes.propose(admin, "remove_teacher", {"teacher_id": teacher_id("elena@luwo.test")})
    with pytest.raises(NotFound):
        await services.changes.propose(
            admin, "assign_teacher",
            {"teacher_id": teacher_id("bakyt@luwo.test"), "class_id": class_id(GYMNASIUM, "3Б")},
        )


async def test_teacher_and_class_must_be_in_the_same_school(services, actor):
    root = await actor("root@luwo.test")
    with pytest.raises(InvalidRequest):
        await services.changes.propose(
            root, "assign_teacher",
            {"teacher_id": teacher_id("bakyt@luwo.test"), "class_id": class_id(GYMNASIUM, "3Б")},
        )


async def test_assign_and_unassign(services, actor):
    admin = await actor("admin2@luwo.test")  # Гимназия №5, 3Б has no teacher; Сергей leads nothing
    params = {"teacher_id": teacher_id("sergey@luwo.test"), "class_id": class_id(GYMNASIUM, "3Б")}

    proposal = await services.changes.propose(admin, "assign_teacher", params)
    await services.changes.confirm(admin, proposal.token)
    assert [t.full_name for t in (await services.directory.get_roster(admin, "3Б")).teachers] == ["Сергей Лебедев"]
    with pytest.raises(Conflict):  # already assigned
        await services.changes.propose(admin, "assign_teacher", params)

    # He can now work with that class
    sergey = await actor("sergey@luwo.test")
    assert len((await services.directory.get_roster(sergey, "3Б")).students) == 4

    proposal = await services.changes.propose(admin, "unassign_teacher", params)
    assert proposal.warnings == [{"code": "class_left_without_teacher", "class": "3Б"}]
    await services.changes.confirm(admin, proposal.token)
    assert (await services.directory.get_roster(admin, "3Б")).teachers == []
    with pytest.raises(Conflict):
        await services.changes.propose(admin, "unassign_teacher", params)


async def test_removing_a_teacher_unassigns_their_classes(services, actor):
    admin = await actor("admin1@luwo.test")
    proposal = await services.changes.propose(admin, "remove_teacher", {"teacher_id": teacher_id("nurlan@luwo.test")})
    assert proposal.warnings == [{"code": "classes_left_without_teacher", "classes": ["4Б"]}]
    outcome = await services.changes.confirm(admin, proposal.token)

    assert outcome.result["unassigned_classes"] == ["4Б"]
    assert (await services.directory.get_roster(admin, "4Б")).teachers == []
    assert "Нурлан Ибраев" not in {e.teacher.full_name for e in await services.directory.list_teachers(admin)}
    # and he can no longer act
    from tests.helpers import user_id

    with pytest.raises(PermissionDenied):
        await services.actors.load(user_id("nurlan@luwo.test"))
