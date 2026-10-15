import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import anyio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi_users.authentication import JWTStrategy
from sqlalchemy import select

from app.auth.manager import UserDatabase, UserManager
from app.models import StudySession, User
from app.models.enums import SessionStatus
from app.services.sessions import (
    REACTIONS,
    advance_session,
    heartbeat,
    participant_for,
    require_session,
    session_view,
)


class PrivateSocketToken:
    """Keep query credentials out of Uvicorn's accepted/closed socket path logs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            query = parse_qs(scope.get("query_string", b"").decode())
            scope.setdefault("state", {})["socket_token"] = query.get("token", [None])[0]
            scope["query_string"] = b""
        await self.app(scope, receive, send)


@dataclass(eq=False)
class Connection:
    socket: WebSocket
    user_id: int
    token: str
    display_name: str
    last_reaction: float = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, data):
        async with self.lock:
            await self.socket.send_json(jsonable_encoder(data))


class Presence:
    def __init__(self, app):
        self.app = app
        self.rooms: dict[int, set[Connection]] = {}
        self.scheduler = AsyncIOScheduler(timezone="Africa/Lagos")

    @asynccontextmanager
    async def database(self):
        # Shield the short transaction as well as close: cancellation during aiosqlite I/O
        # can invalidate its connection before rollback has a chance to return it to the pool.
        with anyio.CancelScope(shield=True):
            async with self.app.state.database.session_factory() as db:
                yield db

    async def authenticate(self, db, token):
        config = self.app.state.settings
        strategy = JWTStrategy(
            secret=config.auth_secret, lifetime_seconds=config.auth_token_lifetime_seconds
        )
        manager = UserManager(UserDatabase(db, User), config)
        user = await strategy.read_token(token, manager)
        if not user or not user.is_active:
            raise HTTPException(401)
        return user

    async def tick(self):
        # This also catches up scheduled/running sessions after a process restart.
        async with self.database() as db:
            await db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
            sessions = (
                await db.scalars(
                    select(StudySession).where(
                        StudySession.status.in_([SessionStatus.SCHEDULED, SessionStatus.RUNNING])
                    )
                )
            ).all()
            now = self.app.state.clock()
            for session in sessions:
                await advance_session(db, session, now)
            await db.commit()
        for session_id in list(self.rooms):
            await self.publish(session_id)

    async def snapshot(self, session_id, connection, beat=False):
        async with self.database() as db:
            if beat:
                await db.connection(execution_options={"sqlite_transaction_mode": "IMMEDIATE"})
            user = await self.authenticate(db, connection.token)
            session = await require_session(db, session_id, user.id)
            now = self.app.state.clock()
            if beat:
                participant = await participant_for(db, session_id, user.id)
                if participant:
                    heartbeat(session, participant, now)
                await advance_session(db, session, now)
                await db.commit()
            data = await session_view(db, session, user.id, now)
            present = {m["user_id"] for m in data["members"]}
            for other in self.rooms.get(session_id, set()):
                if other.user_id not in present:
                    data["members"].append(
                        dict(
                            user_id=other.user_id,
                            display_name=other.display_name,
                            subject="",
                            status="observing",
                        )
                    )
                    present.add(other.user_id)
            return data

    async def publish(self, session_id):
        for connection in list(self.rooms.get(session_id, set())):
            try:
                data = await self.snapshot(session_id, connection)
                await connection.send({"type": "state", **data})
                await connection.send({"type": "presence", "members": data["members"]})
                await connection.send({"type": "goal", **data["goal"]})
                mine = data["mine"]
                if mine and mine["quiz_unlocked"] and mine["quiz_status"] == "ready":
                    await connection.send({"type": "quiz_ready"})
                if data["status"] == "ended":
                    await connection.send({"type": "session_ended"})
            except HTTPException as error:
                await connection.socket.close(code=4401 if error.status_code == 401 else 4403)
                self.rooms.get(session_id, set()).discard(connection)
            except (RuntimeError, WebSocketDisconnect, OSError):
                self.rooms.get(session_id, set()).discard(connection)

    async def connect(self, socket: WebSocket, session_id: int):
        origin = socket.headers.get("origin")
        if origin and origin not in self.app.state.settings.cors_origins:
            await socket.close(code=4403)
            return
        token = socket.scope.get("state", {}).get("socket_token")
        try:
            async with self.database() as db:
                user = await self.authenticate(db, token)
                await require_session(db, session_id, user.id)
                connection = Connection(socket, user.id, token, user.display_name)
        except HTTPException as error:
            await socket.close(code=4401 if error.status_code == 401 else 4403)
            return
        await socket.accept()
        self.rooms.setdefault(session_id, set()).add(connection)
        try:
            await self.publish(session_id)
            while True:
                raw = await socket.receive_text()
                if len(raw) > 1024:
                    await connection.send({"type": "error", "message": "Message too large."})
                    continue
                try:
                    data = json.loads(raw)
                except ValueError:
                    await connection.send({"type": "error", "message": "Send a JSON event."})
                    continue
                if not isinstance(data, dict):
                    continue
                # Every event rechecks credentials and membership, including owner removals.
                await self.snapshot(session_id, connection, beat=data.get("type") == "heartbeat")
                if data.get("type") == "heartbeat":
                    await self.publish(session_id)
                elif data.get("type") == "react" and data.get("emoji") in REACTIONS:
                    now = asyncio.get_running_loop().time()
                    if now - connection.last_reaction >= 2:
                        connection.last_reaction = now
                        for other in list(self.rooms.get(session_id, set())):
                            await other.send(
                                {"type": "reaction", "user_id": user.id, "emoji": data["emoji"]}
                            )
                else:
                    await connection.send(
                        {"type": "error", "message": "Use a heartbeat or a supported reaction."}
                    )
        except HTTPException as error:
            await socket.close(code=4401 if error.status_code == 401 else 4403)
        except (RuntimeError, WebSocketDisconnect, OSError):
            pass
        finally:
            self.rooms.get(session_id, set()).discard(connection)
            if not self.rooms.get(session_id):
                self.rooms.pop(session_id, None)

    async def start(self):
        await self.tick()
        self.scheduler.add_job(self.tick, "interval", seconds=1, max_instances=1, coalesce=True)
        self.scheduler.start()

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
