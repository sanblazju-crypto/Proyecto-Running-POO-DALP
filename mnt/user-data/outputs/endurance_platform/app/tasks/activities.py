from datetime import datetime, timedelta, date, timezone
from app.celery_app import celery_app


@celery_app.task
def recalculate_user_streak(user_id: str):
    """
    Recalculate the consecutive training streak for a user.
    A streak day counts if the user logged at least one activity that day.
    """
    from app.tasks._db import run_in_sync_session
    from app.models import Activity, User
    from sqlalchemy import select, func, cast
    from sqlalchemy import Date

    def _work(session):
        rows = session.execute(
            select(func.cast(Activity.started_at, Date).label("day"))
            .where(Activity.user_id == user_id)
            .distinct()
            .order_by(func.cast(Activity.started_at, Date).desc())
            .limit(365)
        ).fetchall()

        if not rows:
            return 0

        streak = 0
        today = date.today()
        for i, (day,) in enumerate(rows):
            expected = today - timedelta(days=i)
            if day == expected:
                streak += 1
            else:
                break

        # Persist to user preferences
        user = session.get(User, user_id)
        if user:
            prefs = user.preferences or {}
            prefs["current_streak_days"] = streak
            prefs["streak_updated_at"] = datetime.utcnow().isoformat()
            user.preferences = prefs
            session.commit()

        return streak

    return run_in_sync_session(_work)


@celery_app.task
def recalculate_all_streaks():
    """Batch task: recalculate streaks for all active users."""
    from app.tasks._db import run_in_sync_session
    from app.models import User
    from sqlalchemy import select

    def _get_users(session):
        return [str(u.id) for u in session.execute(
            select(User).where(User.is_active == True)
        ).scalars().all()]

    user_ids = run_in_sync_session(_get_users)
    for uid in user_ids:
        recalculate_user_streak.delay(uid)


@celery_app.task(bind=True, max_retries=3)
def upload_gpx_to_s3(self, activity_id: str, file_content: bytes, filename: str):
    """Upload a GPX file to S3 and update the activity record."""
    import boto3
    from app.config import settings
    from app.tasks._db import run_in_sync_session
    from app.models import Activity

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        key = f"gpx/{activity_id}/{filename}"
        s3.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=file_content,
            ContentType="application/gpx+xml",
        )
        url = f"{settings.S3_BASE_URL}/{key}"

        def _update(session):
            activity = session.get(Activity, activity_id)
            if activity:
                activity.gpx_url = url
                session.commit()

        run_in_sync_session(_update)
        return url

    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, max_retries=3)
def upload_image_to_s3(self, folder: str, object_id: str, file_content: bytes,
                        filename: str, content_type: str = "image/jpeg") -> str:
    """Generic image upload to S3. Returns the public URL."""
    import boto3
    from app.config import settings

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        key = f"{folder}/{object_id}/{filename}"
        s3.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=file_content,
            ContentType=content_type,
            ACL="public-read",
        )
        return f"{settings.S3_BASE_URL}/{key}"

    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task
def process_strava_webhook(payload: dict):
    """
    Handle incoming Strava webhook events.
    Supported: activity create/update/delete.
    """
    from app.tasks._db import run_in_sync_session
    from app.models import Activity, User
    from sqlalchemy import select

    event_type = payload.get("object_type")
    aspect_type = payload.get("aspect_type")
    owner_id = str(payload.get("owner_id", ""))
    object_id = str(payload.get("object_id", ""))

    if event_type != "activity":
        return

    def _work(session):
        user = session.execute(
            select(User).where(User.strava_id == owner_id)
        ).scalar_one_or_none()

        if not user:
            return

        if aspect_type == "create":
            # In production: fetch activity details from Strava API and create
            print(f"[STRAVA] New activity {object_id} for user {user.username}")

        elif aspect_type == "update":
            activity = session.execute(
                select(Activity).where(Activity.strava_activity_id == object_id)
            ).scalar_one_or_none()
            if activity:
                print(f"[STRAVA] Update activity {object_id}")

        elif aspect_type == "delete":
            activity = session.execute(
                select(Activity).where(Activity.strava_activity_id == object_id)
            ).scalar_one_or_none()
            if activity:
                session.delete(activity)
                session.commit()

    run_in_sync_session(_work)


@celery_app.task
def generate_performance_report(team_id: str, period_days: int = 30) -> dict:
    """
    Generate a performance summary report for a team over the last N days.
    Returns a dict suitable for rendering to PDF or sending by email.
    """
    from app.tasks._db import run_in_sync_session
    from app.models import Activity, TeamMember, User
    from sqlalchemy import select, func
    from datetime import timedelta

    def _work(session):
        since = datetime.now(timezone.utc) - timedelta(days=period_days)

        members = session.execute(
            select(TeamMember.user_id).where(
                TeamMember.team_id == team_id,
                TeamMember.is_active == True,
            )
        ).scalars().all()

        report = {"team_id": team_id, "period_days": period_days, "athletes": []}

        for user_id in members:
            user = session.get(User, user_id)
            if not user:
                continue

            stats = session.execute(
                select(
                    func.count(Activity.id).label("sessions"),
                    func.coalesce(func.sum(Activity.distance_meters), 0).label("distance"),
                    func.coalesce(func.sum(Activity.duration_seconds), 0).label("duration"),
                    func.coalesce(func.sum(Activity.elevation_gain_m), 0).label("elevation"),
                )
                .where(
                    Activity.user_id == user_id,
                    Activity.started_at >= since,
                )
            ).fetchone()

            report["athletes"].append({
                "user_id": str(user_id),
                "username": user.username,
                "full_name": user.full_name,
                "sessions": stats.sessions,
                "total_km": round((stats.distance or 0) / 1000, 2),
                "total_hours": round((stats.duration or 0) / 3600, 2),
                "total_elevation_m": round(stats.elevation or 0, 1),
            })

        report["athletes"].sort(key=lambda a: a["total_km"], reverse=True)
        return report

    return run_in_sync_session(_work)
