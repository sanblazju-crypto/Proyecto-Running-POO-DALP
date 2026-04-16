from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, cast, Float
from sqlalchemy.dialects.postgresql import array
from slugify import slugify

from app.database import get_db
from app.models import User, Event, EventResult, event_participants, Discipline, EventStatus
from app.schemas import (
    EventCreate, EventUpdate, EventPublic, EventFilters,
)
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/events", tags=["events"])


def _haversine_sql(lat1, lon1, lat_col, lon_col):
    """Approximate distance in km between a point and a DB column (PostgreSQL)."""
    from sqlalchemy import text
    return text(
        f"6371 * acos(cos(radians({lat1})) * cos(radians({lat_col})) "
        f"* cos(radians({lon_col}) - radians({lon1})) "
        f"+ sin(radians({lat1})) * sin(radians({lat_col})))"
    )


@router.get("", response_model=list[EventPublic])
async def list_events(
    discipline: Optional[str] = None,
    difficulty: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    distance_min_km: Optional[float] = None,
    distance_max_km: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = Query(None, gt=0),
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    q = select(Event)
    filters = []

    if discipline:
        filters.append(Event.discipline == discipline)
    if difficulty:
        filters.append(Event.difficulty == difficulty)
    if status:
        filters.append(Event.status == status)
    if city:
        filters.append(Event.city.ilike(f"%{city}%"))
    if country:
        filters.append(Event.country.ilike(f"%{country}%"))
    if distance_min_km:
        filters.append(Event.distance_km >= distance_min_km)
    if distance_max_km:
        filters.append(Event.distance_km <= distance_max_km)
    if search:
        filters.append(
            or_(
                Event.name.ilike(f"%{search}%"),
                Event.location_name.ilike(f"%{search}%"),
                Event.organizer_name.ilike(f"%{search}%"),
            )
        )
    if filters:
        q = q.where(and_(*filters))

    # Geo filtering (approximate bounding box first, then haversine)
    if lat is not None and lng is not None and radius_km:
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * func.cos(func.radians(lat)))
        q = q.where(
            Event.latitude.between(lat - lat_delta, lat + lat_delta),
            Event.longitude.between(lng - lat_delta, lng + lat_delta),
        )

    q = q.order_by(Event.date.asc()).offset(skip).limit(limit)
    result = await db.execute(q)
    events = result.scalars().all()

    user_registered = set()
    if current_user:
        reg_result = await db.execute(
            select(event_participants.c.event_id).where(
                event_participants.c.user_id == current_user.id
            )
        )
        user_registered = {str(r[0]) for r in reg_result.fetchall()}

    output = []
    for ev in events:
        p_count = await db.scalar(
            select(func.count()).select_from(event_participants).where(
                event_participants.c.event_id == ev.id
            )
        )
        d = EventPublic.model_validate(ev)
        d.participants_count = p_count or 0
        d.is_registered = str(ev.id) in user_registered
        output.append(d)
    return output


@router.get("/{slug}", response_model=EventPublic)
async def get_event(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Event).where(Event.slug == slug))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    p_count = await db.scalar(
        select(func.count()).select_from(event_participants).where(
            event_participants.c.event_id == ev.id
        )
    )
    is_registered = False
    if current_user:
        count = await db.scalar(
            select(func.count()).select_from(event_participants).where(
                event_participants.c.event_id == ev.id,
                event_participants.c.user_id == current_user.id,
            )
        )
        is_registered = count > 0

    data = EventPublic.model_validate(ev)
    data.participants_count = p_count or 0
    data.is_registered = is_registered
    return data


@router.post("", response_model=EventPublic, status_code=201)
async def create_event(
    payload: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    slug_base = slugify(payload.name)
    slug = slug_base
    counter = 1
    while True:
        existing = await db.scalar(select(func.count(Event.id)).where(Event.slug == slug))
        if not existing:
            break
        slug = f"{slug_base}-{counter}"
        counter += 1

    ev = Event(
        slug=slug,
        created_by_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    data = EventPublic.model_validate(ev)
    data.participants_count = 0
    data.is_registered = False
    return data


@router.patch("/{event_id}", response_model=EventPublic)
async def update_event(
    event_id: UUID,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev = await db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if ev.created_by_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Sin permisos para editar este evento")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(ev, field, value)
    await db.commit()
    await db.refresh(ev)
    data = EventPublic.model_validate(ev)
    data.participants_count = 0
    data.is_registered = False
    return data


@router.post("/{event_id}/register", status_code=204)
async def register_to_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ev = await db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if ev.status != EventStatus.UPCOMING:
        raise HTTPException(status_code=400, detail="Las inscripciones están cerradas")

    existing = await db.scalar(
        select(func.count()).select_from(event_participants).where(
            event_participants.c.event_id == event_id,
            event_participants.c.user_id == current_user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya estás inscrito en este evento")

    if ev.max_participants:
        current_count = await db.scalar(
            select(func.count()).select_from(event_participants).where(
                event_participants.c.event_id == event_id
            )
        )
        if current_count >= ev.max_participants:
            raise HTTPException(status_code=400, detail="El evento está completo")

    await db.execute(
        event_participants.insert().values(user_id=current_user.id, event_id=event_id)
    )
    await db.commit()


@router.delete("/{event_id}/register", status_code=204)
async def unregister_from_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        event_participants.delete().where(
            event_participants.c.event_id == event_id,
            event_participants.c.user_id == current_user.id,
        )
    )
    await db.commit()


@router.get("/{event_id}/results", response_model=list[dict])
async def get_event_results(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    result = await db.execute(
        select(EventResult)
        .where(EventResult.event_id == event_id)
        .order_by(EventResult.overall_position.asc())
        .offset(skip)
        .limit(limit)
    )
    return [
        {
            "position": r.overall_position,
            "user_id": str(r.user_id),
            "finish_time_seconds": r.finish_time_seconds,
            "category": r.category,
            "category_position": r.category_position,
            "dnf": r.dnf,
            "dns": r.dns,
        }
        for r in result.scalars().all()
    ]
