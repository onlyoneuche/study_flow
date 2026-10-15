import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import lagos_date, lagos_week_start
from app.db.types import utc_now
from app.models import (
    Group,
    GroupMember,
    GroupStreak,
    Invite,
    PointsLedger,
    SessionParticipant,
    StreakFreeze,
    User,
)
from app.models.enums import ParticipantStatus

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def fail(code: str, message: str, status: int = 409):
    raise HTTPException(status, detail={"code": code, "reason": message})


async def active_members(db: AsyncSession, group_id: int):
    return list(
        (
            await db.scalars(
                select(GroupMember)
                .where(GroupMember.group_id == group_id, GroupMember.left_at.is_(None))
                .order_by(GroupMember.joined_at, GroupMember.id)
            )
        ).all()
    )


async def group_count(db: AsyncSession, user_id: int):
    return await db.scalar(
        select(func.count())
        .select_from(GroupMember)
        .where(GroupMember.user_id == user_id, GroupMember.left_at.is_(None))
    )


async def require_group(db: AsyncSession, group_id: int, user_id: int, owner=False):
    group = await db.get(Group, group_id)
    member = await db.scalar(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
            GroupMember.left_at.is_(None),
        )
    )
    if not group or not group.is_active or not member:
        fail("not_member", "This group is available to its current members only.", 403)
    if owner and group.owner_id != user_id:
        fail("owner_only", "Only the group owner can do this.", 403)
    return group


async def find_invite(db: AsyncSession, code: str):
    invite = await db.scalar(select(Invite).where(Invite.code == code.upper()))
    if not invite:
        fail("not_found", "This invite link was not found. Check the code with your friend.", 404)
    return invite, await db.get(Group, invite.group_id)


def check_invite(invite: Invite, group: Group, now):
    if invite.revoked_at or not group.is_active:
        fail("disabled", "This invite has been disabled. Ask the owner for a new link.", 410)
    if now >= invite.expires_at:
        fail("expired", "This invite has expired. Ask the owner for a new link.", 410)
    if invite.uses >= invite.max_uses:
        fail("used_up", "This invite has reached its use limit. Ask the owner for a new link.", 410)


def invite_view(invite: Invite, group: Group, frontend_url: str):
    url = f"{frontend_url.rstrip('/')}/join/{invite.code}"
    return dict(
        code=invite.code,
        url=url,
        expires_at=invite.expires_at,
        max_uses=invite.max_uses,
        uses=invite.uses,
        revoked_at=invite.revoked_at,
        whatsapp_url="https://wa.me/?"
        + urlencode({"text": f"Join {group.name} on StudyFlow! Let’s study together. {url}"}),
    )


async def new_invite(db: AsyncSession, group: Group, user_id: int, max_uses: int):
    now = utc_now()
    old = (
        await db.scalars(
            select(Invite).where(Invite.group_id == group.id, Invite.revoked_at.is_(None))
        )
    ).all()
    for invite in old:
        invite.revoked_at = now
    # BEGIN IMMEDIATE makes code collision checks and insertion atomic.
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        if not await db.scalar(select(Invite.id).where(Invite.code == code)):
            break
    invite = Invite(
        group_id=group.id,
        code=code,
        created_by=user_id,
        created_at=now,
        expires_at=now + timedelta(days=7),
        max_uses=max_uses,
    )
    db.add(invite)
    await db.flush()
    return invite


async def group_view(db: AsyncSession, group: Group, user_id: int, frontend_url: str):
    members = await active_members(db, group.id)
    users = (await db.scalars(select(User).where(User.id.in_([m.user_id for m in members])))).all()
    names = {u.id: u for u in users}
    now = utc_now()
    week = lagos_week_start(now)
    points = await db.scalar(
        select(func.coalesce(func.sum(PointsLedger.points), 0)).where(
            PointsLedger.group_id == group.id, PointsLedger.week_start == week
        )
    )
    freezes = await db.scalar(
        select(func.count())
        .select_from(StreakFreeze)
        .where(StreakFreeze.group_id == group.id, StreakFreeze.week_start == week)
    )
    completed = await db.scalar(
        select(func.count())
        .select_from(SessionParticipant)
        .where(
            SessionParticipant.user_id.in_(list(names)),
            SessionParticipant.session_date == lagos_date(now),
            SessionParticipant.status == ParticipantStatus.COMPLETED,
        )
    )
    streak = await db.scalar(select(GroupStreak).where(GroupStreak.group_id == group.id))
    invite = None
    if group.owner_id == user_id:
        invite = await db.scalar(
            select(Invite)
            .where(Invite.group_id == group.id, Invite.revoked_at.is_(None))
            .order_by(Invite.id.desc())
            .limit(1)
        )
    return dict(
        id=group.id,
        name=group.name,
        owner_id=group.owner_id,
        audience_band=group.audience_band,
        max_members=group.max_members,
        member_count=len(members),
        members=[
            dict(
                user_id=m.user_id,
                display_name=names[m.user_id].display_name,
                level=names[m.user_id].level,
                role=m.role,
                joined_at=m.joined_at,
            )
            for m in members
        ],
        weekly_points=points,
        weekly_target=100 * len(members),
        week_start=week,
        streak=streak.current if streak else 0,
        streak_paused=len(members) < 3,
        freezes_remaining=2 - freezes,
        completed_today=completed,
        invite=invite_view(invite, group, frontend_url) if invite else None,
    )
