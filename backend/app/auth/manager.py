from urllib.parse import urlencode

from fastapi import HTTPException, Request
from fastapi_users import BaseUserManager, IntegerIDMixin, exceptions
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.exc import IntegrityError

from app.auth.schemas import UserCreate, UserUpdate
from app.core.config import Settings
from app.db.types import utc_now
from app.models import User
from app.models.enums import AgeBand, AudienceBand, audience_for_level


class UserDatabase(SQLAlchemyUserDatabase[User, int]):
    async def create(self, create_dict):
        try:
            return await super().create(create_dict)
        except IntegrityError as error:
            await self.session.rollback()
            if "users.email" in str(error.orig):
                raise exceptions.UserAlreadyExists() from error
            raise

    async def update(self, user, update_dict):
        try:
            return await super().update(user, update_dict)
        except IntegrityError as error:
            await self.session.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "This level change conflicts with your squads. Leave or transfer them first."
                ),
            ) from error


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    def __init__(self, user_db: UserDatabase, settings: Settings):
        super().__init__(user_db)
        self.settings = settings
        self.reset_password_token_secret = settings.auth_secret
        self.verification_token_secret = settings.auth_secret
        self.reset_password_token_lifetime_seconds = settings.auth_email_token_lifetime_seconds
        self.verification_token_lifetime_seconds = settings.auth_email_token_lifetime_seconds

    async def validate_password(self, password: str, user: UserCreate | User) -> None:
        if not 8 <= len(password) <= 128:
            raise exceptions.InvalidPasswordException("Use a password between 8 and 128 characters")

    async def on_after_register(self, user: User, request: Request | None = None):
        await self.request_verify(user, request)

    def console_email(self, user: User, token: str, action: str, subject: str) -> None:
        origin = str(self.settings.frontend_url).rstrip("/")
        url = f"{origin}/auth/{action}#{urlencode({'token': token})}"
        # Explicit console delivery for this local hackathon. Never return tokens via HTTP.
        print(f"\n[StudyFlow email]\nTo: {user.email}\nSubject: {subject}\n\n{url}\n", flush=True)

    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None):
        self.console_email(user, token, "verify", "Verify your StudyFlow email")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ):
        self.console_email(user, token, "reset-password", "Reset your StudyFlow password")

    async def update(self, user_update: UserUpdate, user: User, safe=False, request=None):
        data = user_update.create_update_dict()
        guardian = data.pop("guardian_consent", False)
        adult = data.pop("adult_confirmation", False)
        level = data.get("level", user.level)
        secondary = audience_for_level(level) == AudienceBand.SECONDARY
        if secondary:
            if user.guardian_consent_at is None and not guardian:
                raise HTTPException(422, "Parent or guardian consent is required for this level")
            if guardian and user.guardian_consent_at is None:
                data["guardian_consent_at"] = utc_now()
        else:
            if user.adult_confirmed_at is None and not adult:
                raise HTTPException(422, "Confirm you are 18 or older for this level")
            if adult and user.adult_confirmed_at is None:
                data["adult_confirmed_at"] = utc_now()
        data["age_band"] = AgeBand.UNDER_18 if secondary else AgeBand.ADULT
        updated = await self._update(user, data)
        await self.on_after_update(updated, data, request)
        return updated
