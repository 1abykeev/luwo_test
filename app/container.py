"""The composition root: the ONE place that decides which data source is plugged in.

Everything above this file (API, agent, tools, services) only sees the UnitOfWork
interface. To connect Luwo's real backend, write a unit of work that calls their REST API
or MCP server and add one branch below. No other file changes."""

from app.agent.agent import Agent
from app.agent.factory import build_llm_client
from app.agent.memory import ConversationStore, InMemoryConversationStore, PostgresConversationStore
from app.auth.passwords import hash_password
from app.config import settings
from app.repositories.interfaces import UnitOfWorkFactory
from app.repositories.memory.store import load_demo_world
from app.repositories.memory.unit_of_work import MemoryUnitOfWork
from app.repositories.postgres.unit_of_work import PostgresUnitOfWork
from app.observability.request_log import InMemoryRequestLogStore, PostgresRequestLogStore, RequestLogStore
from app.observability.telemetry import Telemetry
from app.services import Services, build_services
from app.tools import build_registry
from seed.world import DEMO_PASSWORD


def build_uow_factory() -> UnitOfWorkFactory:
    if settings.data_source == "memory":
        store = load_demo_world(password_hash=hash_password(DEMO_PASSWORD))
        return lambda: MemoryUnitOfWork(store)
    if settings.data_source == "postgres":
        return PostgresUnitOfWork
    raise ValueError(f"Unknown DATA_SOURCE '{settings.data_source}'")


def build_conversation_store() -> ConversationStore:
    """Chat history is the agent's own state, so it is NOT part of the swappable lists data source."""
    if settings.data_source == "memory":
        return InMemoryConversationStore()
    return PostgresConversationStore()


def build_request_log() -> RequestLogStore:
    """Analytics rows are the agent's own state too, so they are not part of the swappable lists data source."""
    if settings.data_source == "memory":
        return InMemoryRequestLogStore()
    return PostgresRequestLogStore()


def build_app() -> tuple[Services, Agent, RequestLogStore]:
    """Everything the API needs, wired once. The services and the agent share one data source."""
    services = build_services(build_uow_factory())
    request_log = build_request_log()
    agent = Agent(
        build_llm_client(), build_registry(), services, build_conversation_store(),
        deadline_seconds=settings.agent_timeout_seconds,
        observer=Telemetry(request_log, log_user_text=settings.log_user_text),
    )
    return services, agent, request_log
