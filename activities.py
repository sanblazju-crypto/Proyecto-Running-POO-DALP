import math
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.models import User, Activity, PersonalBest, Post, PostType, Discipline
from app.schemas import ActivityCreate, ActivityUpdate, ActivityPublic
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/activities", tags=["activities"])

# Standard distances for personal best tracking (in meters)
PB_DISTANCES = {
    "1K":           (Discipline.RUNNING,  1_000),
    "5K":           (Discipline.RUNNING,  5_000),
    "10K":          (Discipline.RUNNING, 10_000),
    "Half Marathon": (Discipline.RUNNING, 21_097),
    "Marathon":     (Discipline.RUNNING, 42_195),
    "100K":         (Discipline.RUNNING, 100_000),
    "10K Cycling":  (Discipline.CYCLING,  10_000),
    "40K Cycling":  (Discipline.CYCLING,  40_000),
    "100K Cycling": (Discipline.CYCLING, 100_000),
}


def _calculate_pace(distance_meters: float, duration_seconds: int) -> float:
    """Returns pace in seconds per km."""
    if not distance_meters or not duration_seconds:
        return 0.0
    return duration_seconds / (distance_meters / 1000)


def _calculate_speed(distance_meters: float, duration_seconds: int) -> float:
    """Returns speed in km/h."""
    if not distance_meters or not duration_seconds:
        return 0.0
    return (distance_meters / 1000) / (duration_seconds / 3600)


async def _update_personal_bests(
    db: AsyncSession,
    user: User,
    activity: Activity,
):
    """Check and update personal bests after saving an activity."""
    if not activity.distance_meters or not activity.duration_seconds:
        return

    for label, (discipline, dist_m) in PB_DISTANCES.items():
        if activity.discipline != discipline:
            continue
        # Activity must cover at least this distance
        if activity.distance_meters < dist_m:
            continue

        # Proportionally estimate finish time for this distance
        estimated_seconds = int(activity.duration_seconds * (dist_m / activity.distance_meters))

        result = await db.execute(
            select(PersonalBest).where(
                PersonalBest.user_id == user.id,
                PersonalBest.discipline == discipline,
                PersonalBest.distance_label == label,
            )
        )
        existing_pb = result.scalar_one_or_none()

        if not existing_pb or estimated_seconds < existing_pb.time_seconds:
            if existing_pb:
                existing_pb.time_seconds = estimated_seconds
                existing_pb.achieved_at = activity.started_at
                existing_pb.activity_id = activity.id
            else:
                db.add(PersonalBest(
                    user_id=user.id,
                    discipline=discipline,
                    distance_label=label,
                    distance_meters=dist_m,
                    time_seconds=estimated_seconds,
                    achieved_at=activity.started_at,
                    activity_id=activity.id,
                ))


@router.get("", response_model=list[ActivityPublic])
async def list_my_activities(
    discipline: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Activity).where(Activity.user_id == current_user.id)
    if discipline:
        q = q.where(Activity.discipline == discipline)
    q = q.order_by(Activity.started_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/user/{user_id}", response_model=list[ActivityPublic])
async def list_user_activities(
    user_id: UUID,
    discipline: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Activity).where(
        Activity.user_id == user_id,
        Activity.is_public == True,
    )
    if discipline:
        q = q.where(Activity.discipline == discipline)
    q = q.order_by(Activity.started_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{activity_id}", response_model=ActivityPublic)
async def get_activity(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    if not activity.is_public and activity.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Actividad privada")
    return activity


@router.post("", response_model=ActivityPublic, status_code=201)
async def create_activity(
    payload: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    distance_m = data.get("distance_meters")
    duration_s = data.get("duration_seconds")

    # Auto-compute pace and speed if possible
    if distance_m and duration_s:
        data["avg_pace_sec_per_km"] = _calculate_pace(distance_m, duration_s)
        data["avg_speed_kmh"] = _calculate_speed(distance_m, duration_s)

    activity = Activity(user_id=current_user.id, **data)
    db.add(activity)
    await db.flush()

    # Auto-create a post for public activities
    if activity.is_public:
        post_content = f"Completé {payload.title}"
        if distance_m:
            post_content += f" · {distance_m / 1000:.2f} km"
        db.add(Post(
            author_id=current_user.id,
            activity_id=activity.id,
            post_type=PostType.ACTIVITY,
            content=post_content,
            is_public=True,
        ))

    await _update_personal_bests(db, current_user, activity)
    await db.commit()
    await db.refresh(activity)
    return activity


@router.patch("/{activity_id}", response_model=ActivityPublic)
async def update_activity(
    activity_id: UUID,
    payload: ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    if activity.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sin permisos")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(activity, field, value)
    await db.commit()
    await db.refresh(activity)
    return activity


@router.delete("/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    if activity.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sin permisos")
    await db.delete(activity)
    await db.commit()


@router.post("/{activity_id}/gpx", status_code=200)
async def upload_gpx(
    activity_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a GPX file and parse basic metrics from it."""
    import gpxpy

    activity = await db.get(Activity, activity_id)
    if not activity or activity.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Archivo demasiado grande (máx 10 MB)")

    try:
        gpx = gpxpy.parse(content.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Archivo GPX inválido")

    # Extract metrics from GPX
    length_2d = gpx.length_2d() or 0
    uphill, _ = gpx.get_uphill_downhill()
    moving_data = gpx.get_moving_data()

    if not activity.distance_meters and length_2d:
        activity.distance_meters = length_2d
    if not activity.elevation_gain_m and uphill:
        activity.elevation_gain_m = uphill
    if moving_data:
        if not activity.moving_time_seconds:
            activity.moving_time_seconds = int(moving_data.moving_time)
        if not activity.avg_speed_kmh:
            activity.avg_speed_kmh = (moving_data.moving_distance / 1000) / (moving_data.moving_time / 3600) if moving_data.moving_time else 0

    # Build per-km splits
    splits = []
    for i, point in enumerate(gpx.get_points_data(distance_2d=True)):
        pass  # simplified - real implementation would compute km splits

    activity.splits = splits
    # In production: upload raw file to S3 and store URL
    activity.gpx_url = f"/activities/{activity_id}/gpx/download"

    await db.commit()
    return {"message": "GPX procesado correctamente", "distance_meters": activity.distance_meters}
