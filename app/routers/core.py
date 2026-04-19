"""
Routes: /auth, /users, /events
Merges the original auth.py + users.py + events.py routers.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from slugify import slugify

from app.database import get_db
from app.models import (User, RefreshToken, Event, EventResult,
                        event_participants, user_follows, EventStatus)
from app.schemas import (RegisterRequest, LoginRequest, TokenResponse, RefreshRequest,
                         ChangePasswordRequest, UserMe, UserPublic, UserProfile,
                         UserUpdate, EventCreate, EventUpdate, EventPublic)
from app.security import (hash_password, verify_password, create_access_token,
                          create_refresh_token, get_current_user)
from app.config import settings

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/auth/register", response_model=TokenResponse, status_code=201, tags=["auth"])
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(func.count(User.id)).where(User.email == payload.email)):
        raise HTTPException(400, "El email ya está registrado")
    if await db.scalar(select(func.count(User.id)).where(User.username == payload.username)):
        raise HTTPException(400, "El nombre de usuario ya está en uso")

    user = User(email=payload.email, username=payload.username,
                hashed_password=hash_password(payload.password),
                full_name=payload.full_name, disciplines=payload.disciplines)
    db.add(user)
    await db.flush()

    access = create_access_token(str(user.id))
    refresh = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token=refresh,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)))
    return TokenResponse(access_token=access, refresh_token=refresh,
                         expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Credenciales incorrectas")
    if not user.is_active:
        raise HTTPException(403, "Cuenta desactivada")

    user.last_login_at = datetime.now(timezone.utc)
    access = create_access_token(str(user.id))
    refresh = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token=refresh,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)))
    return TokenResponse(access_token=access, refresh_token=refresh,
                         expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@router.post("/auth/refresh", response_model=TokenResponse, tags=["auth"])
async def refresh_tokens(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RefreshToken).where(
        RefreshToken.token == payload.refresh_token, RefreshToken.revoked == False))
    token_obj = result.scalar_one_or_none()
    if not token_obj:
        raise HTTPException(401, "Refresh token inválido")
    if token_obj.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, "Refresh token expirado")

    token_obj.revoked = True
    access = create_access_token(str(token_obj.user_id))
    refresh = create_refresh_token()
    db.add(RefreshToken(user_id=token_obj.user_id, token=refresh,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)))
    return TokenResponse(access_token=access, refresh_token=refresh,
                         expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@router.post("/auth/logout", status_code=204, tags=["auth"])
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    result = await db.execute(select(RefreshToken).where(
        RefreshToken.token == payload.refresh_token, RefreshToken.user_id == current_user.id))
    token_obj = result.scalar_one_or_none()
    if token_obj:
        token_obj.revoked = True


@router.post("/auth/change-password", status_code=204, tags=["auth"])
async def change_password(payload: ChangePasswordRequest, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    if not current_user.hashed_password or not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(400, "Contraseña actual incorrecta")
    current_user.hashed_password = hash_password(payload.new_password)


# ═══════════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/users/me", response_model=UserMe, tags=["users"])
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/users/me", response_model=UserMe, tags=["users"])
async def update_me(payload: UserUpdate, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(current_user, k, v)
    await db.refresh(current_user)
    return current_user


@router.get("/users/search", response_model=list[UserPublic], tags=["users"])
async def search_users(q: str = Query(..., min_length=2), limit: int = 20,
                       db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.is_active == True,
                           or_(User.username.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
        .limit(limit))
    return result.scalars().all()


@router.get("/users/{username}", response_model=UserProfile, tags=["users"])
async def get_user_profile(username: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    followers_count = await db.scalar(select(func.count()).where(user_follows.c.following_id == user.id))
    following_count = await db.scalar(select(func.count()).where(user_follows.c.follower_id == user.id))
    from app.models import Activity
    activities_count = await db.scalar(select(func.count(Activity.id)).where(
        Activity.user_id == user.id, Activity.is_public == True))
    is_following = (await db.scalar(select(func.count()).where(
        user_follows.c.follower_id == current_user.id,
        user_follows.c.following_id == user.id)) or 0) > 0

    profile = UserProfile.model_validate(user)
    profile.followers_count = followers_count or 0
    profile.following_count = following_count or 0
    profile.activities_count = activities_count or 0
    profile.is_following = is_following
    return profile


@router.post("/users/{user_id}/follow", status_code=204, tags=["users"])
async def follow_user(user_id: UUID, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    if user_id == current_user.id:
        raise HTTPException(400, "No puedes seguirte a ti mismo")
    if not await db.get(User, user_id):
        raise HTTPException(404, "Usuario no encontrado")
    if await db.scalar(select(func.count()).where(
            user_follows.c.follower_id == current_user.id,
            user_follows.c.following_id == user_id)):
        raise HTTPException(400, "Ya sigues a este usuario")
    await db.execute(user_follows.insert().values(follower_id=current_user.id, following_id=user_id))


@router.delete("/users/{user_id}/follow", status_code=204, tags=["users"])
async def unfollow_user(user_id: UUID, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    await db.execute(user_follows.delete().where(
        user_follows.c.follower_id == current_user.id,
        user_follows.c.following_id == user_id))


@router.get("/users/{user_id}/followers", response_model=list[UserPublic], tags=["users"])
async def get_followers(user_id: UUID, skip: int = 0, limit: int = 20,
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).join(user_follows, user_follows.c.follower_id == User.id)
        .where(user_follows.c.following_id == user_id).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/users/{user_id}/following", response_model=list[UserPublic], tags=["users"])
async def get_following(user_id: UUID, skip: int = 0, limit: int = 20,
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).join(user_follows, user_follows.c.following_id == User.id)
        .where(user_follows.c.follower_id == user_id).offset(skip).limit(limit))
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

async def _event_public(db: AsyncSession, ev: Event, current_user: Optional[User]) -> EventPublic:
    count = await db.scalar(select(func.count()).select_from(event_participants)
                            .where(event_participants.c.event_id == ev.id))
    is_reg = False
    if current_user:
        is_reg = bool(await db.scalar(select(func.count()).select_from(event_participants).where(
            event_participants.c.event_id == ev.id,
            event_participants.c.user_id == current_user.id)))
    d = EventPublic.model_validate(ev)
    d.participants_count = count or 0
    d.is_registered = is_reg
    return d


@router.get("/events", response_model=list[EventPublic], tags=["events"])
async def list_events(
    discipline: Optional[str] = None, difficulty: Optional[str] = None,
    city: Optional[str] = None, country: Optional[str] = None,
    distance_min_km: Optional[float] = None, distance_max_km: Optional[float] = None,
    search: Optional[str] = None,
    skip: int = 0, limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Event)
    if discipline:     q = q.where(Event.discipline == discipline)
    if difficulty:     q = q.where(Event.difficulty == difficulty)
    if city:           q = q.where(Event.city.ilike(f"%{city}%"))
    if country:        q = q.where(Event.country.ilike(f"%{country}%"))
    if distance_min_km: q = q.where(Event.distance_km >= distance_min_km)
    if distance_max_km: q = q.where(Event.distance_km <= distance_max_km)
    if search:
        q = q.where(or_(Event.name.ilike(f"%{search}%"),
                        Event.location_name.ilike(f"%{search}%")))
    result = await db.execute(q.order_by(Event.date.asc()).offset(skip).limit(limit))
    return [await _event_public(db, ev, current_user) for ev in result.scalars().all()]


@router.get("/events/{slug}", response_model=EventPublic, tags=["events"])
async def get_event(slug: str, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Event).where(Event.slug == slug))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Evento no encontrado")
    return await _event_public(db, ev, current_user)


@router.post("/events", response_model=EventPublic, status_code=201, tags=["events"])
async def create_event(payload: EventCreate, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    slug_base = slugify(payload.name)
    slug, i = slug_base, 1
    while await db.scalar(select(func.count(Event.id)).where(Event.slug == slug)):
        slug, i = f"{slug_base}-{i}", i + 1

    ev = Event(slug=slug, created_by_id=current_user.id, **payload.model_dump())
    db.add(ev)
    await db.flush()
    return await _event_public(db, ev, current_user)


@router.patch("/events/{event_id}", response_model=EventPublic, tags=["events"])
async def update_event(event_id: UUID, payload: EventUpdate,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    ev = await db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "Evento no encontrado")
    if ev.created_by_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(403, "Sin permisos")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(ev, k, v)
    return await _event_public(db, ev, current_user)


@router.post("/events/{event_id}/register", status_code=204, tags=["events"])
async def register_to_event(event_id: UUID, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    ev = await db.get(Event, event_id)
    if not ev or ev.status != EventStatus.UPCOMING:
        raise HTTPException(400, "Las inscripciones están cerradas")
    if await db.scalar(select(func.count()).select_from(event_participants).where(
            event_participants.c.event_id == event_id,
            event_participants.c.user_id == current_user.id)):
        raise HTTPException(400, "Ya estás inscrito")
    if ev.max_participants:
        count = await db.scalar(select(func.count()).select_from(event_participants)
                                .where(event_participants.c.event_id == event_id))
        if count >= ev.max_participants:
            raise HTTPException(400, "El evento está completo")
    await db.execute(event_participants.insert().values(user_id=current_user.id, event_id=event_id))


@router.delete("/events/{event_id}/register", status_code=204, tags=["events"])
async def unregister_from_event(event_id: UUID, db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(get_current_user)):
    await db.execute(event_participants.delete().where(
        event_participants.c.event_id == event_id,
        event_participants.c.user_id == current_user.id))


@router.get("/events/{event_id}/results", tags=["events"])
async def get_event_results(event_id: UUID, skip: int = 0, limit: int = 50,
                             db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EventResult).where(EventResult.event_id == event_id)
                              .order_by(EventResult.overall_position).offset(skip).limit(limit))
    return [{"position": r.overall_position, "user_id": str(r.user_id),
             "finish_time_seconds": r.finish_time_seconds, "category": r.category,
             "dnf": r.dnf, "dns": r.dns} for r in result.scalars().all()]
