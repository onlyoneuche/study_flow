from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_active_user
from app.db.database import get_session
from app.db.types import utc_now
from app.models import Group, GroupMember, Invite, User
from app.models.enums import MemberRole, audience_for_level
from app.services.groups import (
    active_members,
    check_invite,
    fail,
    find_invite,
    group_count,
    group_view,
    invite_view,
    new_invite,
    require_group,
)

router = APIRouter()
DB = Annotated[AsyncSession, Depends(get_session)]
Learner = Annotated[User, Depends(current_active_user)]


class CreateGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    max_members: int = Field(default=8, ge=3, le=8, strict=True)


class CreateInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_uses: int = Field(ge=1, strict=True)


@router.get("/groups")
async def my_groups(request: Request, db: DB, user: Learner):
    groups = (
        await db.scalars(
            select(Group)
            .join(GroupMember)
            .where(
                GroupMember.user_id == user.id,
                GroupMember.left_at.is_(None),
                Group.is_active.is_(True),
            )
            .order_by(Group.id)
        )
    ).all()
    return [
        await group_view(db, g, user.id, str(request.app.state.settings.frontend_url))
        for g in groups
    ]


@router.post("/groups", status_code=201)
async def create_group(data: CreateGroup, request: Request, db: DB, user: Learner):
    if await group_count(db, user.id) >= 3:
        fail(
            "group_limit",
            "You can belong to at most 3 groups. Leave a group before creating another.",
        )
    group = Group(
        name=data.name,
        max_members=data.max_members,
        owner_id=user.id,
        audience_band=audience_for_level(user.level),
    )
    db.add(group)
    await db.flush()
    db.add(GroupMember(group_id=group.id, user_id=user.id, role=MemberRole.OWNER))
    await db.flush()
    await db.commit()
    return await group_view(db, group, user.id, str(request.app.state.settings.frontend_url))


@router.get("/groups/{group_id}")
async def get_group(group_id: int, request: Request, db: DB, user: Learner):
    group = await require_group(db, group_id, user.id)
    return await group_view(db, group, user.id, str(request.app.state.settings.frontend_url))


@router.post("/groups/{group_id}/invites", status_code=201)
async def create_invite(group_id: int, data: CreateInvite, request: Request, db: DB, user: Learner):
    group = await require_group(db, group_id, user.id, owner=True)
    invite = await new_invite(db, group, user.id, data.max_uses)
    await db.commit()
    return invite_view(invite, group, str(request.app.state.settings.frontend_url))


@router.delete("/invites/{code}", status_code=204)
async def disable_invite(code: str, db: DB, user: Learner):
    invite, group = await find_invite(db, code)
    await require_group(db, group.id, user.id, owner=True)
    invite.revoked_at = invite.revoked_at or utc_now()
    await db.commit()
    return Response(status_code=204)


@router.get("/invites/{code}")
async def preview_invite(code: str, db: DB):
    invite, group = await find_invite(db, code)
    check_invite(invite, group, utc_now())
    members = await active_members(db, group.id)
    if len(members) >= group.max_members:
        fail("full", "This group is full. Ask the owner to make a place for you.")
    return dict(name=group.name, member_count=len(members))


@router.post("/invites/{code}/accept")
async def accept_invite(code: str, db: DB, user: Learner):
    invite, group = await find_invite(db, code)
    members = await active_members(db, group.id)
    # Existing membership is an idempotent success, including reused, full or expired links.
    if group.is_active and any(m.user_id == user.id for m in members):
        return dict(group_id=group.id, already_member=True)
    check_invite(invite, group, utc_now())
    if audience_for_level(user.level) != group.audience_band:
        fail(
            "wrong_band",
            "This group is in a different audience band. "
            "Secondary learners and university/adult learners cannot join the same group.",
            403,
        )
    if len(members) >= group.max_members:
        fail("full", "This group is full. Ask the owner to make a place for you.")
    if await group_count(db, user.id) >= 3:
        fail(
            "group_limit",
            "You can belong to at most 3 groups. Leave a group before joining another.",
        )
    db.add(GroupMember(group_id=group.id, user_id=user.id, role=MemberRole.MEMBER))
    invite.uses += 1
    await db.commit()
    return dict(group_id=group.id, already_member=False)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
async def leave_or_remove(group_id: int, user_id: int, db: DB, user: Learner):
    group = await require_group(db, group_id, user.id, owner=user.id != user_id)
    members = await active_members(db, group.id)
    member = next((m for m in members if m.user_id == user_id), None)
    if not member:
        fail("not_member", "This person is no longer a member.", 404)
    now = utc_now()
    member.left_at = now
    member.removed_by = user.id if user.id != user_id else None
    if user_id == group.owner_id:
        remaining = [m for m in members if m.user_id != user_id]
        if remaining:
            group.owner_id = remaining[0].user_id
            remaining[0].role = MemberRole.OWNER
        else:
            # TODO: confirm empty-group lifecycle; retain history and close joins for now.
            group.is_active = False
            invites = (await db.scalars(select(Invite).where(Invite.group_id == group.id))).all()
            for invite in invites:
                invite.revoked_at = invite.revoked_at or now
    await db.commit()
    return Response(status_code=204)
