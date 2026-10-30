"""Tools that change data. They only PROPOSE a change: nothing happens until the user confirms."""

import hashlib
import hmac

from app.config import settings
from app.domain.errors import Conflict, InvalidRequest
from app.services.names import clean_person_name

from .base import Tool, ToolContext, ToolOutcome, banner, int_arg, schema, str_arg
from .read_tools import CLASS_NAME, SCHOOL

PENDING_NOTE = (
    "NOTHING HAS BEEN CHANGED YET. Describe what will happen, ask the user to confirm (a confirmation "
    "card with buttons is shown to them), and stop. Never say the change is done."
)


async def _propose(ctx: ToolContext, action: str, params: dict) -> ToolOutcome:
    proposal = await ctx.services.changes.propose(ctx.actor, action, params, ctx.conversation_id)
    ctx.proposals_this_turn.add(proposal.token)
    card = {
        "type": "confirmation", "token": proposal.token, "action": proposal.action,
        "summary": proposal.summary, "details": proposal.details, "warnings": proposal.warnings,
        "expires_at": proposal.expires_at.isoformat(),
    }
    result = {
        "status": "pending_confirmation", "token": proposal.token, "summary": proposal.summary,
        "details": proposal.details, "warnings": proposal.warnings, "instruction": PENDING_NOTE,
    }
    return ToolOutcome(result, blocks=[card], kind="pending_confirmation")


def _override_token(ctx: ToolContext, kind: str, place_id: int, name: str) -> str:
    """Proof that the model has seen a namesake conflict for exactly this person in this place.
    Signed with a server secret, so the model cannot make one up."""
    message = f"{kind}:{ctx.actor.user_id}:{place_id}:{name.casefold()}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()[:24]


def _check_override(ctx: ToolContext, kind: str, place_id: int, name: str, given: str | None) -> bool:
    if not given:
        return False
    if given in ctx.override_tokens_this_turn:
        raise InvalidRequest(
            "You received this token in the current message. Ask the user whether it is the same "
            "person or a different one; use the token only after they answer in a later message."
        )
    if not hmac.compare_digest(given, _override_token(ctx, kind, place_id, name)):
        raise InvalidRequest("This token does not belong to this person; do not invent tokens")
    return True


def _namesake_conflict(ctx: ToolContext, conflict: Conflict, kind: str, place_id: int, name: str) -> Conflict:
    token = _override_token(ctx, kind, place_id, name)
    ctx.override_tokens_this_turn.add(token)
    details = {
        **conflict.details,
        "different_person_token": token,
        "instruction": "Ask the user: is it the same person, or a different one with the same name? "
        "Only if they say it is a different person, in a later message, call again with this token.",
    }
    return Conflict(conflict.message, details)


async def add_student(ctx: ToolContext, args: dict) -> ToolOutcome:
    cls = await ctx.services.directory.find_class(
        ctx.actor, str_arg(args, "class_name"), str_arg(args, "school", required=False)
    )
    name = clean_person_name(str_arg(args, "full_name"))
    allow = _check_override(ctx, "student", cls.id, name, str_arg(args, "different_person_token", required=False))
    try:
        return await _propose(ctx, "add_student", {"class_id": cls.id, "full_name": name, "allow_duplicate": allow})
    except Conflict as conflict:
        if "existing" not in conflict.details:
            raise
        raise _namesake_conflict(ctx, conflict, "student", cls.id, name) from None


async def remove_student(ctx: ToolContext, args: dict) -> ToolOutcome:
    return await _propose(ctx, "remove_student", {"student_id": int_arg(args, "student_id")})


async def restore_student(ctx: ToolContext, args: dict) -> ToolOutcome:
    return await _propose(ctx, "restore_student", {"student_id": int_arg(args, "student_id")})


async def transfer_students(ctx: ToolContext, args: dict) -> ToolOutcome:
    ids = args.get("student_ids")
    if not isinstance(ids, list):
        raise InvalidRequest("'student_ids' must be a list of student ids")
    target = await ctx.services.directory.find_class(
        ctx.actor, str_arg(args, "to_class"), str_arg(args, "school", required=False)
    )
    return await _propose(ctx, "transfer_students", {"student_ids": ids, "to_class_id": target.id})


async def add_teacher(ctx: ToolContext, args: dict) -> ToolOutcome:
    school = str_arg(args, "school", required=False)
    school_id = await ctx.services.directory.find_school_id(ctx.actor, school)
    class_ids = []
    for name in args.get("class_names") or []:
        cls = await ctx.services.directory.find_class(ctx.actor, str(name), school)
        class_ids.append(cls.id)
    name = clean_person_name(str_arg(args, "full_name"))
    place = school_id or 0
    allow = _check_override(ctx, "teacher", place, name, str_arg(args, "different_person_token", required=False))
    try:
        return await _propose(ctx, "add_teacher", {
            "full_name": name, "school_id": school_id, "class_ids": class_ids, "allow_duplicate": allow,
        })
    except Conflict as conflict:
        if "existing" not in conflict.details:
            raise
        raise _namesake_conflict(ctx, conflict, "teacher", place, name) from None


async def remove_teacher(ctx: ToolContext, args: dict) -> ToolOutcome:
    return await _propose(ctx, "remove_teacher", {"teacher_id": int_arg(args, "teacher_id")})


async def _teacher_class_change(ctx: ToolContext, args: dict, action: str) -> ToolOutcome:
    cls = await ctx.services.directory.find_class(
        ctx.actor, str_arg(args, "class_name"), str_arg(args, "school", required=False)
    )
    return await _propose(ctx, action, {"teacher_id": int_arg(args, "teacher_id"), "class_id": cls.id})


async def assign_teacher(ctx: ToolContext, args: dict) -> ToolOutcome:
    return await _teacher_class_change(ctx, args, "assign_teacher")


async def unassign_teacher(ctx: ToolContext, args: dict) -> ToolOutcome:
    return await _teacher_class_change(ctx, args, "unassign_teacher")


async def confirm_pending_action(ctx: ToolContext, args: dict) -> ToolOutcome:
    token = str_arg(args, "token")
    if token in ctx.proposals_this_turn:
        # The same message that asked for the change must not also approve it.
        raise InvalidRequest(
            "This change was proposed in the current message. Ask the user to confirm it first; "
            "you can only confirm after the user replies with a clear yes."
        )
    outcome = await ctx.services.changes.confirm(ctx.actor, token, source="agent")
    status = "already_done" if outcome.already_applied else "done"
    return ToolOutcome(
        {"status": status, "result": outcome.result},
        blocks=[{"type": "result", "status": status, "result": outcome.result}],
        kind="confirmed",
    )


async def cancel_pending_action(ctx: ToolContext, args: dict) -> ToolOutcome:
    await ctx.services.changes.cancel(ctx.actor, str_arg(args, "token"))
    return ToolOutcome(
        {"status": "cancelled", "note": "The change was NOT made."},
        blocks=[banner("info", "Cancelled")],
        kind="cancelled",
    )


STUDENT_ID = {"type": "integer", "description": "Student id from an earlier search or class list."}
TEACHER_ID = {"type": "integer", "description": "Teacher id from list_teachers."}
FULL_NAME = {"type": "string", "description": "Full name, letters only."}
DIFFERENT_PERSON_TOKEN = {
    "type": "string",
    "description": "The 'different_person_token' from a namesake conflict. Pass it ONLY after the user "
    "told you, in a message after the conflict, that it is a different person with the same name.",
}

CHANGE_TOOLS = [
    Tool(
        "add_student",
        "Propose adding a NEW student to a class. Nothing is added until the user confirms. If a student "
        "with the same name already exists in that class you get a 'conflict' error listing them and a "
        "different_person_token: ask the user whether it is the same child or a different one, and only "
        "if they say it is a different child call again with that token.",
        schema({"full_name": FULL_NAME, "class_name": CLASS_NAME, "school": SCHOOL,
                "different_person_token": DIFFERENT_PERSON_TOKEN}, ["full_name", "class_name"]),
        "add", add_student,
    ),
    Tool(
        "remove_student",
        "Propose removing a student from their class. This deactivates the record (history is kept). "
        "Needs the student's id: search first. If several students match, ask the user which one.",
        schema({"student_id": STUDENT_ID}, ["student_id"]),
        "remove", remove_student,
    ),
    Tool(
        "restore_student",
        "Propose bringing a removed (inactive) student back into their class.",
        schema({"student_id": STUDENT_ID}, ["student_id"]),
        "restore", restore_student,
    ),
    Tool(
        "transfer_students",
        "Propose moving one or more students to another class, confirmed once. For 'move the remaining "
        "students' list the class first and pass all the ids. Teachers can only move students between "
        "their own classes.",
        schema({"student_ids": {"type": "array", "items": {"type": "integer"}},
                "to_class": {"type": "string", "description": "Name of the destination class."},
                "school": SCHOOL}, ["student_ids", "to_class"]),
        "transfer", transfer_students,
    ),
    Tool(
        "add_teacher",
        "Propose adding a new teacher to the school, optionally assigning classes at the same time. "
        "School admins and superadmins only. A superadmin must also say which school.",
        schema({"full_name": FULL_NAME, "school": SCHOOL,
                "class_names": {"type": "array", "items": {"type": "string"},
                                "description": "Classes the new teacher will lead."},
                "different_person_token": DIFFERENT_PERSON_TOKEN}, ["full_name"]),
        "add", add_teacher,
    ),
    Tool(
        "remove_teacher",
        "Propose removing a teacher from the school; their class assignments end. School admins and "
        "superadmins only. Needs the teacher's id from list_teachers.",
        schema({"teacher_id": TEACHER_ID}, ["teacher_id"]),
        "remove", remove_teacher,
    ),
    Tool(
        "assign_teacher",
        "Propose making a teacher lead a class. School admins and superadmins only.",
        schema({"teacher_id": TEACHER_ID, "class_name": CLASS_NAME, "school": SCHOOL},
               ["teacher_id", "class_name"]),
        "assign", assign_teacher,
    ),
    Tool(
        "unassign_teacher",
        "Propose taking a class away from a teacher. School admins and superadmins only.",
        schema({"teacher_id": TEACHER_ID, "class_name": CLASS_NAME, "school": SCHOOL},
               ["teacher_id", "class_name"]),
        "assign", unassign_teacher,
    ),
    Tool(
        "confirm_pending_action",
        "Carry out a change the user has just approved in their LATEST message ('yes', 'да', 'confirm'). "
        "Pass the token from the earlier proposal. Never call this in the same turn that proposed the "
        "change, and never without a clear approval from the user. After it returns status 'done' you may "
        "tell the user the change was made; if it returns an error, tell them it was NOT made.",
        schema({"token": {"type": "string"}}, ["token"]),
        "confirm", confirm_pending_action,
    ),
    Tool(
        "cancel_pending_action",
        "Cancel a proposed change when the user says no or changes their mind. Pass the proposal's token.",
        schema({"token": {"type": "string"}}, ["token"]),
        "confirm", cancel_pending_action,
    ),
]
