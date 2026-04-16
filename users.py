from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.database import get_db
from app.models import User, user_follows, Activity
from app.schemas import UserPublic, UserProfile, UserMe, UserUpdate, PaginatedResponse
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserMe)
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/me/feed-suggestions", response_model=list[UserPublic])
async def feed_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=30),
):
    """Return users not yet followed with shared disciplines."""
    already_following = select(user_follows.c.following_id).where(
        user_follows.c.follower_id == current_user.id
    )
    result = await db.execute(
        select(User)
        .where(
            User.id != current_user.id,
            User.id.notin_(already_following),
            User.is_active == True,
            User.disciplines.overlap(current_user.disciplines) if current_user.disciplines else True,
        )
        .order_by(func.random())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/search", response_model=list[UserPublic])
async def search_users(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=50),
):
    result = await db.execute(
        select(User)
        .where(
            User.is_active == True,
            or_(
                User.username.ilike(f"%{q}%"),
                User.full_name.ilike(f"%{q}%"),
            ),
        )
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{username}", response_model=UserProfile)
async def get_user_profile(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Counts
    followers_count = await db.scalar(
        select(func.count()).where(user_follows.c.following_id == user.id)
    )
    following_count = await db.scalar(
        select(func.count()).where(user_follows.c.follower_id == user.id)
    )
    activities_count = await db.scalar(
        select(func.count(Activity.id)).where(
            Activity.user_id == user.id,
            Activity.is_public == True,
        )
    )
    is_following = await db.scalar(
        select(func.count()).where(
            user_follows.c.follower_id == current_user.id,
            user_follows.c.following_id == user.id,
        )
    ) > 0

    profile = UserProfile.model_validate(user)
    profile.followers_count = followers_count or 0
    profile.following_count = following_count or 0
    profile.activities_count = activities_count or 0
    profile.is_following = is_following
    return profile


@router.post("/{user_id}/follow", status_code=204)
async def follow_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes seguirte a ti mismo")

    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    existing = await db.scalar(
        select(func.count()).where(
            user_follows.c.follower_id == current_user.id,
            user_follows.c.following_id == user_id,
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya sigues a este usuario")

    await db.execute(
        user_follows.insert().values(follower_id=current_user.id, following_id=user_id)
    )
    await db.commit()


@router.delete("/{user_id}/follow", status_code=204)
async def unfollow_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        user_follows.delete().where(
            user_follows.c.follower_id == current_user.id,
            user_follows.c.following_id == user_id,
        )
    )
    await db.commit()


@router.get("/{user_id}/followers", response_model=list[UserPublic])
async def get_followers(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    result = await db.execute(
        select(User)
        .join(user_follows, user_follows.c.follower_id == User.id)
        .where(user_follows.c.following_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{user_id}/following", response_model=list[UserPublic])
async def get_following(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    result = await db.execute(
        select(User)
        .join(user_follows, user_follows.c.following_id == User.id)
        .where(user_follows.c.follower_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
