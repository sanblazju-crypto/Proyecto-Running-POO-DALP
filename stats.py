from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, extract

from app.database import get_db
from app.models import User, Activity, PersonalBest
from app.schemas import UserStats
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/me", response_model=UserStats)
async def get_my_stats(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _build_stats(db, current_user.id, year)


@router.get("/user/{user_id}", response_model=UserStats)
async def get_user_stats(
    user_id: UUID,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _build_stats(db, user_id, year)


@router.get("/me/personal-bests")
async def get_personal_bests(
    discipline: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(PersonalBest).where(PersonalBest.user_id == current_user.id)
    if discipline:
        q = q.where(PersonalBest.discipline == discipline)
    q = q.order_by(PersonalBest.discipline, PersonalBest.distance_meters)
    result = await db.execute(q)
    pbs = result.scalars().all()
    return [
        {
            "discipline": pb.discipline,
            "distance_label": pb.distance_label,
            "distance_meters": pb.distance_meters,
            "time_seconds": pb.time_seconds,
            "pace_sec_per_km": pb.time_seconds / (pb.distance_meters / 1000),
            "achieved_at": pb.achieved_at,
            "activity_id": str(pb.activity_id) if pb.activity_id else None,
        }
        for pb in pbs
    ]


@router.get("/me/weekly-volume")
async def weekly_volume(
    weeks: int = Query(12, ge=1, le=52),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns weekly distance totals for the last N weeks, by discipline."""
    since = datetime.utcnow() - timedelta(weeks=weeks)
    result = await db.execute(
        select(
            extract("year", Activity.started_at).label("year"),
            extract("week", Activity.started_at).label("week"),
            Activity.discipline,
            func.sum(Activity.distance_meters).label("total_meters"),
            func.sum(Activity.duration_seconds).label("total_seconds"),
            func.count(Activity.id).label("count"),
        )
        .where(
            Activity.user_id == current_user.id,
            Activity.started_at >= since,
        )
        .group_by("year", "week", Activity.discipline)
        .order_by("year", "week")
    )
    rows = result.fetchall()
    return [
        {
            "year": int(r.year),
            "week": int(r.week),
            "discipline": r.discipline,
            "total_km": round((r.total_meters or 0) / 1000, 2),
            "total_hours": round((r.total_seconds or 0) / 3600, 2),
            "sessions": r.count,
        }
        for r in rows
    ]


@router.get("/me/monthly-volume")
async def monthly_volume(
    months: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(days=months * 30)
    result = await db.execute(
        select(
            extract("year", Activity.started_at).label("year"),
            extract("month", Activity.started_at).label("month"),
            Activity.discipline,
            func.sum(Activity.distance_meters).label("total_meters"),
            func.sum(Activity.duration_seconds).label("total_seconds"),
            func.sum(Activity.elevation_gain_m).label("total_elevation"),
            func.count(Activity.id).label("count"),
        )
        .where(
            Activity.user_id == current_user.id,
            Activity.started_at >= since,
        )
        .group_by("year", "month", Activity.discipline)
        .order_by("year", "month")
    )
    rows = result.fetchall()
    return [
        {
            "year": int(r.year),
            "month": int(r.month),
            "discipline": r.discipline,
            "total_km": round((r.total_meters or 0) / 1000, 2),
            "total_hours": round((r.total_seconds or 0) / 3600, 2),
            "total_elevation_m": round(r.total_elevation or 0, 1),
            "sessions": r.count,
        }
        for r in rows
    ]


async def _build_stats(db: AsyncSession, user_id: UUID, year: Optional[int]) -> UserStats:
    q_base = select(Activity).where(Activity.user_id == user_id)
    if year:
        q_base = q_base.where(extract("year", Activity.started_at) == year)

    # Totals
    totals = await db.execute(
        select(
            func.count(Activity.id).label("total"),
            func.coalesce(func.sum(Activity.distance_meters), 0).label("distance"),
            func.coalesce(func.sum(Activity.duration_seconds), 0).label("duration"),
            func.coalesce(func.sum(Activity.elevation_gain_m), 0).label("elevation"),
            func.coalesce(func.sum(Activity.calories_burned), 0).label("calories"),
        ).where(Activity.user_id == user_id)
        .where(extract("year", Activity.started_at) == year if year else True)
    )
    t = totals.fetchone()

    # By discipline
    by_disc = await db.execute(
        select(Activity.discipline, func.count(Activity.id), func.sum(Activity.distance_meters))
        .where(Activity.user_id == user_id)
        .group_by(Activity.discipline)
    )
    disc_map = {str(d): {"count": c, "total_km": round((m or 0) / 1000, 2)} for d, c, m in by_disc}

    # Monthly breakdown (last 12 months)
    monthly = await db.execute(
        select(
            extract("year", Activity.started_at).label("yr"),
            extract("month", Activity.started_at).label("mo"),
            func.sum(Activity.distance_meters).label("dist"),
            func.count(Activity.id).label("cnt"),
        )
        .where(Activity.user_id == user_id)
        .group_by("yr", "mo")
        .order_by("yr", "mo")
        .limit(12)
    )
    monthly_data = [
        {"year": int(r.yr), "month": int(r.mo), "km": round((r.dist or 0) / 1000, 2), "sessions": r.cnt}
        for r in monthly.fetchall()
    ]

    # Personal bests
    pb_result = await db.execute(
        select(PersonalBest).where(PersonalBest.user_id == user_id)
    )
    pbs = [
        {
            "discipline": pb.discipline,
            "distance_label": pb.distance_label,
            "time_seconds": pb.time_seconds,
            "achieved_at": str(pb.achieved_at),
        }
        for pb in pb_result.scalars().all()
    ]

    total_weeks = max((t.duration or 1) / 3600 / 24 / 7, 1)
    avg_weekly_km = round((t.distance or 0) / 1000 / total_weeks, 2)

    return UserStats(
        total_activities=t.total or 0,
        total_distance_km=round((t.distance or 0) / 1000, 2),
        total_duration_hours=round((t.duration or 0) / 3600, 2),
        total_elevation_gain_m=round(t.elevation or 0, 1),
        total_calories=int(t.calories or 0),
        activities_by_discipline=disc_map,
        activities_by_month=monthly_data,
        personal_bests=pbs,
        avg_weekly_distance_km=avg_weekly_km,
        current_streak_days=0,  # Implemented separately
    )
