"""propose -> confirm: how every change reaches the database."""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.domain.errors import Conflict, InvalidRequest, NotFound
from app.domain.models import Actor, PendingAction
from app.repositories.interfaces import UnitOfWorkFactory

from .actions import ACTIONS, ActionContext
from .views import ConfirmResult, Proposal


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChangeService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Callable[[], datetime] = utc_now,
        ttl: timedelta = timedelta(minutes=15),
    ):
        self._uow = uow_factory
        self._clock = clock
        self._ttl = ttl

    async def propose(
        self, actor: Actor, action: str, params: dict, conversation_id: str | None = None
    ) -> Proposal:
        """Check the request and store it as 'pending'. Nothing is changed yet."""
        handler = ACTIONS.get(action)
        if handler is None:
            raise InvalidRequest(f"Unknown action '{action}'")
        async with self._uow() as uow:
            plan = await handler.plan(uow, actor, params)
            pending = PendingAction(
                token=str(uuid.uuid4()),
                actor_user_id=actor.user_id,
                conversation_id=conversation_id,
                action=action,
                params=plan.params,
                summary=plan.summary,
                status="pending",
                expires_at=self._clock() + self._ttl,
            )
            await uow.pending.add(pending)
            await uow.commit()
        return Proposal(pending.token, action, plan.summary, plan.details, plan.warnings, pending.expires_at)

    async def confirm(
        self, actor: Actor, token: str, source: str = "agent", conversation_id: str | None = None
    ) -> ConfirmResult:
        """Run a pending change. The token can only be used once. If `conversation_id` is given, the
        change must have been proposed in that same conversation.

        Claiming the token, re-checking, changing the data and writing history all happen in
        one transaction. If anything fails, the claim is rolled back with everything else."""
        async with self._uow() as uow:
            pending = await uow.pending.get(token)
            # Someone else's token looks exactly like a token that doesn't exist.
            if pending is None or pending.actor_user_id != actor.user_id:
                raise NotFound("Unknown confirmation request")
            if conversation_id is not None and pending.conversation_id != conversation_id:
                raise NotFound("Unknown confirmation request")

            claimed = await uow.pending.claim(token, self._clock())
            if claimed is None:
                # Lost the race or used before: re-read to see what happened.
                latest = await uow.pending.get(token)
                if latest.status == "confirmed" and latest.result is not None:
                    return ConfirmResult(latest.result, already_applied=True)
                if latest.status == "pending" or latest.expires_at <= self._clock():
                    raise Conflict("This confirmation has expired; please make the request again")
                raise Conflict(f"This request was already {latest.status}")

            handler = ACTIONS[claimed.action]
            plan = await handler.plan(uow, actor, claimed.params)  # state may have changed since propose
            result = await handler.apply(uow, actor, plan, ActionContext(source, claimed.conversation_id))
            await uow.pending.set_result(token, result)
            await uow.commit()
        return ConfirmResult(result, already_applied=False)

    async def cancel(self, actor: Actor, token: str, conversation_id: str | None = None) -> None:
        async with self._uow() as uow:
            pending = await uow.pending.get(token)
            if pending is None or pending.actor_user_id != actor.user_id:
                raise NotFound("Unknown confirmation request")
            if conversation_id is not None and pending.conversation_id != conversation_id:
                raise NotFound("Unknown confirmation request")
            if not await uow.pending.cancel(token):
                raise Conflict(f"This request was already {pending.status}")
            await uow.commit()
