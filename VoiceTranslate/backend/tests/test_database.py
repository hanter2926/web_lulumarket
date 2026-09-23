import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import Call, CallParticipant, Contact, Device, User, UserPreference


async def make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_models_create_and_relationships() -> None:
    async def scenario() -> None:
        engine, session_factory = await make_session()
        async with session_factory() as session:
            user = User(email="owner@example.com", password_hash="hashed", display_name="Owner")
            device = Device(device_name="Phone", platform="android", user=user)
            preference = UserPreference(user=user)
            call = Call(initiator=user)
            participant = CallParticipant(call=call, user=user)
            session.add_all([user, device, preference, call, participant])
            await session.commit()

            result = await session.scalar(select(User).where(User.email == "owner@example.com"))
            assert result is not None
            assert result.devices[0].platform == "android"
            assert result.preference is not None
            assert result.initiated_calls[0].participants[0].user_id == result.id
        await engine.dispose()

    asyncio.run(scenario())


def test_unique_constraints_are_enforced() -> None:
    async def scenario() -> None:
        engine, session_factory = await make_session()
        async with session_factory() as session:
            owner = User(email="owner@example.com", password_hash="hashed", display_name="Owner")
            contact_user = User(email="contact@example.com", password_hash="hashed", display_name="Contact")
            session.add_all([owner, contact_user])
            await session.flush()
            session.add(Contact(owner_id=owner.id, contact_user_id=contact_user.id))
            await session.flush()
            session.add(Contact(owner_id=owner.id, contact_user_id=contact_user.id))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
        await engine.dispose()

    asyncio.run(scenario())


def test_cascade_deletes_children() -> None:
    async def scenario() -> None:
        engine, session_factory = await make_session()
        user_id = uuid4()
        async with session_factory() as session:
            user = User(id=user_id, email="owner@example.com", password_hash="hashed", display_name="Owner")
            session.add(Call(initiator=user))
            await session.commit()
            await session.delete(user)
            await session.commit()
            assert await session.scalar(select(Call).where(Call.initiator_id == user_id)) is None
        await engine.dispose()

    asyncio.run(scenario())
