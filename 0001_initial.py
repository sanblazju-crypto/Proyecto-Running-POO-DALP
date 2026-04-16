"""Initial migration - create all tables

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(60), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(120)),
        sa.Column("bio", sa.Text),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("location", sa.String(120)),
        sa.Column("birth_date", sa.DateTime),
        sa.Column("disciplines", ARRAY(sa.String), server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_verified", sa.Boolean, server_default="false"),
        sa.Column("is_premium", sa.Boolean, server_default="false"),
        sa.Column("is_superuser", sa.Boolean, server_default="false"),
        sa.Column("oauth_provider", sa.String(30)),
        sa.Column("oauth_provider_id", sa.String(255)),
        sa.Column("strava_id", sa.String(50)),
        sa.Column("strava_access_token", sa.String(500)),
        sa.Column("strava_refresh_token", sa.String(500)),
        sa.Column("preferences", sa.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_oauth", "users", ["oauth_provider", "oauth_provider_id"])
    op.create_index("ix_users_strava", "users", ["strava_id"])

    # refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(512), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_token", "refresh_tokens", ["token"])

    # user_follows
    op.create_table(
        "user_follows",
        sa.Column("follower_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("following_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # events
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(200), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("discipline", sa.String(30), nullable=False),
        sa.Column("difficulty", sa.String(20)),
        sa.Column("status", sa.String(20), server_default="upcoming"),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_deadline", sa.DateTime(timezone=True)),
        sa.Column("location_name", sa.String(200)),
        sa.Column("city", sa.String(100)),
        sa.Column("country", sa.String(100)),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("distance_km", sa.Float),
        sa.Column("elevation_gain_m", sa.Float),
        sa.Column("max_participants", sa.Integer),
        sa.Column("registration_fee", sa.Numeric(8, 2)),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("website_url", sa.String(500)),
        sa.Column("cover_image_url", sa.String(500)),
        sa.Column("gpx_url", sa.String(500)),
        sa.Column("organizer_name", sa.String(200)),
        sa.Column("organizer_contact", sa.String(200)),
        sa.Column("tags", ARRAY(sa.String), server_default="{}"),
        sa.Column("extra_data", sa.JSON, server_default="{}"),
        sa.Column("created_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_events_slug", "events", ["slug"])
    op.create_index("ix_events_geo", "events", ["latitude", "longitude"])
    op.create_index("ix_events_discipline_date", "events", ["discipline", "date"])

    # event_participants
    op.create_table(
        "event_participants",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("bib_number", sa.String(20)),
    )

    # activities
    op.create_table(
        "activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("discipline", sa.String(30), nullable=False),
        sa.Column("activity_type", sa.String(30), server_default="training"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("moving_time_seconds", sa.Integer),
        sa.Column("distance_meters", sa.Float),
        sa.Column("elevation_gain_m", sa.Float),
        sa.Column("elevation_loss_m", sa.Float),
        sa.Column("avg_pace_sec_per_km", sa.Float),
        sa.Column("avg_speed_kmh", sa.Float),
        sa.Column("max_speed_kmh", sa.Float),
        sa.Column("avg_heart_rate", sa.Integer),
        sa.Column("max_heart_rate", sa.Integer),
        sa.Column("avg_power_watts", sa.Integer),
        sa.Column("normalized_power_watts", sa.Integer),
        sa.Column("avg_cadence", sa.Integer),
        sa.Column("calories_burned", sa.Integer),
        sa.Column("perceived_effort", sa.Integer),
        sa.Column("weather_conditions", sa.String(100)),
        sa.Column("temperature_celsius", sa.Float),
        sa.Column("gpx_url", sa.String(500)),
        sa.Column("strava_activity_id", sa.String(50)),
        sa.Column("splits", sa.JSON, server_default="[]"),
        sa.Column("lap_data", sa.JSON, server_default="[]"),
        sa.Column("notes", sa.Text),
        sa.Column("is_public", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_activities_user_date", "activities", ["user_id", "started_at"])
    op.create_index("ix_activities_strava", "activities", ["strava_activity_id"])

    # posts
    op.create_table(
        "posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", UUID(as_uuid=True), sa.ForeignKey("activities.id")),
        sa.Column("post_type", sa.String(20), server_default="text"),
        sa.Column("content", sa.Text),
        sa.Column("image_urls", ARRAY(sa.String), server_default="{}"),
        sa.Column("is_public", sa.Boolean, server_default="true"),
        sa.Column("likes_count", sa.Integer, server_default="0"),
        sa.Column("comments_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_posts_author_created", "posts", ["author_id", "created_at"])

    # post_likes
    op.create_table(
        "post_likes",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("post_id", UUID(as_uuid=True), sa.ForeignKey("posts.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # comments
    op.create_table(
        "comments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("post_id", UUID(as_uuid=True), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("comments.id")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # event_results
    op.create_table(
        "event_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("finish_time_seconds", sa.Integer),
        sa.Column("overall_position", sa.Integer),
        sa.Column("category_position", sa.Integer),
        sa.Column("category", sa.String(50)),
        sa.Column("dnf", sa.Boolean, server_default="false"),
        sa.Column("dns", sa.Boolean, server_default="false"),
        sa.Column("split_times", sa.JSON, server_default="{}"),
        sa.Column("official", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_result_user"),
    )

    # personal_bests
    op.create_table(
        "personal_bests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discipline", sa.String(30), nullable=False),
        sa.Column("distance_label", sa.String(30), nullable=False),
        sa.Column("distance_meters", sa.Float, nullable=False),
        sa.Column("time_seconds", sa.Integer, nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_id", UUID(as_uuid=True), sa.ForeignKey("activities.id")),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("events.id")),
        sa.Column("verified", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "discipline", "distance_label", name="uq_pb_user_discipline_distance"),
    )

    # teams
    op.create_table(
        "teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(150), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("website", sa.String(500)),
        sa.Column("location", sa.String(120)),
        sa.Column("disciplines", ARRAY(sa.String), server_default="{}"),
        sa.Column("is_public", sa.Boolean, server_default="true"),
        sa.Column("created_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_teams_slug", "teams", ["slug"])

    # team_members
    op.create_table(
        "team_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), server_default="athlete"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )

    # training_plans
    op.create_table(
        "training_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE")),
        sa.Column("created_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("discipline", sa.String(30)),
        sa.Column("difficulty", sa.String(20)),
        sa.Column("duration_weeks", sa.Integer),
        sa.Column("goal", sa.String(300)),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("starts_on", sa.DateTime),
        sa.Column("ends_on", sa.DateTime),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # training_sessions
    op.create_table(
        "training_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_number", sa.Integer, nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("discipline", sa.String(30)),
        sa.Column("session_type", sa.String(30)),
        sa.Column("target_duration_minutes", sa.Integer),
        sa.Column("target_distance_km", sa.Float),
        sa.Column("target_heart_rate_zone", sa.Integer),
        sa.Column("target_pace_sec_per_km", sa.Float),
        sa.Column("warmup_description", sa.Text),
        sa.Column("main_set_description", sa.Text),
        sa.Column("cooldown_description", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("order", sa.Integer, server_default="0"),
    )

    # plan_assignments
    op.create_table(
        "plan_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("athlete_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("starts_on", sa.DateTime, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("plan_id", "athlete_id", name="uq_plan_assignment"),
    )

    # notifications
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("message", sa.Text),
        sa.Column("data", sa.JSON, server_default="{}"),
        sa.Column("read", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("plan_assignments")
    op.drop_table("training_sessions")
    op.drop_table("training_plans")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("personal_bests")
    op.drop_table("event_results")
    op.drop_table("comments")
    op.drop_table("post_likes")
    op.drop_table("posts")
    op.drop_table("activities")
    op.drop_table("event_participants")
    op.drop_table("events")
    op.drop_table("user_follows")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
