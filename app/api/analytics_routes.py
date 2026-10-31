from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import current_actor
from app.api.schemas import ErrorResponse
from app.domain.errors import PermissionDenied
from app.domain.models import Actor, Role
from app.observability.request_log import RequestLogStore, Stats

router = APIRouter(prefix="/analytics", tags=["analytics"])


class TypeRow(BaseModel):
    request_type: str = Field(description="add, remove, transfer, show, search, missing_student, duplicate, off_topic, ...")
    count: int
    share: float = Field(description="Part of all requests, 0 to 1")
    outcomes: dict[str, int]


class TokenStats(BaseModel):
    input: int = Field(description="All input tokens, including the cached ones")
    output: int
    cached: int = Field(description="The part of the input served from the prompt cache")
    avg_per_request: float
    avg_per_conversation: float


class LatencyStats(BaseModel):
    p50_ms: float | None
    p95_ms: float | None


class AnalyticsResponse(BaseModel):
    since: datetime
    days: int
    total_requests: int
    conversations: int
    outcomes: dict[str, int] = Field(description="resolved, permission_denied, needs_clarification, out_of_scope, error")
    outcome_shares: dict[str, float]
    by_type: list[TypeRow] = Field(description="Most common first")
    most_common_type: str | None
    least_common_type: str | None
    tokens: TokenStats
    latency: LatencyStats


def to_response(stats: Stats, days: int) -> AnalyticsResponse:
    total = stats.total or 1  # avoid dividing by zero; every share is 0 anyway when there are no requests
    return AnalyticsResponse(
        since=stats.since, days=days, total_requests=stats.total, conversations=stats.conversations,
        outcomes=stats.outcomes,
        outcome_shares={outcome: round(count / total, 3) for outcome, count in stats.outcomes.items()},
        by_type=[TypeRow(request_type=t.request_type, count=t.count, share=round(t.count / total, 3), outcomes=t.outcomes)
                 for t in stats.by_type],
        most_common_type=stats.by_type[0].request_type if stats.by_type else None,
        least_common_type=stats.by_type[-1].request_type if stats.by_type else None,
        tokens=TokenStats(
            input=stats.input_tokens, output=stats.output_tokens, cached=stats.cached_tokens,
            avg_per_request=stats.avg_tokens_per_request, avg_per_conversation=stats.avg_tokens_per_conversation,
        ),
        latency=LatencyStats(p50_ms=stats.latency_p50_ms, p95_ms=stats.latency_p95_ms),
    )


def get_request_log(request: Request) -> RequestLogStore:
    return request.app.state.request_log


@router.get(
    "/requests",
    summary="What people ask the agent, and how it went",
    description="Every chat request is classified by type and outcome. This answers: which questions are most "
    "and least common, how many were resolved, how many hit permissions, how many needed a clarification, "
    "plus token use and response times. Superadmin only: it covers every school.",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def request_stats(
    days: int = Query(7, ge=1, le=90, description="How many days back to look"),
    actor: Actor = Depends(current_actor),
    request_log: RequestLogStore = Depends(get_request_log),
) -> AnalyticsResponse:
    if actor.role != Role.SUPERADMIN:
        raise PermissionDenied("Only a superadmin can view request analytics")
    since = datetime.now(UTC) - timedelta(days=days)
    return to_response(await request_log.stats(since), days)
