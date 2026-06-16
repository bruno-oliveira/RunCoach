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
    resting_hr: Optional[int] = None
    threshold_hr: Optional[int] = None


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
    # Resting heart rate (BPM) for Heart Rate Reserve zone math. Send 0/null to
    # clear and revert to the data-derived estimate.
    resting_hr: Optional[int] = Field(default=None, ge=0, le=120)
    # Lactate-threshold heart rate (BPM) for re-anchoring the zone bands. Send
    # 0/null to clear and revert to the data-derived estimate.
    threshold_hr: Optional[int] = Field(default=None, ge=0, le=220)
