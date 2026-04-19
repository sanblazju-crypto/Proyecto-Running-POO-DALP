import uuid, enum
from datetime import datetime
from sqlalchemy import (Column, String, Text, Boolean, Integer, Float,
                        DateTime, ForeignKey, Enum, JSON, Table,
                        UniqueConstraint, Index, Numeric)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class Discipline(str, enum.Enum):
    RUNNING = "running"; CYCLING = "cycling"; TRAIL = "trail"
    TRIATHLON = "triathlon"; SWIMMING = "swimming"; OTHER = "other"

class Difficulty(str, enum.Enum):
    BEGINNER = "beginner"; INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"; ELITE = "elite"

class EventStatus(str, enum.Enum):
    UPCOMING = "upcoming"; ONGOING = "ongoing"
    FINISHED = "finished"; CANCELLED = "cancelled"

class ActivityType(str, enum.Enum):
    TRAINING = "training"; RACE = "race"; LONG_RUN = "long_run"
    INTERVAL = "interval"; RECOVERY = "recovery"

class PostType(str, enum.Enum):
    ACTIVITY = "activity"; RACE_RESULT = "race_result"
    TEXT = "text"; IMAGE = "image"

class TeamRole(str, enum.Enum):
    COACH = "coach"; ATHLETE = "athlete"; SUPPORT = "support"

class PlanStatus(str, enum.Enum):
    DRAFT = "draft"; ACTIVE = "active"; COMPLETED = "completed"


# ── Association tables ────────────────────────────────────────────────────────

user_follows = Table("user_follows", Base.metadata,
    Column("follower_id",  UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("following_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

event_participants = Table("event_participants", Base.metadata,
    Column("user_id",  UUID(as_uuid=True), ForeignKey("users.id"),   primary_key=True),
    Column("event_id", UUID(as_uuid=True), ForeignKey("events.id"),  primary_key=True),
    Column("registered_at", DateTime(timezone=True), server_default=func.now()),
    Column("bib_number", String(20)),
)

post_likes = Table("post_likes", Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"),  primary_key=True),
    Column("post_id", UUID(as_uuid=True), ForeignKey("posts.id"),  primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    username        = Column(String(60),  unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)
    full_name       = Column(String(120))
    bio             = Column(Text)
    avatar_url      = Column(String(500))
    location        = Column(String(120))
    disciplines     = Column(ARRAY(String), default=list)
    is_active       = Column(Boolean, default=True)
    is_verified     = Column(Boolean, default=False)
    is_premium      = Column(Boolean, default=False)
    is_superuser    = Column(Boolean, default=False)
    oauth_provider    = Column(String(30))
    oauth_provider_id = Column(String(255))
    strava_id         = Column(String(50), nullable=True, index=True)
    preferences     = Column(JSON, default=dict)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at   = Column(DateTime(timezone=True))

    activities      = relationship("Activity",     back_populates="user", cascade="all, delete-orphan")
    posts           = relationship("Post",         back_populates="author", cascade="all, delete-orphan")
    comments        = relationship("Comment",      back_populates="author", cascade="all, delete-orphan")
    event_results   = relationship("EventResult",  back_populates="user")
    personal_bests  = relationship("PersonalBest", back_populates="user", cascade="all, delete-orphan")
    team_memberships = relationship("TeamMember",  back_populates="user")
    refresh_tokens  = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    followers = relationship("User", secondary=user_follows,
        primaryjoin=id == user_follows.c.following_id,
        secondaryjoin=id == user_follows.c.follower_id, backref="following")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token      = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked    = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user       = relationship("User", back_populates="refresh_tokens")


class Event(Base):
    __tablename__ = "events"
    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug                  = Column(String(200), unique=True, nullable=False, index=True)
    name                  = Column(String(200), nullable=False)
    description           = Column(Text)
    discipline            = Column(Enum(Discipline), nullable=False)
    difficulty            = Column(Enum(Difficulty))
    status                = Column(Enum(EventStatus), default=EventStatus.UPCOMING)
    date                  = Column(DateTime(timezone=True), nullable=False)
    registration_deadline = Column(DateTime(timezone=True))
    location_name         = Column(String(200))
    city                  = Column(String(100))
    country               = Column(String(100))
    latitude              = Column(Numeric(9, 6))
    longitude             = Column(Numeric(9, 6))
    distance_km           = Column(Float)
    elevation_gain_m      = Column(Float)
    max_participants      = Column(Integer)
    registration_fee      = Column(Numeric(8, 2))
    currency              = Column(String(3), default="EUR")
    website_url           = Column(String(500))
    cover_image_url       = Column(String(500))
    organizer_name        = Column(String(200))
    tags                  = Column(ARRAY(String), default=list)
    created_by_id         = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at            = Column(DateTime(timezone=True), server_default=func.now())

    participants = relationship("User", secondary=event_participants, backref="registered_events")
    results      = relationship("EventResult", back_populates="event", cascade="all, delete-orphan")
    activities   = relationship("Activity",    back_populates="event")

    __table_args__ = (
        Index("ix_events_geo",   "latitude", "longitude"),
        Index("ix_events_disc",  "discipline", "date"),
    )


class Activity(Base):
    __tablename__ = "activities"
    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id              = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id             = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    title                = Column(String(200), nullable=False)
    description          = Column(Text)
    discipline           = Column(Enum(Discipline), nullable=False)
    activity_type        = Column(Enum(ActivityType), default=ActivityType.TRAINING)
    started_at           = Column(DateTime(timezone=True), nullable=False)
    duration_seconds     = Column(Integer)
    moving_time_seconds  = Column(Integer)
    distance_meters      = Column(Float)
    elevation_gain_m     = Column(Float)
    avg_pace_sec_per_km  = Column(Float)
    avg_speed_kmh        = Column(Float)
    avg_heart_rate       = Column(Integer)
    max_heart_rate       = Column(Integer)
    avg_power_watts      = Column(Integer)
    avg_cadence          = Column(Integer)
    calories_burned      = Column(Integer)
    perceived_effort     = Column(Integer)
    gpx_url              = Column(String(500))
    strava_activity_id   = Column(String(50), nullable=True, index=True)
    splits               = Column(JSON, default=list)
    notes                = Column(Text)
    is_public            = Column(Boolean, default=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())

    user  = relationship("User",  back_populates="activities")
    event = relationship("Event", back_populates="activities")
    post  = relationship("Post",  back_populates="activity", uselist=False)

    __table_args__ = (Index("ix_activities_user_date", "user_id", "started_at"),)


class Post(Base):
    __tablename__ = "posts"
    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id      = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    activity_id    = Column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=True)
    post_type      = Column(Enum(PostType), default=PostType.TEXT)
    content        = Column(Text)
    image_urls     = Column(ARRAY(String), default=list)
    is_public      = Column(Boolean, default=True)
    likes_count    = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    author   = relationship("User",     back_populates="posts")
    activity = relationship("Activity", back_populates="post")
    comments = relationship("Comment",  back_populates="post", cascade="all, delete-orphan")
    liked_by = relationship("User", secondary=post_likes, backref="liked_posts")

    __table_args__ = (Index("ix_posts_author_created", "author_id", "created_at"),)


class Comment(Base):
    __tablename__ = "comments"
    id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id   = Column(UUID(as_uuid=True), ForeignKey("posts.id",    ondelete="CASCADE"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id",    ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("comments.id"), nullable=True)
    content   = Column(Text, nullable=False)
    created_at= Column(DateTime(timezone=True), server_default=func.now())

    post    = relationship("Post",    back_populates="comments")
    author  = relationship("User",    back_populates="comments")
    replies = relationship("Comment", backref="parent", remote_side=[id])


class EventResult(Base):
    __tablename__ = "event_results"
    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id          = Column(UUID(as_uuid=True), ForeignKey("events.id",  ondelete="CASCADE"), nullable=False)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.id"),  nullable=False)
    finish_time_seconds = Column(Integer)
    overall_position  = Column(Integer)
    category_position = Column(Integer)
    category          = Column(String(50))
    dnf               = Column(Boolean, default=False)
    dns               = Column(Boolean, default=False)
    split_times       = Column(JSON, default=dict)
    official          = Column(Boolean, default=False)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("Event", back_populates="results")
    user  = relationship("User",  back_populates="event_results")
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_result_user"),)


class PersonalBest(Base):
    __tablename__ = "personal_bests"
    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    discipline     = Column(Enum(Discipline), nullable=False)
    distance_label = Column(String(30), nullable=False)
    distance_meters= Column(Float, nullable=False)
    time_seconds   = Column(Integer, nullable=False)
    achieved_at    = Column(DateTime(timezone=True), nullable=False)
    activity_id    = Column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="personal_bests")
    __table_args__ = (UniqueConstraint("user_id", "discipline", "distance_label", name="uq_pb"),)


# ── Premium / Teams ───────────────────────────────────────────────────────────

class Team(Base):
    __tablename__ = "teams"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name         = Column(String(120), nullable=False)
    slug         = Column(String(150), unique=True, nullable=False, index=True)
    description  = Column(Text)
    logo_url     = Column(String(500))
    location     = Column(String(120))
    disciplines  = Column(ARRAY(String), default=list)
    is_public    = Column(Boolean, default=True)
    created_by_id= Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    members        = relationship("TeamMember",    back_populates="team", cascade="all, delete-orphan")
    training_plans = relationship("TrainingPlan",  back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"
    id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id   = Column(UUID(as_uuid=True), ForeignKey("teams.id",  ondelete="CASCADE"), nullable=False)
    user_id   = Column(UUID(as_uuid=True), ForeignKey("users.id",  ondelete="CASCADE"), nullable=False)
    role      = Column(Enum(TeamRole), default=TeamRole.ATHLETE)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id        = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    created_by_id  = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name           = Column(String(200), nullable=False)
    description    = Column(Text)
    discipline     = Column(Enum(Discipline))
    difficulty     = Column(Enum(Difficulty))
    duration_weeks = Column(Integer)
    goal           = Column(String(300))
    status         = Column(Enum(PlanStatus), default=PlanStatus.DRAFT)
    starts_on      = Column(DateTime)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    team     = relationship("Team",            back_populates="training_plans")
    sessions = relationship("TrainingSession", back_populates="plan", cascade="all, delete-orphan")
    assignments = relationship("PlanAssignment", back_populates="plan", cascade="all, delete-orphan")


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    id                     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id                = Column(UUID(as_uuid=True), ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False)
    week_number            = Column(Integer, nullable=False)
    day_of_week            = Column(Integer, nullable=False)
    title                  = Column(String(200), nullable=False)
    description            = Column(Text)
    discipline             = Column(Enum(Discipline))
    session_type           = Column(Enum(ActivityType))
    target_duration_minutes= Column(Integer)
    target_distance_km     = Column(Float)
    target_heart_rate_zone = Column(Integer)
    target_pace_sec_per_km = Column(Float)
    main_set_description   = Column(Text)
    notes                  = Column(Text)
    order                  = Column(Integer, default=0)

    plan = relationship("TrainingPlan", back_populates="sessions")


class PlanAssignment(Base):
    __tablename__ = "plan_assignments"
    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id        = Column(UUID(as_uuid=True), ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False)
    athlete_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assigned_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    starts_on      = Column(DateTime, nullable=False)
    notes          = Column(Text)
    assigned_at    = Column(DateTime(timezone=True), server_default=func.now())

    plan = relationship("TrainingPlan", back_populates="assignments")
    __table_args__ = (UniqueConstraint("plan_id", "athlete_id", name="uq_plan_assignment"),)


class Notification(Base):
    __tablename__ = "notifications"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type       = Column(String(50), nullable=False)
    title      = Column(String(200))
    message    = Column(Text)
    data       = Column(JSON, default=dict)
    read       = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_notif_user_read", "user_id", "read"),)
