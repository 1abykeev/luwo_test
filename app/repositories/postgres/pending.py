import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.models import PendingAction


def _to_domain(row: m.PendingAction) -> PendingAction:
    return PendingAction(
        token=str(row.token),
        actor_user_id=row.actor_user_id,
        conversation_id=row.conversation_id,
        action=row.action,
        params=row.params,
        summary=row.summary,
        status=row.status,
        expires_at=row.expires_at,
        result=row.result,
    )


def _parse_token(token: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(token)
    except ValueError:
        return None


class PostgresPendingActionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, action: PendingAction) -> None:
        self.session.add(
            m.PendingAction(
                token=uuid.UUID(action.token),
                actor_user_id=action.actor_user_id,
                conversation_id=action.conversation_id,
                action=action.action,
                params=action.params,
                summary=action.summary,
                status=action.status,
                expires_at=action.expires_at,
            )
        )
        await self.session.flush()

    async def get(self, token: str) -> PendingAction | None:
        parsed = _parse_token(token)
        # populate_existing: always re-read, never trust a cached copy (matters after a lost claim)
        row = await self.session.get(m.PendingAction, parsed, populate_existing=True) if parsed else None
        return _to_domain(row) if row else None

    async def claim(self, token: str, now: datetime) -> PendingAction | None:
        parsed = _parse_token(token)
        if parsed is None:
            return None
        # One UPDATE decides the winner: only a row that is still 'pending' and not expired matches.
        row = (
            await self.session.execute(
                update(m.PendingAction)
                .where(
                    m.PendingAction.token == parsed,
                    m.PendingAction.status == "pending",
                    m.PendingAction.expires_at > now,
                )
                .values(status="confirmed", executed_at=now)
                .returning(m.PendingAction)
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def set_result(self, token: str, result: dict) -> None:
        await self.session.execute(
            update(m.PendingAction).where(m.PendingAction.token == uuid.UUID(token)).values(result=result)
        )

    async def cancel(self, token: str) -> bool:
        parsed = _parse_token(token)
        if parsed is None:
            return False
        row = (
            await self.session.execute(
                update(m.PendingAction)
                .where(m.PendingAction.token == parsed, m.PendingAction.status == "pending")
                .values(status="cancelled")
                .returning(m.PendingAction.token)
            )
        ).scalar_one_or_none()
        return row is not None
