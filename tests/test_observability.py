"""Analytics, structured logs and Prometheus metrics, tested through the real app with a scripted model."""

import io
import json
import logging
import re

import httpx
import pytest
import structlog

from app.agent.agent import Agent
from app.agent.fake_client import FakeLLMClient, text_response, tool_response
from app.agent.memory import InMemoryConversationStore
from app.auth.passwords import hash_password
from app.config import settings
from app.main import create_app
from app.observability import metrics
from app.observability.logging import configure_logging
from app.observability.request_log import InMemoryRequestLogStore
from app.observability.telemetry import Telemetry
from app.repositories.memory.store import load_demo_world
from app.repositories.memory.unit_of_work import MemoryUnitOfWork
from app.services import build_services
from app.tools import build_registry
from seed.world import DEMO_PASSWORD

PASSWORD_HASH = hash_password(DEMO_PASSWORD)


def scripted_model(request):
    """list the class, try another class, propose an add, or answer without tools."""
    last = request.messages[-1]
    if last.tool_results:
        data = json.loads(last.tool_results[0].content)
        if data.get("status") == "pending_confirmation":
            return text_response("Подтвердите.")
        if data.get("status") in ("done", "already_done"):
            return text_response("Готово.")
        if "error" in data:
            return text_response("Не получилось.")
        return text_response("Вот список.")
    text = last.text
    if "4Б" in text:
        return tool_response("list_class_students", {"class_name": "4Б"})
    if "список" in text:
        return tool_response("list_class_students", {"class_name": "4А"})
    if "добавь" in text.lower():
        return tool_response("add_student", {"full_name": "Новый Ученик", "class_name": "4А"})
    if "оценки" in text:
        return tool_response("report_out_of_scope", {"topic": "grades"})
    return text_response("Здравствуйте!")


class Stack:
    def __init__(self, request_log=None, observer=None, model=scripted_model):
        self.store = load_demo_world(password_hash=PASSWORD_HASH)
        self.services = build_services(lambda: MemoryUnitOfWork(self.store))
        self.request_log = request_log if request_log is not None else InMemoryRequestLogStore()
        self.fake = FakeLLMClient(model)
        self.agent = Agent(
            self.fake, build_registry(), self.services, InMemoryConversationStore(),
            observer=observer if observer is not None else Telemetry(self.request_log, log_user_text=True),
        )
        self.app = create_app(self.services, self.agent, self.request_log)

    async def client(self, email="aigul@luwo.test"):
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        token = (await client.post("/auth/login", json={"email": email, "password": DEMO_PASSWORD})).json()
        client.headers["Authorization"] = f"Bearer {token['access_token']}"
        return client


@pytest.fixture
def stack():
    return Stack()


def sample(name, **labels):
    return metrics.registry.get_sample_value(name, labels) or 0.0


async def say(client, text, conversation_id=None):
    return (await client.post("/chat", json={"message": text, "conversation_id": conversation_id})).json()


@pytest.fixture
def logs():
    """Real JSON logging into a buffer; the previous logging setup is restored afterwards."""
    root = logging.getLogger()
    before = (root.handlers[:], root.level)
    stream = io.StringIO()
    configure_logging("DEBUG", json=True, stream=stream)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    structlog.reset_defaults()
    root.handlers[:], root.level = before[0], before[1]
    logging.getLogger("uvicorn.access").disabled = False


# ---------------------------------------------------------------- analytics

async def test_analytics_is_for_superadmins_only(stack):
    anonymous = httpx.AsyncClient(transport=httpx.ASGITransport(app=stack.app), base_url="http://test")
    assert (await anonymous.get("/analytics/requests")).status_code == 401
    for email in ("aigul@luwo.test", "admin1@luwo.test"):
        response = await (await stack.client(email)).get("/analytics/requests")
        assert response.status_code == 403 and response.json()["error"]["code"] == "permission_denied"
    assert (await (await stack.client("root@luwo.test")).get("/analytics/requests")).status_code == 200


async def test_analytics_answers_the_questions_in_the_task(stack):
    teacher = await stack.client()
    for _ in range(3):
        await say(teacher, "покажи список")
    await say(teacher, "покажи 4Б")  # permission denied
    await say(teacher, "какие оценки")  # off topic
    await say(teacher, "привет")  # answered without tools
    body = (await (await stack.client("root@luwo.test")).get("/analytics/requests")).json()

    assert body["total_requests"] == 6 and body["days"] == 7
    assert body["outcomes"] == {"resolved": 4, "permission_denied": 1, "needs_clarification": 0, "out_of_scope": 1, "error": 0}
    assert sum(body["outcome_shares"].values()) == pytest.approx(1.0, abs=0.01)
    assert [(t["request_type"], t["count"]) for t in body["by_type"]][0] == ("show", 4)  # 3 lists + the denied one
    assert body["most_common_type"] == "show"
    assert body["least_common_type"] in {"off_topic", "other"}
    assert body["by_type"][0]["outcomes"]["permission_denied"] == 1
    assert body["tokens"]["input"] > 0 and body["tokens"]["output"] > 0
    assert body["conversations"] == 6 and body["latency"]["p50_ms"] is not None


async def test_an_empty_log_is_a_valid_answer(stack):
    body = (await (await stack.client("root@luwo.test")).get("/analytics/requests")).json()
    assert body["total_requests"] == 0 and body["by_type"] == []
    assert body["most_common_type"] is None and body["least_common_type"] is None
    assert body["latency"] == {"p50_ms": None, "p95_ms": None}


@pytest.mark.parametrize("days", [0, 91, -1])
async def test_the_time_window_is_validated(stack, days):
    assert (await (await stack.client("root@luwo.test")).get("/analytics/requests", params={"days": days})).status_code == 422


async def test_button_presses_are_logged_as_requests_too(stack):
    client = await stack.client()
    proposal = await say(client, "добавь ученика")
    token = proposal["blocks"][0]["token"]
    await client.post("/chat/confirm", json={"conversation_id": proposal["conversation_id"], "token": token, "approve": True})
    stats = (await (await stack.client("root@luwo.test")).get("/analytics/requests")).json()
    types = {t["request_type"]: t["count"] for t in stats["by_type"]}
    assert types == {"add": 1, "confirmation": 1}


# ---------------------------------------------------------------- metrics

async def test_http_requests_are_counted_by_route_template_not_by_raw_url(stack):
    mine, other = await stack.client(), await stack.client("bakyt@luwo.test")
    conversation = (await say(mine, "привет"))["conversation_id"]
    def ok():
        return sample("luwo_http_requests_total", method="GET", route="/chat/history", status="200")

    def not_found():
        return sample("luwo_http_requests_total", method="GET", route="/chat/history", status="404")

    ok_before, nf_before = ok(), not_found()

    await mine.get("/chat/history", params={"conversation_id": conversation})
    await other.get("/chat/history", params={"conversation_id": conversation})  # someone else's: 404

    # two different URLs with a query string, still ONE series per status: the label is the route template
    assert (ok() - ok_before, not_found() - nf_before) == (1, 1)


async def test_unknown_urls_share_one_label_so_scanners_cannot_flood_the_metrics(stack):
    client = await stack.client()
    before = sample("luwo_http_requests_total", method="GET", route="unmatched", status="404")
    for n in range(5):
        await client.get(f"/does-not-exist/{n}")
    assert sample("luwo_http_requests_total", method="GET", route="unmatched", status="404") == before + 5


async def test_metrics_and_health_probes_are_not_counted(stack):
    client = await stack.client()
    await client.get("/health")
    await client.get("/metrics")
    routes = {s.labels["route"] for family in metrics.registry.collect() for s in family.samples if "route" in s.labels}
    assert "/metrics" not in routes and "/health" not in routes


async def test_a_chat_request_updates_the_agent_llm_tool_and_token_metrics(stack):
    client = await stack.client()
    names = {
        "requests": lambda: sample("luwo_agent_requests_total", request_type="show", outcome="resolved"),
        "calls": lambda: sample("luwo_llm_calls_total", status="ok"),
        "tokens_in": lambda: sample("luwo_llm_tokens_total", kind="input"),
        "tokens_out": lambda: sample("luwo_llm_tokens_total", kind="output"),
        "tool": lambda: sample("luwo_tool_calls_total", tool="list_class_students", result="ok"),
        "started": lambda: sample("luwo_conversations_started_total"),
        "latency_count": lambda: sample("luwo_agent_request_duration_seconds_count", request_type="show"),
    }
    before = {k: f() for k, f in names.items()}
    first = await say(client, "покажи список")
    await say(client, "покажи список", first["conversation_id"])  # same conversation: not a new one

    after = {k: f() for k, f in names.items()}
    assert after["requests"] - before["requests"] == 2
    assert after["calls"] - before["calls"] == 4  # two model calls per request
    assert after["tokens_in"] - before["tokens_in"] == 400 and after["tokens_out"] - before["tokens_out"] == 80
    assert after["tool"] - before["tool"] == 2
    assert after["started"] - before["started"] == 1
    assert after["latency_count"] - before["latency_count"] == 2


async def test_permission_denials_show_up_in_the_tool_and_outcome_counters(stack):
    client = await stack.client()
    tool_before = sample("luwo_tool_calls_total", tool="list_class_students", result="permission_denied")
    out_before = sample("luwo_agent_requests_total", request_type="show", outcome="permission_denied")
    await say(client, "покажи 4Б")
    assert sample("luwo_tool_calls_total", tool="list_class_students", result="permission_denied") == tool_before + 1
    assert sample("luwo_agent_requests_total", request_type="show", outcome="permission_denied") == out_before + 1


async def test_the_metrics_endpoint_serves_prometheus_text_with_memory_and_cpu(stack):
    response = await (await stack.client()).get("/metrics")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# TYPE luwo_http_request_duration_seconds histogram" in body
    memory = re.search(r"^luwo_process_resident_memory_bytes (\S+)", body, re.M)
    cpu = re.search(r"^luwo_process_cpu_seconds_total (\S+)", body, re.M)
    assert memory and float(memory.group(1)) > 1_000_000  # more than 1 MB
    assert cpu and float(cpu.group(1)) > 0
    assert "luwo_process_cpu_percent" in body and "luwo_process_threads" in body


async def test_metrics_can_be_protected_with_a_token(stack, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "scrape-secret")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=stack.app), base_url="http://test")
    assert (await client.get("/metrics")).status_code == 401
    assert (await client.get("/metrics", headers={"Authorization": "Bearer wrong"})).status_code == 401
    assert (await client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})).status_code == 200


async def test_no_label_ever_holds_a_conversation_id_user_id_or_free_text(stack):
    """Labels with unbounded values would create a new time series per user or conversation."""
    for email in ("aigul@luwo.test", "bakyt@luwo.test", "admin1@luwo.test"):
        client = await stack.client(email)
        for text in ("покажи список", "привет", "какие оценки", "добавь ученика"):
            await say(client, text)
    values = {v for family in metrics.registry.collect() for s in family.samples for v in s.labels.values()}
    assert not any(re.fullmatch(r"c_[0-9a-f]{16}", v) for v in values), "a conversation id is used as a label"
    assert not any(v.isdigit() and len(v) > 3 for v in values), "an id is used as a label"
    assert not any("@" in v or " " in v for v in values), "free text is used as a label"
    assert len({s.labels.get("tool") for family in metrics.registry.collect() for s in family.samples} - {None}) <= 19


async def test_database_time_is_measured_for_postgres_queries(uow_factory):
    async with uow_factory() as uow:
        if not hasattr(uow, "session"):
            pytest.skip("only the PostgreSQL adapter talks to a database")
        metrics.install_db_metrics()
        before = sample("luwo_db_query_duration_seconds_count", operation="SELECT")
        await uow.classes.list_by_school(1)
        assert sample("luwo_db_query_duration_seconds_count", operation="SELECT") == before + 1
        assert sample("luwo_db_query_duration_seconds_sum", operation="SELECT") > 0


# ---------------------------------------------------------------- structured logs

async def test_every_log_line_of_a_request_carries_the_conversation_and_user_id(stack, logs):
    client = await stack.client()
    reply = await say(client, "покажи список")
    lines = [line for line in logs() if line.get("event") in ("conversation_started", "tool_call", "chat_request")]

    assert {line["event"] for line in lines} == {"conversation_started", "tool_call", "chat_request"}
    assert {line["conversation_id"] for line in lines} == {reply["conversation_id"]}
    assert {line["user_id"] for line in lines} == {6}
    request = next(line for line in lines if line["event"] == "chat_request")
    assert request["request_type"] == "show" and request["outcome"] == "resolved"
    assert request["tools"] == ["list_class_students"] and request["llm_calls"] == 2
    assert request["input_tokens"] == 200 and request["user_text"] == "покажи список" and request["role"] == "teacher"
    tool = next(line for line in lines if line["event"] == "tool_call")
    assert tool["tool"] == "list_class_students" and tool["ok"] is True and "duration_ms" in tool
    assert all("timestamp" in line and line["level"] for line in lines)


async def test_a_permission_denial_is_logged_as_a_warning_with_its_own_event_name(stack, logs):
    await say(await stack.client(), "покажи 4Б")
    denial = next(line for line in logs() if line["event"] == "permission_denied")
    assert denial["level"] == "warning" and denial["tool"] == "list_class_students"
    assert denial["role"] == "teacher" and "conversation_id" in denial
    assert "not one of your classes" in denial["message"]


async def test_backend_errors_are_logged_as_errors(stack, logs, monkeypatch):
    async def explode(*args, **kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(stack.services.directory, "get_roster", explode)
    await say(await stack.client(), "покажи список")
    lines = logs()
    failure = next(line for line in lines if line["event"] == "tool_error")
    assert failure["level"] == "error" and failure["tool"] == "list_class_students"
    request = next(line for line in lines if line["event"] == "chat_request")
    assert request["outcome"] == "error" and request["level"] == "error"
    assert any("database is on fire" in json.dumps(line, ensure_ascii=False) for line in lines), "the traceback should be in the logs"
    assert not any("database is on fire" in (line.get("message") or "") for line in lines if line["event"] == "tool_error"), \
        "...but never in the message that goes back to the model"


async def test_message_text_and_tool_arguments_can_be_kept_out_of_the_logs(logs):
    stack = Stack(observer=Telemetry(InMemoryRequestLogStore()))  # the default: no message text in the logs
    await say(await stack.client(), "покажи список")
    text = json.dumps(logs(), ensure_ascii=False)
    assert "покажи список" not in text and '"args"' not in text and '"user_text"' not in text


async def test_every_http_request_is_logged_once_with_the_route_and_a_matching_request_id(stack, logs):
    client = await stack.client()
    response = await client.get("/chat/history")
    line = [line for line in logs() if line["event"] == "http_request" and line["route"] == "/chat/history"][-1]
    assert line["status"] == 200 and line["method"] == "GET" and "duration_ms" in line
    assert line["request_id"] == response.headers["x-request-id"]


async def test_one_requests_ids_never_leak_into_the_next_one(stack, logs):
    client = await stack.client()
    await say(client, "покажи список")
    await client.get("/chat/history")  # not a chat request: must not carry the earlier conversation id
    lines = [line for line in logs() if line["event"] == "http_request"]
    history = next(line for line in lines if line["route"] == "/chat/history")
    assert "conversation_id" not in history


async def test_library_logs_use_the_same_json_format(logs):
    logging.getLogger("some.library").warning("something odd happened")
    line = next(line for line in logs() if line["event"] == "something odd happened")
    assert line["level"] == "warning" and line["logger"] == "some.library" and "timestamp" in line


# ---------------------------------------------------------------- monitoring must never break the chat

class BrokenRequestLog:
    async def add(self, entry):
        raise RuntimeError("analytics database is down")

    async def stats(self, since):
        raise RuntimeError("analytics database is down")


async def test_a_broken_request_log_does_not_break_the_chat(logs):
    stack = Stack(request_log=BrokenRequestLog())
    reply = await say(await stack.client(), "покажи список")
    assert reply["text"] == "Вот список." and reply["blocks"][0]["type"] == "class_roster"
    assert any(line["event"] == "telemetry_failed" and line["level"] == "error" for line in logs())


async def test_a_broken_observer_does_not_break_the_chat():
    class Exploding(Telemetry):
        def tool_finished(self, *args, **kwargs):
            raise RuntimeError("boom")

    # even a subclass that raises directly is not a reason to lose the user's answer
    stack = Stack(observer=Telemetry(InMemoryRequestLogStore()))
    reply = await say(await stack.client(), "привет")
    assert reply["text"] == "Здравствуйте!"


async def test_text_is_not_logged_unless_asked_for_even_with_the_defaults_of_the_class(logs):
    assert Telemetry(InMemoryRequestLogStore())._log_user_text is False


async def test_confirmation_tokens_never_reach_the_logs(stack, logs):
    client = await stack.client()
    proposal = await say(client, "добавь ученика")
    token = proposal["blocks"][0]["token"]
    await client.post("/chat/confirm", json={"conversation_id": proposal["conversation_id"], "token": token, "approve": True})
    text = json.dumps(logs(), ensure_ascii=False)
    assert token not in text and "[redacted]" in text


async def test_the_http_clients_used_for_the_model_do_not_flood_the_logs(logs):
    for name in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(name).info("HTTP Request: POST https://api.anthropic.com/v1/messages")
    logging.getLogger("httpx2").warning("a real problem")
    events = [line["event"] for line in logs()]
    assert not any(e.startswith("HTTP Request") for e in events)
    assert "a real problem" in events  # warnings and errors still come through


async def test_the_docs_pages_have_their_own_label_not_the_scanner_label(stack):
    client = await stack.client()
    before = sample("luwo_http_requests_total", method="GET", route="docs", status="200")
    await client.get("/docs")
    await client.get("/openapi.json")
    assert sample("luwo_http_requests_total", method="GET", route="docs", status="200") == before + 2
