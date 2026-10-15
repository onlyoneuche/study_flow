from datetime import datetime

from fastapi_users import schemas
from pydantic import ConfigDict, Field, StrictBool, computed_field, field_validator, model_validator

from app.db.types import utc_now
from app.models.enums import AgeBand, AudienceBand, EducationLevel, audience_for_level


class UserRead(schemas.BaseUser[int]):
    display_name: str
    level: EducationLevel
    age_band: AgeBand
    guardian_consent_at: datetime | None
    adult_confirmed_at: datetime | None

    @computed_field
    @property
    def audience_band(self) -> AudienceBand:
        return audience_for_level(self.level)


class UserCreate(schemas.BaseUserCreate):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    level: EducationLevel
    audience_band: AudienceBand
    guardian_consent: StrictBool = False
    adult_confirmation: StrictBool = False

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a display name")
        return value.strip()

    @model_validator(mode="after")
    def consent_and_band(self):
        expected = audience_for_level(self.level)
        if self.audience_band != expected:
            raise ValueError("Audience band must match the education level")
        if expected == AudienceBand.SECONDARY and not self.guardian_consent:
            raise ValueError("Parent or guardian consent is required for secondary levels")
        if expected == AudienceBand.TERTIARY and not self.adult_confirmation:
            raise ValueError("Confirm you are 18 or older for university and OTHER levels")
        return self

    def create_update_dict(self):
        data = super().create_update_dict()
        data.pop("audience_band", None)
        data.pop("guardian_consent", None)
        data.pop("adult_confirmation", None)
        secondary = self.audience_band == AudienceBand.SECONDARY
        data.update(
            age_band=AgeBand.UNDER_18 if secondary else AgeBand.ADULT,
            guardian_consent_at=utc_now() if secondary else None,
            adult_confirmed_at=None if secondary else utc_now(),
        )
        return data


class UserUpdate(schemas.CreateUpdateDictModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    level: EducationLevel | None = None
    guardian_consent: StrictBool = False
    adult_confirmation: StrictBool = False

    @field_validator("display_name", "level", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Profile fields cannot be null")
        if isinstance(value, str):
            value = value.strip()
        return value
