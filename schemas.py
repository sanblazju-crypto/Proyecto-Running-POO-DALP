from datetime import datetime
from typing import Optional, List, Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, model_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    disciplines: List[str] = []

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class RefreshRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


# ── Users ─────────────────────────────────────────────────────────────────────

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    disciplines: Optional[List[str]] = None

class UserPublic(BaseModel):
    id: UUID
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    disciplines: List[str] = []
    is_premium: bool = False
    created_at: datetime
    model_config = {"from_attributes": True}

class UserMe(UserPublic):
    email: str
    is_verified: bool

class UserProfile(UserPublic):
    followers_count: int = 0
    following_count: int = 0
    activities_count: int = 0
    is_following: bool = False


# ── Events ────────────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    discipline: str
    difficulty: Optional[str] = None
    date: datetime
    registration_deadline: Optional[datetime] = None
    location_name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    distance_km: Optional[float] = Field(None, gt=0)
    elevation_gain_m: Optional[float] = None
    max_participants: Optional[int] = Field(None, gt=0)
    registration_fee: Optional[float] = None
    currency: str = "EUR"
    website_url: Optional[str] = None
    organizer_name: Optional[str] = None
    tags: List[str] = []

class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    date: Optional[datetime] = None
    status: Optional[str] = None
    registration_deadline: Optional[datetime] = None
    max_participants: Optional[int] = None
    tags: Optional[List[str]] = None

class EventPublic(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    discipline: str
    difficulty: Optional[str] = None
    status: str
    date: datetime
    location_name: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    max_participants: Optional[int] = None
    registration_fee: Optional[float] = None
    currency: str
    cover_image_url: Optional[str] = None
    organizer_name: Optional[str] = None
    tags: List[str] = []
    participants_count: int = 0
    is_registered: bool = False
    model_config = {"from_attributes": True}


# ── Activities ────────────────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    discipline: str
    activity_type: str = "training"
    started_at: datetime
    duration_seconds: Optional[int] = Field(None, gt=0)
    distance_meters: Optional[float] = Field(None, gt=0)
    elevation_gain_m: Optional[float] = None
    avg_heart_rate: Optional[int] = Field(None, ge=40, le=250)
    max_heart_rate: Optional[int] = Field(None, ge=40, le=250)
    avg_power_watts: Optional[int] = None
    avg_cadence: Optional[int] = None
    calories_burned: Optional[int] = None
    perceived_effort: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None
    is_public: bool = True
    event_id: Optional[UUID] = None

class ActivityUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    perceived_effort: Optional[int] = Field(None, ge=1, le=10)
    is_public: Optional[bool] = None

class ActivityPublic(BaseModel):
    id: UUID
    title: str
    discipline: str
    activity_type: str
    started_at: datetime
    duration_seconds: Optional[int] = None
    distance_meters: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    avg_pace_sec_per_km: Optional[float] = None
    avg_speed_kmh: Optional[float] = None
    avg_heart_rate: Optional[int] = None
    calories_burned: Optional[int] = None
    perceived_effort: Optional[int] = None
    gpx_url: Optional[str] = None
    is_public: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Feed ──────────────────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    content: Optional[str] = Field(None, max_length=2000)
    post_type: str = "text"
    activity_id: Optional[UUID] = None
    is_public: bool = True

    @model_validator(mode="after")
    def content_or_activity(self):
        if not self.content and not self.activity_id:
            raise ValueError("Se requiere content o activity_id")
        return self

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    parent_id: Optional[UUID] = None

class CommentPublic(BaseModel):
    id: UUID
    content: str
    author: UserPublic
    created_at: datetime
    model_config = {"from_attributes": True}

class PostPublic(BaseModel):
    id: UUID
    post_type: str
    content: Optional[str] = None
    image_urls: List[str] = []
    likes_count: int
    comments_count: int
    is_public: bool
    created_at: datetime
    author: UserPublic
    activity: Optional[ActivityPublic] = None
    is_liked: bool = False
    model_config = {"from_attributes": True}


# ── Stats ─────────────────────────────────────────────────────────────────────

class UserStats(BaseModel):
    total_activities: int
    total_distance_km: float
    total_duration_hours: float
    total_elevation_gain_m: float
    total_calories: int
    activities_by_discipline: dict
    activities_by_month: List[dict]
    personal_bests: List[dict]
    avg_weekly_distance_km: float


# ── Teams ─────────────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str = Field(..., max_length=120)
    description: Optional[str] = None
    location: Optional[str] = None
    disciplines: List[str] = []
    is_public: bool = True

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    disciplines: Optional[List[str]] = None

class TeamPublic(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    location: Optional[str] = None
    disciplines: List[str] = []
    members_count: int = 0
    is_public: bool
    model_config = {"from_attributes": True}

class InviteMemberRequest(BaseModel):
    user_id: UUID
    role: str = "athlete"

class TrainingSessionCreate(BaseModel):
    week_number: int = Field(..., ge=1)
    day_of_week: int = Field(..., ge=0, le=6)
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    discipline: Optional[str] = None
    session_type: Optional[str] = None
    target_duration_minutes: Optional[int] = None
    target_distance_km: Optional[float] = None
    target_heart_rate_zone: Optional[int] = Field(None, ge=1, le=5)
    main_set_description: Optional[str] = None
    notes: Optional[str] = None

class TrainingPlanCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    discipline: Optional[str] = None
    difficulty: Optional[str] = None
    duration_weeks: Optional[int] = Field(None, ge=1, le=52)
    goal: Optional[str] = None
    starts_on: Optional[datetime] = None
    team_id: Optional[UUID] = None
    sessions: List[TrainingSessionCreate] = []

class TrainingPlanPublic(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    discipline: Optional[str] = None
    difficulty: Optional[str] = None
    duration_weeks: Optional[int] = None
    goal: Optional[str] = None
    status: str
    sessions_count: int = 0
    created_at: datetime
    model_config = {"from_attributes": True}

class AssignPlanRequest(BaseModel):
    athlete_ids: List[UUID]
    starts_on: datetime
    notes: Optional[str] = None


# ── AI ────────────────────────────────────────────────────────────────────────

class AIRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    discipline: Optional[str] = None
