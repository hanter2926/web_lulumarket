import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-that-is-long-enough")

from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
import app.models  # noqa: F401


@pytest.fixture(scope="module")
def database():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def reset_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(reset_schema())

    async def override_session():
        async with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    yield engine
    fastapi_app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


@pytest.fixture(autouse=True)
def reset_database(database) -> None:
    async def reset_schema() -> None:
        async with database.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(reset_schema())


def client(database) -> TestClient:
    return TestClient(fastapi_app)


def register_user(test_client: TestClient, email: str = "user@example.com") -> dict:
    response = test_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPass1", "display_name": "Test User"},
    )
    assert response.status_code == 201
    return response.json()


def login_user(test_client: TestClient, email: str = "user@example.com") -> dict:
    response = test_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "StrongPass1"}
    )
    assert response.status_code == 200
    return response.json()


def test_successful_registration(database) -> None:
    with client(database) as test_client:
        user = register_user(test_client)
        assert user["email"] == "user@example.com"
        assert "password_hash" not in user


def test_duplicate_email_rejected(database) -> None:
    with client(database) as test_client:
        register_user(test_client)
        response = test_client.post(
            "/api/v1/auth/register",
            json={"email": "USER@example.com", "password": "StrongPass1", "display_name": "Other"},
        )
        assert response.status_code == 409


def test_invalid_password_rejected(database) -> None:
    with client(database) as test_client:
        response = test_client.post(
            "/api/v1/auth/register",
            json={"email": "weak@example.com", "password": "weakpass", "display_name": "Weak"},
        )
        assert response.status_code == 422


def test_successful_and_invalid_login(database) -> None:
    with client(database) as test_client:
        register_user(test_client)
        tokens = login_user(test_client)
        assert tokens["token_type"] == "bearer"
        assert tokens["access_token"]
        invalid = test_client.post(
            "/api/v1/auth/login", json={"email": "user@example.com", "password": "WrongPass1"}
        )
        assert invalid.status_code == 401


def test_current_user_requires_valid_access_token(database) -> None:
    with client(database) as test_client:
        assert test_client.get("/api/v1/users/me").status_code == 401
        register_user(test_client)
        tokens = login_user(test_client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        response = test_client.get("/api/v1/users/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["email"] == "user@example.com"
        assert test_client.get("/api/v1/users/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_refresh_token_and_invalid_refresh_token(database) -> None:
    with client(database) as test_client:
        register_user(test_client)
        tokens = login_user(test_client)
        refreshed = test_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refreshed.status_code == 200
        invalid = test_client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"})
        assert invalid.status_code == 401


def test_logout_invalidates_existing_tokens(database) -> None:
    with client(database) as test_client:
        register_user(test_client)
        tokens = login_user(test_client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        response = test_client.post("/api/v1/auth/logout", headers=headers)
        assert response.status_code == 200
        assert test_client.get("/api/v1/users/me", headers=headers).status_code == 401
        assert test_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code == 401


def test_health_endpoints_remain_available(database) -> None:
    with client(database) as test_client:
        assert test_client.get("/health").status_code == 200
        assert test_client.get("/health/live").status_code == 200
        assert test_client.get("/health/ready").status_code == 200
