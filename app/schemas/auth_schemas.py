"""Pydantic schemas for authentication and user management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None


class UserCreate(UserBase):
    google_id: str


class UserResponse(UserBase):
    id: str
    google_id: Optional[str] = None
    created_at: datetime
    plans_generated: int
    strava_connected: bool = False
    intervals_connected: bool = False
    age: Optional[int] = None
    max_hr: Optional[int] = None
    resting_hr: Optional[int] = None
    threshold_hr: Optional[int] = None
    nudge_email_enabled: bool = False


class AuthResponse(BaseModel):
    message: str = "authenticated"
    user: UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., description="Google OAuth ID token")


class UserSettingsUpdate(BaseModel):
    # Age (years), used to estimate max HR when none is detected or supplied.
    # Send 0/null to clear.
    age: Optional[int] = Field(default=None, ge=0, le=120)
    # Max heart rate (BPM). Anchors the top of the zones directly. Send 0/null to
    # clear and revert to detection / the age formula.
    max_hr: Optional[int] = Field(default=None, ge=0, le=230)
    # Resting heart rate (BPM). Raises the Zone 1 floor. Send 0/null to clear.
    resting_hr: Optional[int] = Field(default=None, ge=0, le=120)
    # Lactate-threshold heart rate (BPM), the primary zone anchor. Send 0/null to
    # clear and revert to the data-derived estimate.
    threshold_hr: Optional[int] = Field(default=None, ge=0, le=220)
    # Consent for outbound coaching emails. Unlike the numeric fields above,
    # null means "leave it alone" rather than "clear it" — this is a boolean,
    # so false is a real value the runner can choose.
    nudge_email_enabled: Optional[bool] = None
