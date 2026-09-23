import asyncio
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("JWT_SECRET_KEY", "test-only-websocket-secret")

from app.db.base import Base
from app.main import app as fastapi_app
from app.models.call import Call
from app.models.call_participant import CallParticipant
from app.models.user import User
from app.services.auth_service import issue_tokens
from app.utils.security import create_token
import app.websocket.handlers as websocket_handlers
from app.ai.whisper.service import Transcript
from app.websocket.manager import connection_manager
from app.db.session import async_session_factory as production_session_factory


class FakeSTTService:
    def __init__(self, settings) -> None:
        self.settings = settings

    def transcribe(self, audio: bytes) -> Transcript:
        return Transcript("test transcript", "en", 0.99, len(audio) / 32000, [{"start": 0.0, "end": 0.1, "text": "test transcript"}])


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
    websocket_handlers.async_session_factory = session_factory
    websocket_handlers.stt_service_factory = FakeSTTService
    yield session_factory
    websocket_handlers.async_session_factory = production_session_factory
    asyncio.run(engine.dispose())


@pytest.fixture(autouse=True)
def reset_database(database):
    async def reset_schema() -> None:
        async with database() as session:
            await session.close()
        async with session.bind.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(reset_schema())
    yield


@pytest.fixture
def scenario(database):
    async def seed():
        async with database() as session:
            owner = User(email="owner@example.com", password_hash="unused", display_name="Owner")
            participant = User(email="participant@example.com", password_hash="unused", display_name="Participant")
            outsider = User(email="outsider@example.com", password_hash="unused", display_name="Outsider")
            call = Call(initiator=owner)
            call.participants.append(CallParticipant(user=participant))
            session.add_all([owner, participant, outsider, call])
            await session.commit()
            return call.id, issue_tokens(owner), issue_tokens(participant), issue_tokens(outsider)

    return asyncio.run(seed())


def websocket_path(call_id, token: str) -> str:
    return f"/ws/calls/{call_id}?token={token}"


def test_authenticated_connection_lifecycle_and_ping(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "connection.ready"
            assert ready["call_id"] == str(call_id)
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}
            assert asyncio.run(connection_manager.connection_count(str(call_id))) == 1
        assert asyncio.run(connection_manager.connection_count(str(call_id))) == 0


def test_unauthenticated_and_invalid_jwt_are_rejected(database, scenario) -> None:
    call_id, _, _, _ = scenario
    with TestClient(fastapi_app) as client:
        for path in (f"/ws/calls/{call_id}", websocket_path(call_id, "invalid")):
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect(path):
                    pass
            assert error.value.code == 1008


def test_invalid_call_id_and_missing_call_are_rejected(database, scenario) -> None:
    _, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        for path in (
            websocket_path("not-a-uuid", owner_tokens.access_token),
            websocket_path(uuid4(), owner_tokens.access_token),
        ):
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect(path):
                    pass
            assert error.value.code == 1008


def test_call_participant_is_allowed_but_outsider_is_rejected(database, scenario) -> None:
    call_id, _, participant_tokens, outsider_tokens = scenario
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, participant_tokens.access_token)) as websocket:
            assert websocket.receive_json()["type"] == "connection.ready"
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(websocket_path(call_id, outsider_tokens.access_token)):
                pass
        assert error.value.code == 1008


def test_malformed_messages_and_language_change_validation(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            websocket.receive_json()
            websocket.send_text("not json")
            assert websocket.receive_json()["code"] == "INVALID_MESSAGE"
            websocket.send_json({"type": "unsupported"})
            assert websocket.receive_json()["code"] == "INVALID_MESSAGE"
            websocket.send_json({"type": "language.change", "language": "xx"})
            assert websocket.receive_json()["code"] == "INVALID_MESSAGE"
            websocket.send_json({"type": "language.change", "language": "HI"})
            assert websocket.receive_json() == {"type": "language.changed", "language": "hi"}


def test_multiple_connections_and_disconnect_cleanup(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        first = client.websocket_connect(websocket_path(call_id, owner_tokens.access_token))
        second = client.websocket_connect(websocket_path(call_id, owner_tokens.access_token))
        first.__enter__()
        second.__enter__()
        assert first.receive_json()["type"] == "connection.ready"
        assert second.receive_json()["type"] == "connection.ready"
        assert asyncio.run(connection_manager.connection_count(str(call_id))) == 2
        first.__exit__(None, None, None)
        assert asyncio.run(connection_manager.connection_count(str(call_id))) == 1
        second.__exit__(None, None, None)
        assert asyncio.run(connection_manager.connection_count(str(call_id))) == 0


def test_audio_chunk_before_start_is_rejected(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            websocket.receive_json()
            websocket.send_bytes(b"\x00\x00")
            response = websocket.receive_json()
            assert response["code"] == "AUDIO_NOT_STARTED"


def test_audio_lifecycle_buffers_and_clears_audio(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "audio.start", "sample_rate": 16000, "channels": 1, "sample_width": 2})
            assert websocket.receive_json()["type"] == "audio.ready"
            websocket.send_bytes(b"\x00\x00" * 160)
            assert websocket.receive_json() == {"type": "audio.received", "bytes": "320"}
            websocket.send_json({"type": "audio.end"})
            assert websocket.receive_json() == {"type": "audio.ended", "bytes": "320"}


def test_audio_start_rejects_unsupported_format_and_invalid_transitions(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "audio.end"})
            assert websocket.receive_json()["code"] == "AUDIO_NOT_STARTED"
            websocket.send_json({"type": "audio.start", "sample_rate": 8000, "channels": 1, "sample_width": 2})
            assert websocket.receive_json()["code"] == "UNSUPPORTED_AUDIO_FORMAT"
            websocket.send_json({"type": "audio.start", "sample_rate": 16000, "channels": 1, "sample_width": 2})
            assert websocket.receive_json()["type"] == "audio.ready"
            websocket.send_json({"type": "audio.start", "sample_rate": 16000, "channels": 1, "sample_width": 2})
            assert websocket.receive_json()["code"] == "INVALID_AUDIO_STATE"


def test_audio_protocol_messages_are_strict(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "audio.start", "sample_rate": 16000, "channels": 1, "sample_width": 2, "extra": True})
            assert websocket.receive_json()["code"] == "INVALID_MESSAGE"
            websocket.send_bytes(b"\x00")
            assert websocket.receive_json()["code"] == "AUDIO_NOT_STARTED"


def test_audio_buffers_are_isolated_per_connection(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    with TestClient(fastapi_app) as client:
        first = client.websocket_connect(websocket_path(call_id, owner_tokens.access_token))
        second = client.websocket_connect(websocket_path(call_id, owner_tokens.access_token))
        first.__enter__()
        second.__enter__()
        assert first.receive_json()["type"] == "connection.ready"
        assert second.receive_json()["type"] == "connection.ready"
        for websocket in (first, second):
            websocket.send_json({"type": "audio.start", "sample_rate": 16000, "channels": 1, "sample_width": 2})
            assert websocket.receive_json()["type"] == "audio.ready"
        first.send_bytes(b"\x00\x00" * 2)
        assert first.receive_json()["bytes"] == "4"
        second.send_json({"type": "audio.end"})
        assert second.receive_json() == {"type": "audio.ended", "bytes": "0"}
        first.__exit__(None, None, None)
        second.__exit__(None, None, None)


def test_websocket_emits_speech_started_and_ended_events(database, scenario) -> None:
    call_id, owner_tokens, _, _ = scenario
    speech_frame = b"\xff\x7f" * 320
    silence_frame = b"\x00\x00" * 320
    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "audio.start", "sample_rate": 16000, "channels": 1, "sample_width": 2})
            assert websocket.receive_json()["type"] == "audio.ready"
            for _ in range(9):
                websocket.send_bytes(speech_frame)
                assert websocket.receive_json()["type"] == "audio.received"
            websocket.send_bytes(speech_frame)
            assert websocket.receive_json()["type"] == "audio.received"
            assert websocket.receive_json()["type"] == "speech.started"
            for _ in range(14):
                websocket.send_bytes(silence_frame)
                assert websocket.receive_json()["type"] == "audio.received"
            websocket.send_bytes(silence_frame)
            assert websocket.receive_json()["type"] == "audio.received"
            ended = websocket.receive_json()
            assert ended["type"] == "speech.ended"
            assert ended["duration_ms"] >= 200
            assert ended["bytes"] > 0
            transcript = websocket.receive_json()
            assert transcript["type"] == "transcript.final"
            assert transcript["text"] == "test transcript"


def test_websocket_returns_safe_stt_failure(database, scenario, monkeypatch) -> None:
    call_id, owner_tokens, _, _ = scenario

    class FailingSTTService(FakeSTTService):
        def transcribe(self, audio: bytes) -> Transcript:
            from app.ai.whisper.service import WhisperSTTError

            raise WhisperSTTError("internal details")

    monkeypatch.setattr(websocket_handlers, "stt_service_factory", FailingSTTService)
    speech_frame = b"\xff\x7f" * 320
    silence_frame = b"\x00\x00" * 320

    with TestClient(fastapi_app) as client:
        with client.websocket_connect(websocket_path(call_id, owner_tokens.access_token)) as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "audio.start", "sample_rate": 16000, "channels": 1, "sample_width": 2})
            websocket.receive_json()
            for _ in range(10):
                websocket.send_bytes(speech_frame)
                websocket.receive_json()
                if _ == 9:
                    assert websocket.receive_json()["type"] == "speech.started"
            for _ in range(15):
                websocket.send_bytes(silence_frame)
                websocket.receive_json()
            ended = websocket.receive_json()
            assert ended["type"] == "speech.ended"
            assert websocket.receive_json() == {
                "type": "error",
                "code": "STT_FAILED",
                "message": "Speech transcription failed.",
            }
