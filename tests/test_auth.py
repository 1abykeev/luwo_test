"""Login and tokens, through the real HTTP layer (in-memory data, real password hashing)."""

from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.auth.passwords import hash_password
from app.auth.tokens import ALGORITHM
from app.config import settings
from app.main import create_app
from app.repositories.memory.store import load_demo_world
from app.repositories.memory.unit_of_work import MemoryUnitOfWork
from app.services import build_services
from seed.world import DEMO_PASSWORD
from tests.helpers import user_id

PASSWORD_HASH = hash_password(DEMO_PASSWORD)  # hashed once: bcrypt is deliberately slow


@pytest.fixture
def store():
    return load_demo_world(password_hash=PASSWORD_HASH)


@pytest.fixture
async def client(store):
    app = create_app(build_services(lambda: MemoryUnitOfWork(store)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def login(client, email="aigul@luwo.test", password=DEMO_PASSWORD):
    return await client.post("/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_login_returns_a_token_and_the_profile(client):
    response = await login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == {
        "user_id": user_id("aigul@luwo.test"), "full_name": "Айгуль Садыкова", "role": "teacher",
        "school_name": "Лицей №1", "class_names": ["4А"],
    }


async def test_email_is_not_case_sensitive(client):
    assert (await login(client, email=" AIGUL@luwo.test ")).status_code == 200


async def test_every_login_failure_looks_the_same(client):
    wrong_password = await login(client, password="wrong")
    unknown_email = await login(client, email="nobody@luwo.test")
    removed_teacher = await login(client, email="gulmira@luwo.test")  # correct password, removed account
    too_long = await login(client, password="x" * 100)

    for response in (wrong_password, unknown_email, removed_teacher, too_long):
        assert response.status_code == 401
        assert response.json() == wrong_password.json()
    assert wrong_password.json()["error"]["code"] == "authentication_failed"


async def test_me_requires_a_valid_token(client):
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/auth/me", headers=bearer("garbage"))).status_code == 401


async def test_me_works_with_a_token(client):
    token = (await login(client, "root@luwo.test")).json()["access_token"]
    response = await client.get("/auth/me", headers=bearer(token))
    assert response.status_code == 200
    assert response.json()["role"] == "superadmin" and response.json()["school_name"] is None


async def test_expired_token_is_rejected(client):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(user_id("aigul@luwo.test")), "iat": past - timedelta(hours=1), "exp": past},
        settings.jwt_secret, algorithm=ALGORITHM,
    )
    assert (await client.get("/auth/me", headers=bearer(token))).status_code == 401


async def test_token_signed_with_another_secret_is_rejected(client):
    token = jwt.encode({"sub": str(user_id("root@luwo.test"))}, "some-other-secret", algorithm=ALGORITHM)
    assert (await client.get("/auth/me", headers=bearer(token))).status_code == 401


async def test_unsigned_token_is_rejected(client):
    token = jwt.encode({"sub": str(user_id("root@luwo.test"))}, key=None, algorithm="none")
    assert (await client.get("/auth/me", headers=bearer(token))).status_code == 401


async def test_a_role_claim_inside_the_token_changes_nothing(client):
    # Even a correctly signed token cannot promote its owner: the role is read from the database.
    forged = jwt.encode(
        {"sub": str(user_id("aigul@luwo.test")), "role": "superadmin", "school_id": None,
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.jwt_secret, algorithm=ALGORITHM,
    )
    body = (await client.get("/auth/me", headers=bearer(forged))).json()
    assert body["role"] == "teacher" and body["school_name"] == "Лицей №1"


async def test_a_token_stops_working_when_the_account_is_removed(client, store):
    token = (await login(client, "nurlan@luwo.test")).json()["access_token"]
    assert (await client.get("/auth/me", headers=bearer(token))).status_code == 200

    async with MemoryUnitOfWork(store) as uow:  # the admin removes the teacher
        await uow.teachers.set_active(user_id("nurlan@luwo.test"), False)
        await uow.commit()
    assert (await client.get("/auth/me", headers=bearer(token))).status_code == 401


async def test_health_and_docs_are_public(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/openapi.json")).status_code == 200
    assert (await client.get("/docs")).status_code == 200
