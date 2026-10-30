"""The tools, called the way the agent calls them. Run on both the memory and Postgres adapters."""

import json

import pytest

from app.agent.llm import ToolCall
from app.tools import ToolContext, build_registry
from tests.helpers import GYMNASIUM, LYCEUM, class_id, student_id, teacher_id

REGISTRY = build_registry()


@pytest.fixture
def run(services, actor):
    """await run("aigul@luwo.test", "list_class_students", class_name="4А") -> ToolOutcome.
    A fresh context per call = a fresh chat request."""

    async def call(email, tool, ctx=None, **args):
        ctx = ctx or ToolContext(await actor(email), services, "conv-1")
        return await REGISTRY.execute(ctx, ToolCall("call-1", tool, args))

    return call


async def roster_names(run, email, class_name):
    outcome = await run(email, "list_class_students", class_name=class_name)
    return {s["full_name"] for s in outcome.result["students"]}


# ---- every tool result must be plain JSON the model can read ----

def test_every_tool_has_a_unique_name_and_a_schema():
    names = [s.name for s in REGISTRY.specs]
    assert len(names) == len(set(names)) == 19
    assert all(s.input_schema["type"] == "object" and s.description for s in REGISTRY.specs)


async def test_results_and_blocks_are_json_serializable(run):
    for email, tool, args in [
        ("aigul@luwo.test", "list_class_students", {"class_name": "4А"}),
        ("admin1@luwo.test", "list_classes", {}),
        ("admin1@luwo.test", "list_teachers", {}),
        ("root@luwo.test", "list_schools", {}),
        ("aigul@luwo.test", "search_students", {"name": "Амир"}),
        ("aigul@luwo.test", "find_duplicates", {}),
        ("aigul@luwo.test", "investigate_missing_student", {"name": "Назарова"}),
        ("aigul@luwo.test", "get_student", {"student_id": student_id(LYCEUM, "4А", "Амир Жумаев")}),
    ]:
        outcome = await run(email, tool, **args)
        assert not outcome.is_error, (tool, outcome.result)
        json.dumps(outcome.result, ensure_ascii=False)
        json.dumps(outcome.blocks, ensure_ascii=False)
        assert outcome.blocks


# ---- permissions show up as tool errors, never as data ----

async def test_a_teacher_gets_a_permission_error_for_another_class(run):
    outcome = await run("aigul@luwo.test", "list_class_students", class_name="4Б")
    assert outcome.is_error and outcome.kind == "permission_denied"
    assert outcome.blocks[0]["type"] == "banner"
    assert "students" not in outcome.result


async def test_naming_another_school_is_refused(run):
    outcome = await run("aigul@luwo.test", "list_class_students", class_name="4А", school=GYMNASIUM)
    assert outcome.kind == "permission_denied"


async def test_teachers_cannot_use_admin_tools(run):
    assert (await run("bakyt@luwo.test", "list_teachers")).kind == "permission_denied"
    assert (await run("bakyt@luwo.test", "list_schools")).kind == "permission_denied"
    outcome = await run("bakyt@luwo.test", "add_teacher", full_name="Новый Учитель")
    assert outcome.kind == "permission_denied"


async def test_teachers_do_not_see_who_leads_a_class(run):
    outcome = await run("aigul@luwo.test", "list_class_students", class_name="4А")
    assert outcome.result["teachers"] is None
    admin_outcome = await run("admin1@luwo.test", "list_class_students", class_name="4А")
    assert admin_outcome.result["teachers"] == [{"id": 6, "full_name": "Айгуль Садыкова"}]


async def test_search_never_returns_students_outside_the_scope(run):
    outcome = await run("aigul@luwo.test", "search_students", name="Алина")
    assert outcome.result["count"] == 0


async def test_arguments_the_model_invents_cannot_change_who_is_acting(run):
    # The tool schemas have no user or role fields; extra arguments are simply ignored.
    outcome = await run("aigul@luwo.test", "list_class_students", class_name="4Б", role="superadmin", user_id=1)
    assert outcome.kind == "permission_denied"


# ---- bad input and failures ----

async def test_bad_arguments_become_errors_the_model_can_fix(run):
    assert (await run("aigul@luwo.test", "get_student", student_id="abc")).kind == "invalid_request"
    assert (await run("aigul@luwo.test", "search_students", name="")).kind == "invalid_request"
    assert (await run("aigul@luwo.test", "transfer_students", student_ids="all", to_class="4Б")).kind == "invalid_request"


async def test_an_unknown_tool_is_an_error(services, actor):
    ctx = ToolContext(await actor("aigul@luwo.test"), services, "conv-1")
    outcome = await REGISTRY.execute(ctx, ToolCall("c", "drop_database", {}))
    assert outcome.is_error and outcome.kind == "invalid_request"


async def test_a_backend_crash_says_the_action_was_not_performed(run, services, monkeypatch):
    async def explode(*args, **kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(services.changes, "propose", explode)
    outcome = await run("aigul@luwo.test", "remove_student",
                        student_id=student_id(LYCEUM, "4А", "Амир Жумаев"))
    assert outcome.is_error and outcome.kind == "error"
    assert "NOT performed" in outcome.result["message"]
    assert "on fire" not in json.dumps(outcome.result)  # internals are not leaked to the model or the user
    assert outcome.blocks[0]["level"] == "error"


# ---- changes are proposals first ----

async def test_a_proposal_changes_nothing_and_returns_a_confirmation_card(run):
    amir = student_id(LYCEUM, "4А", "Амир Жумаев")
    outcome = await run("aigul@luwo.test", "remove_student", student_id=amir)

    assert outcome.kind == "pending_confirmation" and not outcome.is_error
    assert outcome.result["status"] == "pending_confirmation"
    assert "NOTHING HAS BEEN CHANGED" in outcome.result["instruction"]
    card = outcome.blocks[0]
    assert card["type"] == "confirmation" and card["token"] == outcome.result["token"]
    assert "Амир Жумаев" in await roster_names(run, "aigul@luwo.test", "4А")


async def test_a_change_cannot_be_confirmed_in_the_same_turn_that_proposed_it(run, services, actor):
    ctx = ToolContext(await actor("aigul@luwo.test"), services, "conv-1")
    amir = student_id(LYCEUM, "4А", "Амир Жумаев")

    proposal = await run("aigul@luwo.test", "remove_student", ctx=ctx, student_id=amir)
    attempt = await run("aigul@luwo.test", "confirm_pending_action", ctx=ctx, token=proposal.result["token"])

    assert attempt.is_error and attempt.kind == "invalid_request"
    assert "Амир Жумаев" in await roster_names(run, "aigul@luwo.test", "4А")


async def test_a_change_can_be_confirmed_in_the_next_turn(run):
    amir = student_id(LYCEUM, "4А", "Амир Жумаев")
    proposal = await run("aigul@luwo.test", "remove_student", student_id=amir)

    done = await run("aigul@luwo.test", "confirm_pending_action", token=proposal.result["token"])  # new context

    assert done.kind == "confirmed" and done.result["status"] == "done"
    assert done.blocks[0]["type"] == "result"
    assert "Амир Жумаев" not in await roster_names(run, "aigul@luwo.test", "4А")


async def test_confirming_twice_reports_already_done(run):
    proposal = await run("aigul@luwo.test", "add_student", full_name="Новый Ученик", class_name="4A")  # Latin A
    token = proposal.result["token"]
    first = await run("aigul@luwo.test", "confirm_pending_action", token=token)
    second = await run("aigul@luwo.test", "confirm_pending_action", token=token)

    assert (first.result["status"], second.result["status"]) == ("done", "already_done")
    assert (await run("aigul@luwo.test", "search_students", name="Новый Ученик")).result["count"] == 1


async def test_a_made_up_or_foreign_token_does_nothing(run):
    assert (await run("aigul@luwo.test", "confirm_pending_action", token="made-up")).kind == "not_found"
    proposal = await run("aigul@luwo.test", "add_student", full_name="Новый Ученик", class_name="4А")
    stolen = await run("admin1@luwo.test", "confirm_pending_action", token=proposal.result["token"])
    assert stolen.kind == "not_found"


async def test_cancel_stops_the_change_for_good(run):
    proposal = await run("aigul@luwo.test", "add_student", full_name="Новый Ученик", class_name="4А")
    token = proposal.result["token"]
    assert (await run("aigul@luwo.test", "cancel_pending_action", token=token)).kind == "cancelled"
    assert (await run("aigul@luwo.test", "confirm_pending_action", token=token)).kind == "conflict"


async def test_a_namesake_is_reported_with_the_existing_student(run):
    outcome = await run("aigul@luwo.test", "add_student", full_name="Амир Касымов", class_name="4А")
    assert outcome.kind == "conflict"
    assert outcome.result["details"]["existing"][0]["full_name"] == "Амир Касымов"
    assert outcome.result["details"]["different_person_token"]


async def test_a_namesake_can_be_added_only_after_the_user_answers(run, services, actor):
    ctx = ToolContext(await actor("aigul@luwo.test"), services, "conv-1")
    conflict = await run("aigul@luwo.test", "add_student", ctx=ctx, full_name="Амир Касымов", class_name="4А")
    token = conflict.result["details"]["different_person_token"]

    # the model tries to answer for the user in the same turn: refused
    same_turn = await run("aigul@luwo.test", "add_student", ctx=ctx, full_name="Амир Касымов",
                          class_name="4А", different_person_token=token)
    assert same_turn.kind == "invalid_request"

    # the user said "different child" in the next message: accepted
    next_turn = await run("aigul@luwo.test", "add_student", full_name="Амир Касымов", class_name="4А",
                          different_person_token=token)
    assert next_turn.kind == "pending_confirmation"


async def test_an_override_token_cannot_be_invented_or_reused_for_someone_else(run):
    invented = await run("aigul@luwo.test", "add_student", full_name="Амир Касымов", class_name="4А",
                         different_person_token="0" * 24)
    assert invented.kind == "invalid_request"

    conflict = await run("aigul@luwo.test", "add_student", full_name="Амир Касымов", class_name="4А")
    token = conflict.result["details"]["different_person_token"]
    other_person = await run("aigul@luwo.test", "add_student", full_name="Амир Жумаев", class_name="4А",
                             different_person_token=token)
    assert other_person.kind == "invalid_request"  # the token is for that exact name and class


async def test_a_boolean_flag_no_longer_bypasses_the_namesake_check(run):
    outcome = await run("aigul@luwo.test", "add_student", full_name="Амир Касымов", class_name="4А",
                        allow_duplicate=True)
    assert outcome.kind == "conflict"


async def test_move_the_remaining_students_with_one_confirmation(run):
    roster = await run("admin1@luwo.test", "list_class_students", class_name="4А")
    ids = [s["id"] for s in roster.result["students"]]
    proposal = await run("admin1@luwo.test", "transfer_students", student_ids=ids, to_class="4B")  # Latin B -> 4Б
    assert proposal.kind == "pending_confirmation"
    assert len(proposal.result["details"]["students"]) == len(ids)

    await run("admin1@luwo.test", "confirm_pending_action", token=proposal.result["token"])
    assert await roster_names(run, "admin1@luwo.test", "4А") == set()


async def test_a_teacher_cannot_move_students_into_someone_elses_class(run):
    ruslan = student_id(LYCEUM, "3А", "Руслан Мамытов")
    outcome = await run("bakyt@luwo.test", "transfer_students", student_ids=[ruslan], to_class="4А")
    assert outcome.kind == "permission_denied"


async def test_adding_a_teacher_with_classes(run):
    proposal = await run("admin3@luwo.test", "add_teacher", full_name="Новый Учитель", class_names=["4Б"])
    assert proposal.kind == "pending_confirmation"
    done = await run("admin3@luwo.test", "confirm_pending_action", token=proposal.result["token"])
    assert done.result["result"]["assigned_classes"] == ["4Б"]


async def test_a_superadmin_must_name_the_school_for_a_new_teacher(run):
    outcome = await run("root@luwo.test", "add_teacher", full_name="Новый Учитель")
    assert outcome.kind == "invalid_request" and "school" in outcome.result["message"]
    ok = await run("root@luwo.test", "add_teacher", full_name="Новый Учитель", school="гимназия 5")
    assert ok.kind == "pending_confirmation"


async def test_assigning_a_teacher_needs_admin_rights_and_the_right_school(run):
    sergey = teacher_id("sergey@luwo.test")  # Гимназия №5, leads nothing
    proposal = await run("admin2@luwo.test", "assign_teacher", teacher_id=sergey, class_name="3Б")
    assert proposal.kind == "pending_confirmation"
    # An admin of another school cannot even see this teacher
    other = await run("admin1@luwo.test", "assign_teacher", teacher_id=sergey, class_name="3Б")
    assert other.kind == "not_found"


# ---- the special tool ----

async def test_out_of_scope_requests_are_marked_for_analytics(run):
    outcome = await run("aigul@luwo.test", "report_out_of_scope", topic="grades")
    assert outcome.kind == "out_of_scope" and not outcome.is_error
    assert REGISTRY.request_type("report_out_of_scope") == "off_topic"


# ---- "a student disappeared" through the tool ----

async def test_the_missing_student_tool_hides_what_the_teacher_may_not_see(run):
    outcome = await run("aigul@luwo.test", "investigate_missing_student", name="Назарова")
    finding = outcome.result["findings"][0]
    assert finding["state"] == "moved_out_of_your_access" and finding["current_class"] is None
    assert "4Б" not in json.dumps(outcome.result, ensure_ascii=False)


# ---- review fix #3: namesake tokens expire and belong to one conversation; confirms too ----

async def test_a_namesake_token_only_works_in_the_conversation_it_was_issued_in(run, services, actor):
    me = await actor("aigul@luwo.test")
    conflict = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-A"),
                         full_name="Амир Касымов", class_name="4А")
    token = conflict.result["details"]["different_person_token"]

    elsewhere = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-B"),
                          full_name="Амир Касымов", class_name="4А", different_person_token=token)
    assert elsewhere.kind == "invalid_request"

    same = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-A"),
                     full_name="Амир Касымов", class_name="4А", different_person_token=token)
    assert same.kind == "pending_confirmation"


async def test_a_namesake_token_expires(run, services, actor, clock):
    me = await actor("aigul@luwo.test")
    conflict = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-1", now=clock),
                         full_name="Амир Касымов", class_name="4А")
    token = conflict.result["details"]["different_person_token"]

    clock.advance(minutes=14)
    still_valid = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-1", now=clock),
                            full_name="Амир Касымов", class_name="4А", different_person_token=token)
    assert still_valid.kind == "pending_confirmation"

    clock.advance(minutes=2)  # 16 minutes after it was issued
    expired = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-1", now=clock),
                        full_name="Амир Касымов", class_name="4А", different_person_token=token)
    assert expired.kind == "invalid_request" and "expired" in expired.result["message"]


async def test_a_token_with_a_tampered_expiry_is_rejected(run, services, actor, clock):
    me = await actor("aigul@luwo.test")
    conflict = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-1", now=clock),
                         full_name="Амир Касымов", class_name="4А")
    expires, signature = conflict.result["details"]["different_person_token"].split(".")
    forged = f"{int(expires) + 86400}.{signature}"  # try to extend it by a day
    outcome = await run("aigul@luwo.test", "add_student", ctx=ToolContext(me, services, "conv-1", now=clock),
                        full_name="Амир Касымов", class_name="4А", different_person_token=forged)
    assert outcome.kind == "invalid_request"


async def test_a_pending_change_can_only_be_confirmed_in_its_own_conversation(run, services, actor):
    me = await actor("aigul@luwo.test")
    amir = student_id(LYCEUM, "4А", "Амир Жумаев")
    proposal = await run("aigul@luwo.test", "remove_student", ctx=ToolContext(me, services, "conv-A"), student_id=amir)
    token = proposal.result["token"]

    elsewhere = await run("aigul@luwo.test", "confirm_pending_action", ctx=ToolContext(me, services, "conv-B"), token=token)
    assert elsewhere.kind == "not_found"
    assert "Амир Жумаев" in await roster_names(run, "aigul@luwo.test", "4А")

    here = await run("aigul@luwo.test", "confirm_pending_action", ctx=ToolContext(me, services, "conv-A"), token=token)
    assert here.kind == "confirmed"
