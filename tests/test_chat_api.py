"""The chat endpoints over real HTTP, with a scripted fake model and the in-memory data."""

import json

import httpx
import pytest

from app.agent.agent import Agent
from app.agent.fake_client import FakeLLMClient, text_response, tool_response
from app.agent.memory import InMemoryConversationStore
from app.auth.passwords import hash_password
from app.main import create_app
from app.repositories.memory.store import load_demo_world
from app.repositories.memory.unit_of_work import MemoryUnitOfWork
from app.services import build_services
from app.tools import build_registry
from seed.world import DEMO_PASSWORD

PASSWORD_HASH = hash_password(DEMO_PASSWORD)


def model(request):
    """A tiny scripted model: lists a class, proposes an add, or says hello."""
    last = request.messages[-1]
    if last.tool_results:
        data = json.loads(last.tool_results[0].content)
        if data.get("status") == "pending_confirmation":
            return text_response("Добавить ученика? Подтвердите.")
        if data.get("status") in ("done", "already_done"):  # the backend's answer to the Confirm button
            return text_response("Готово, ученик добавлен.")
        if "error" in data:
            return text_response("Не получилось: " + data["message"])
        return text_response("Вот список.")
    text = last.text
    if "список" in text:
        return tool_response("list_class_students", {"class_name": "4А"})
    if "добавь" in text.lower():
        return tool_response("add_student", {"full_name": "Новый Ученик", "class_name": "4А"})
    if "4Б" in text:
        return tool_response("list_class_students", {"class_name": "4Б"})
    return text_response("Здравствуйте!")


@pytest.fixture
def client_factory():
    store = load_demo_world(password_hash=PASSWORD_HASH)
    services = build_services(lambda: MemoryUnitOfWork(store))
    agent = Agent(FakeLLMClient(model), build_registry(), services, InMemoryConversationStore())
    app = create_app(services, agent)

    async def make(email="aigul@luwo.test"):
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        token = (await client.post("/auth/login", json={"email": email, "password": DEMO_PASSWORD})).json()
        client.headers["Authorization"] = f"Bearer {token['access_token']}"
        return client

    return make


async def send(client, message, conversation_id=None):
    return await client.post("/chat", json={"message": message, "conversation_id": conversation_id})


async def test_chat_returns_text_cards_and_meta(client_factory):
    client = await client_factory()
    response = await send(client, "покажи список")
    assert response.status_code == 200
    body = response.json()

    assert body["text"] == "Вот список."
    assert body["conversation_id"].startswith("c_")
    assert body["blocks"][0]["type"] == "class_roster"
    assert body["blocks"][0]["class"] == "4А" and len(body["blocks"][0]["students"]) == 5
    assert body["meta"]["request_type"] == "show" and body["meta"]["outcome"] == "resolved"
    assert body["meta"]["input_tokens"] > 0


async def test_chat_needs_a_token(client_factory):
    client = await client_factory()
    del client.headers["Authorization"]
    assert (await send(client, "привет")).status_code == 401
    assert (await client.get("/chat/history")).status_code == 401


async def test_a_permission_denial_comes_back_as_a_banner_not_data(client_factory):
    client = await client_factory()
    body = (await send(client, "покажи 4Б")).json()
    assert body["meta"]["outcome"] == "permission_denied"
    assert [b["type"] for b in body["blocks"]] == ["banner"] and body["blocks"][0]["level"] == "error"
    assert "Нурсултан" not in json.dumps(body, ensure_ascii=False)  # no student of 4Б leaked


async def test_the_confirm_button_flow_over_http(client_factory):
    client = await client_factory()
    proposal = (await send(client, "добавь ученика")).json()
    card = proposal["blocks"][0]
    assert card["type"] == "confirmation" and card["token"]

    confirmed = await client.post("/chat/confirm", json={
        "conversation_id": proposal["conversation_id"], "token": card["token"], "approve": True})
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["text"] == "Готово, ученик добавлен."
    assert body["blocks"][0]["type"] == "result" and body["blocks"][0]["status"] == "done"

    again = (await client.post("/chat/confirm", json={
        "conversation_id": proposal["conversation_id"], "token": card["token"], "approve": True})).json()
    assert again["blocks"][0]["status"] == "already_done"

    roster = (await send(client, "покажи список")).json()["blocks"][0]["students"]
    assert [s["full_name"] for s in roster].count("Новый Ученик") == 1


async def test_history_returns_the_conversation_with_cards(client_factory):
    client = await client_factory()
    first = (await send(client, "покажи список")).json()
    await send(client, "привет", first["conversation_id"])

    history = (await client.get("/chat/history", params={"conversation_id": first["conversation_id"]})).json()
    assert [(m["role"], m["text"]) for m in history["messages"]] == [
        ("user", "покажи список"), ("assistant", "Вот список."), ("user", "привет"), ("assistant", "Здравствуйте!"),
    ]
    assert history["messages"][1]["blocks"][0]["type"] == "class_roster"

    latest = (await client.get("/chat/history")).json()  # no id = the most recent conversation
    assert latest["conversation_id"] == first["conversation_id"] and len(latest["messages"]) == 4


async def test_history_is_empty_for_a_new_user(client_factory):
    client = await client_factory("nurlan@luwo.test")
    assert (await client.get("/chat/history")).json() == {"conversation_id": None, "messages": []}


async def test_other_users_cannot_read_or_continue_my_conversation(client_factory):
    mine = await client_factory("aigul@luwo.test")
    theirs = await client_factory("bakyt@luwo.test")
    conversation = (await send(mine, "покажи список")).json()["conversation_id"]

    assert (await theirs.get("/chat/history", params={"conversation_id": conversation})).status_code == 404
    assert (await send(theirs, "привет", conversation)).status_code == 404
    stolen = await theirs.post("/chat/confirm", json={"conversation_id": conversation, "token": "x", "approve": True})
    assert stolen.status_code == 404


async def test_an_invented_conversation_id_is_refused(client_factory):
    client = await client_factory()
    assert (await send(client, "привет", "c_made_up")).status_code == 404


async def test_bad_input_is_rejected_before_it_reaches_the_agent(client_factory):
    client = await client_factory()
    assert (await send(client, "")).status_code == 422
    assert (await send(client, "я" * 2001)).status_code == 422
    assert (await send(client, "привет", "bad id with spaces")).status_code == 422
    assert (await client.post("/chat", json={})).status_code == 422


async def test_the_chat_contract_is_documented(client_factory):
    client = await client_factory()
    spec = (await client.get("/openapi.json")).json()
    description = spec["paths"]["/chat"]["post"]["description"]
    for block in ["class_roster", "confirmation", "banner", "investigation"]:
        assert block in description
    assert {"/chat", "/chat/confirm", "/chat/history"} <= set(spec["paths"])
