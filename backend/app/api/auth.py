from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import (
    auth_backend,
    current_active_user,
    fastapi_users,
    get_user_manager,
)
from app.auth.manager import UserManager
from app.auth.schemas import UserCreate, UserRead, UserUpdate
from app.models import User

router = APIRouter()
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth")
router.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt")
router.include_router(fastapi_users.get_verify_router(UserRead), prefix="/auth")
router.include_router(fastapi_users.get_reset_password_router(), prefix="/auth")


@router.get("/users/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(current_active_user)]):
    return user


@router.patch("/users/me", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    request: Request,
    user: Annotated[User, Depends(current_active_user)],
    manager: Annotated[UserManager, Depends(get_user_manager)],
):
    return await manager.update(data, user, safe=True, request=request)
