from typing import Annotated

from fastapi import Depends, Request
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.manager import UserDatabase, UserManager
from app.db.database import get_session
from app.models import User


async def get_user_db(session: Annotated[AsyncSession, Depends(get_session)]):
    yield UserDatabase(session, User)


async def get_user_manager(
    request: Request, user_db: Annotated[UserDatabase, Depends(get_user_db)]
):
    yield UserManager(user_db, request.app.state.settings)


def get_jwt_strategy(request: Request) -> JWTStrategy:
    settings = request.app.state.settings
    return JWTStrategy(
        secret=settings.auth_secret, lifetime_seconds=settings.auth_token_lifetime_seconds
    )


bearer_transport = BearerTransport(tokenUrl="api/v1/auth/jwt/login")
auth_backend = AuthenticationBackend(
    name="jwt", transport=bearer_transport, get_strategy=get_jwt_strategy
)
fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(active=True)
