"""
Routes: /activities, /feed, /stats, /teams, /ai
Merges the original activities.py + feed.py + stats.py + teams.py + ai.py.
Background notifications use FastAPI's built-in BackgroundTasks (no Celery needed).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func, desc, extract, or_
from sqlalchemy.ext.asyncio import AsyncSession
from slugify import slugify

from app.database import get_db
from app.models import (User, Activity, Post, PostType, Comment, PersonalBest,
                        Team, TeamMember, TeamRole, TrainingPlan, TrainingSession,
                        PlanAssignment, Notification, Discipline,
                        post_likes, user_follows)
from app.schemas import (ActivityCreate, ActivityUpdate, ActivityPublic,
                         PostCreate, PostPublic, CommentCreate, CommentPublic,
                         UserStats, TeamCreate, TeamUpdate, TeamPublic,
                         InviteMemberRequest, TrainingPlanCreate, TrainingPlanPublic,
                         AssignPlanRequest, AIRequest)
from app.security import get_current_user, require_premium
from app.config import settings

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

PB_DISTANCES = {
    "5K":            (Discipline.RUNNING,  5_000),
    "10K":           (Discipline.RUNNING, 10_000),
    "Half Marathon": (Discipline.RUNNING, 21_097),
    "Marathon":      (Discipline.RUNNING, 42_195),
    "40K Cycling":   (Discipline.CYCLING, 40_000),
    "100K Cycling":  (Discipline.CYCLING, 100_000),
}


async def _update_personal_bests(db: AsyncSession, user: User, activity: Activity):
    if not activity.distance_meters or not activity.duration_seconds:
        return
    for label, (discipline, dist_m) in PB_DISTANCES.items():
        if activity.discipline != discipline or activity.distance_meters < dist_m:
            continue
        est = int(activity.duration_seconds * (dist_m / activity.distance_meters))
        result = await db.execute(select(PersonalBest).where(
            PersonalBest.user_id == user.id, PersonalBest.discipline == discipline,
            PersonalBest.distance_label == label))
        pb = result.scalar_one_or_none()
        if not pb or est < pb.time_seconds:
            if pb:
                pb.time_seconds = est; pb.achieved_at = activity.started_at; pb.activity_id = activity.id
            else:
                db.add(PersonalBest(user_id=user.id, discipline=discipline,
                                    distance_label=label, distance_meters=dist_m,
                                    time_seconds=est, achieved_at=activity.started_at,
                                    activity_id=activity.id))


async def _save_notification(db: AsyncSession, user_id, type: str, title: str, message: str, data: dict = None):
    """Persist a notification record — replaces the Celery notification tasks."""
    db.add(Notification(user_id=user_id, type=type, title=title, message=message, data=data or {}))
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITIES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/activities", response_model=list[ActivityPublic], tags=["activities"])
async def list_my_activities(discipline: Optional[str] = None,
                              skip: int = 0, limit: int = Query(20, le=100),
                              db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    q = select(Activity).where(Activity.user_id == current_user.id)
    if discipline:
        q = q.where(Activity.discipline == discipline)
    result = await db.execute(q.order_by(Activity.started_at.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/activities/user/{user_id}", response_model=list[ActivityPublic], tags=["activities"])
async def list_user_activities(user_id: UUID, discipline: Optional[str] = None,
                                skip: int = 0, limit: int = 20,
                                db: AsyncSession = Depends(get_db),
                                _: User = Depends(get_current_user)):
    q = select(Activity).where(Activity.user_id == user_id, Activity.is_public == True)
    if discipline:
        q = q.where(Activity.discipline == discipline)
    result = await db.execute(q.order_by(Activity.started_at.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/activities/{activity_id}", response_model=ActivityPublic, tags=["activities"])
async def get_activity(activity_id: UUID, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    a = await db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, "Actividad no encontrada")
    if not a.is_public and a.user_id != current_user.id:
        raise HTTPException(403, "Actividad privada")
    return a


@router.post("/activities", response_model=ActivityPublic, status_code=201, tags=["activities"])
async def create_activity(payload: ActivityCreate, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    data = payload.model_dump()
    d, t = data.get("distance_meters"), data.get("duration_seconds")
    if d and t:
        data["avg_pace_sec_per_km"] = t / (d / 1000)
        data["avg_speed_kmh"] = (d / 1000) / (t / 3600)

    activity = Activity(user_id=current_user.id, **data)
    db.add(activity)
    await db.flush()

    if activity.is_public:
        content = f"Completé {payload.title}"
        if d:
            content += f" · {d/1000:.2f} km"
        db.add(Post(author_id=current_user.id, activity_id=activity.id,
                    post_type=PostType.ACTIVITY, content=content, is_public=True))

    await _update_personal_bests(db, current_user, activity)
    await db.refresh(activity)
    return activity


@router.patch("/activities/{activity_id}", response_model=ActivityPublic, tags=["activities"])
async def update_activity(activity_id: UUID, payload: ActivityUpdate,
                           db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    a = await db.get(Activity, activity_id)
    if not a or a.user_id != current_user.id:
        raise HTTPException(404, "Actividad no encontrada o sin permisos")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(a, k, v)
    await db.refresh(a)
    return a


@router.delete("/activities/{activity_id}", status_code=204, tags=["activities"])
async def delete_activity(activity_id: UUID, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    a = await db.get(Activity, activity_id)
    if not a or a.user_id != current_user.id:
        raise HTTPException(404, "Actividad no encontrada o sin permisos")
    await db.delete(a)


@router.post("/activities/{activity_id}/gpx", tags=["activities"])
async def upload_gpx(activity_id: UUID, file: UploadFile = File(...),
                     db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    import gpxpy
    a = await db.get(Activity, activity_id)
    if not a or a.user_id != current_user.id:
        raise HTTPException(404, "Actividad no encontrada")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Archivo demasiado grande (máx 10 MB)")
    try:
        gpx = gpxpy.parse(content.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Archivo GPX inválido")

    length = gpx.length_2d() or 0
    uphill, _ = gpx.get_uphill_downhill()
    moving = gpx.get_moving_data()

    if not a.distance_meters and length:
        a.distance_meters = length
    if not a.elevation_gain_m and uphill:
        a.elevation_gain_m = uphill
    if moving and not a.moving_time_seconds:
        a.moving_time_seconds = int(moving.moving_time)

    a.gpx_url = f"/activities/{activity_id}/gpx/download"
    return {"message": "GPX procesado", "distance_meters": a.distance_meters}


# ═══════════════════════════════════════════════════════════════════════════════
# FEED
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/feed", response_model=list[PostPublic], tags=["feed"])
async def get_feed(mode: str = Query("chronological", pattern="^(chronological|relevance)$"),
                   skip: int = 0, limit: int = Query(20, le=50),
                   db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    following_q = select(user_follows.c.following_id).where(
        user_follows.c.follower_id == current_user.id).scalar_subquery()

    q = select(Post).where(Post.is_public == True,
                            or_(Post.author_id.in_(following_q),
                                Post.author_id == current_user.id))
    q = q.order_by(desc(Post.created_at) if mode == "chronological"
                   else desc(Post.likes_count * 3 + Post.comments_count * 2))
    result = await db.execute(q.offset(skip).limit(limit))
    posts = result.scalars().all()

    liked = {str(r[0]) for r in (await db.execute(
        select(post_likes.c.post_id).where(post_likes.c.user_id == current_user.id))).fetchall()}

    out = []
    for p in posts:
        d = PostPublic.model_validate(p)
        d.is_liked = str(p.id) in liked
        out.append(d)
    return out


@router.get("/feed/explore", response_model=list[PostPublic], tags=["feed"])
async def explore_feed(skip: int = 0, limit: int = Query(20, le=50),
                        db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Post).where(Post.is_public == True)
        .order_by(desc(Post.likes_count * 3 + Post.comments_count * 2), desc(Post.created_at))
        .offset(skip).limit(limit))
    liked = {str(r[0]) for r in (await db.execute(
        select(post_likes.c.post_id).where(post_likes.c.user_id == current_user.id))).fetchall()}
    out = []
    for p in result.scalars().all():
        d = PostPublic.model_validate(p); d.is_liked = str(p.id) in liked
        out.append(d)
    return out


@router.post("/feed", response_model=PostPublic, status_code=201, tags=["feed"])
async def create_post(payload: PostCreate, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    post = Post(author_id=current_user.id, content=payload.content,
                post_type=payload.post_type, activity_id=payload.activity_id,
                is_public=payload.is_public)
    db.add(post)
    await db.flush()
    await db.refresh(post)
    d = PostPublic.model_validate(post); d.is_liked = False
    return d


@router.delete("/feed/{post_id}", status_code=204, tags=["feed"])
async def delete_post(post_id: UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    post = await db.get(Post, post_id)
    if not post or (post.author_id != current_user.id and not current_user.is_superuser):
        raise HTTPException(404, "Post no encontrado o sin permisos")
    await db.delete(post)


@router.post("/feed/{post_id}/like", status_code=204, tags=["feed"])
async def like_post(post_id: UUID, background: BackgroundTasks,
                    db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post no encontrado")
    if not await db.scalar(select(func.count()).select_from(post_likes).where(
            post_likes.c.user_id == current_user.id, post_likes.c.post_id == post_id)):
        await db.execute(post_likes.insert().values(user_id=current_user.id, post_id=post_id))
        post.likes_count += 1
        if post.author_id != current_user.id:
            background.add_task(_save_notification, db, post.author_id, "like",
                                 "Me gusta", f"A {current_user.username} le ha gustado tu publicación",
                                 {"post_id": str(post_id)})


@router.delete("/feed/{post_id}/like", status_code=204, tags=["feed"])
async def unlike_post(post_id: UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post no encontrado")
    deleted = await db.execute(post_likes.delete().where(
        post_likes.c.user_id == current_user.id, post_likes.c.post_id == post_id))
    if deleted.rowcount > 0:
        post.likes_count = max(0, post.likes_count - 1)


@router.get("/feed/{post_id}/comments", response_model=list[CommentPublic], tags=["feed"])
async def list_comments(post_id: UUID, skip: int = 0, limit: int = 30,
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Comment).where(Comment.post_id == post_id, Comment.parent_id == None)
        .order_by(Comment.created_at).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("/feed/{post_id}/comments", response_model=CommentPublic, status_code=201, tags=["feed"])
async def add_comment(post_id: UUID, payload: CommentCreate, background: BackgroundTasks,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post no encontrado")
    comment = Comment(post_id=post_id, author_id=current_user.id,
                      content=payload.content, parent_id=payload.parent_id)
    db.add(comment)
    post.comments_count += 1
    await db.flush()
    if post.author_id != current_user.id:
        background.add_task(_save_notification, db, post.author_id, "comment",
                             "Nuevo comentario",
                             f"{current_user.username}: {payload.content[:80]}",
                             {"post_id": str(post_id)})
    await db.refresh(comment)
    return comment


@router.delete("/feed/comments/{comment_id}", status_code=204, tags=["feed"])
async def delete_comment(comment_id: UUID, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    comment = await db.get(Comment, comment_id)
    if not comment or (comment.author_id != current_user.id and not current_user.is_superuser):
        raise HTTPException(404, "Comentario no encontrado o sin permisos")
    post = await db.get(Post, comment.post_id)
    if post:
        post.comments_count = max(0, post.comments_count - 1)
    await db.delete(comment)


# ═══════════════════════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════════════════════

async def _build_stats(db: AsyncSession, user_id: UUID) -> UserStats:
    t = await db.execute(select(
        func.count(Activity.id).label("total"),
        func.coalesce(func.sum(Activity.distance_meters), 0).label("distance"),
        func.coalesce(func.sum(Activity.duration_seconds), 0).label("duration"),
        func.coalesce(func.sum(Activity.elevation_gain_m), 0).label("elevation"),
        func.coalesce(func.sum(Activity.calories_burned), 0).label("calories"),
    ).where(Activity.user_id == user_id))
    t = t.fetchone()

    by_disc = await db.execute(
        select(Activity.discipline, func.count(Activity.id), func.sum(Activity.distance_meters))
        .where(Activity.user_id == user_id).group_by(Activity.discipline))
    disc_map = {str(d): {"count": c, "total_km": round((m or 0)/1000, 2)} for d, c, m in by_disc}

    monthly = await db.execute(
        select(extract("year", Activity.started_at).label("yr"),
               extract("month", Activity.started_at).label("mo"),
               func.sum(Activity.distance_meters), func.count(Activity.id))
        .where(Activity.user_id == user_id).group_by("yr", "mo").order_by("yr", "mo").limit(12))
    monthly_data = [{"year": int(r[0]), "month": int(r[1]),
                     "km": round((r[2] or 0)/1000, 2), "sessions": r[3]} for r in monthly.fetchall()]

    pbs = await db.execute(select(PersonalBest).where(PersonalBest.user_id == user_id))
    pb_list = [{"discipline": pb.discipline, "distance_label": pb.distance_label,
                "time_seconds": pb.time_seconds, "achieved_at": str(pb.achieved_at)}
               for pb in pbs.scalars().all()]

    weeks = max((t.duration or 1) / 3600 / 24 / 7, 1)
    return UserStats(
        total_activities=t.total or 0,
        total_distance_km=round((t.distance or 0)/1000, 2),
        total_duration_hours=round((t.duration or 0)/3600, 2),
        total_elevation_gain_m=round(t.elevation or 0, 1),
        total_calories=int(t.calories or 0),
        activities_by_discipline=disc_map,
        activities_by_month=monthly_data,
        personal_bests=pb_list,
        avg_weekly_distance_km=round((t.distance or 0)/1000/weeks, 2),
    )


@router.get("/stats/me", response_model=UserStats, tags=["stats"])
async def my_stats(db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    return await _build_stats(db, current_user.id)


@router.get("/stats/user/{user_id}", response_model=UserStats, tags=["stats"])
async def user_stats(user_id: UUID, db: AsyncSession = Depends(get_db),
                     _: User = Depends(get_current_user)):
    return await _build_stats(db, user_id)


@router.get("/stats/me/personal-bests", tags=["stats"])
async def personal_bests(discipline: Optional[str] = None,
                          db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    q = select(PersonalBest).where(PersonalBest.user_id == current_user.id)
    if discipline:
        q = q.where(PersonalBest.discipline == discipline)
    result = await db.execute(q.order_by(PersonalBest.discipline, PersonalBest.distance_meters))
    return [{"discipline": pb.discipline, "distance_label": pb.distance_label,
             "time_seconds": pb.time_seconds,
             "pace_sec_per_km": pb.time_seconds / (pb.distance_meters / 1000),
             "achieved_at": pb.achieved_at} for pb in result.scalars().all()]


@router.get("/stats/me/weekly-volume", tags=["stats"])
async def weekly_volume(weeks: int = Query(12, ge=1, le=52),
                         db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    result = await db.execute(
        select(extract("year", Activity.started_at).label("yr"),
               extract("week", Activity.started_at).label("wk"),
               Activity.discipline,
               func.sum(Activity.distance_meters).label("dist"),
               func.sum(Activity.duration_seconds).label("dur"),
               func.count(Activity.id).label("cnt"))
        .where(Activity.user_id == current_user.id, Activity.started_at >= since)
        .group_by("yr", "wk", Activity.discipline).order_by("yr", "wk"))
    return [{"year": int(r.yr), "week": int(r.wk), "discipline": r.discipline,
             "total_km": round((r.dist or 0)/1000, 2),
             "total_hours": round((r.dur or 0)/3600, 2), "sessions": r.cnt}
            for r in result.fetchall()]


# ═══════════════════════════════════════════════════════════════════════════════
# TEAMS  (premium)
# ═══════════════════════════════════════════════════════════════════════════════

async def _require_coach(db, team_id, user_id):
    result = await db.execute(select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id,
        TeamMember.role.in_([TeamRole.COACH]), TeamMember.is_active == True))
    if not result.scalar_one_or_none():
        raise HTTPException(403, "Se requiere rol de entrenador")


@router.get("/teams", response_model=list[TeamPublic], tags=["teams"])
async def list_my_teams(db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current_user.id, TeamMember.is_active == True))
    teams = result.scalars().all()
    out = []
    for t in teams:
        count = await db.scalar(select(func.count(TeamMember.id)).where(
            TeamMember.team_id == t.id, TeamMember.is_active == True))
        d = TeamPublic.model_validate(t); d.members_count = count or 0
        out.append(d)
    return out


@router.post("/teams", response_model=TeamPublic, status_code=201, tags=["teams"])
async def create_team(payload: TeamCreate, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_premium)):
    slug_base = slugify(payload.name)
    slug, i = slug_base, 1
    while await db.scalar(select(func.count(Team.id)).where(Team.slug == slug)):
        slug, i = f"{slug_base}-{i}", i + 1
    team = Team(slug=slug, created_by_id=current_user.id, **payload.model_dump())
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=current_user.id, role=TeamRole.COACH))
    await db.refresh(team)
    d = TeamPublic.model_validate(team); d.members_count = 1
    return d


@router.get("/teams/{team_id}/members", tags=["teams"])
async def list_members(team_id: UUID, db: AsyncSession = Depends(get_db),
                        _: User = Depends(get_current_user)):
    result = await db.execute(
        select(TeamMember, User).join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id, TeamMember.is_active == True))
    return [{"user_id": str(m.user_id), "username": u.username, "full_name": u.full_name,
             "role": m.role, "joined_at": m.joined_at} for m, u in result.fetchall()]


@router.post("/teams/{team_id}/members", status_code=204, tags=["teams"])
async def invite_member(team_id: UUID, payload: InviteMemberRequest,
                         db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_premium)):
    await _require_coach(db, team_id, current_user.id)
    if not await db.get(User, payload.user_id):
        raise HTTPException(404, "Usuario no encontrado")
    if await db.scalar(select(func.count(TeamMember.id)).where(
            TeamMember.team_id == team_id, TeamMember.user_id == payload.user_id)):
        raise HTTPException(400, "El usuario ya es miembro")
    db.add(TeamMember(team_id=team_id, user_id=payload.user_id, role=payload.role))


@router.delete("/teams/{team_id}/members/{user_id}", status_code=204, tags=["teams"])
async def remove_member(team_id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_premium)):
    await _require_coach(db, team_id, current_user.id)
    result = await db.execute(select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "Miembro no encontrado")
    member.is_active = False


@router.post("/teams/{team_id}/plans", response_model=TrainingPlanPublic, status_code=201, tags=["teams"])
async def create_plan(team_id: UUID, payload: TrainingPlanCreate,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_premium)):
    await _require_coach(db, team_id, current_user.id)
    sessions_data = payload.sessions
    plan = TrainingPlan(team_id=team_id, created_by_id=current_user.id,
                        **payload.model_dump(exclude={"sessions", "team_id"}))
    db.add(plan)
    await db.flush()
    for i, s in enumerate(sessions_data):
        db.add(TrainingSession(plan_id=plan.id, order=i, **s.model_dump()))
    await db.refresh(plan)
    d = TrainingPlanPublic.model_validate(plan); d.sessions_count = len(sessions_data)
    return d


@router.get("/teams/{team_id}/plans", response_model=list[TrainingPlanPublic], tags=["teams"])
async def list_plans(team_id: UUID, db: AsyncSession = Depends(get_db),
                      _: User = Depends(get_current_user)):
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.team_id == team_id)
                              .order_by(TrainingPlan.created_at.desc()))
    out = []
    for p in result.scalars().all():
        count = await db.scalar(select(func.count(TrainingSession.id)).where(TrainingSession.plan_id == p.id))
        d = TrainingPlanPublic.model_validate(p); d.sessions_count = count or 0
        out.append(d)
    return out


@router.get("/teams/{team_id}/plans/{plan_id}", tags=["teams"])
async def get_plan(team_id: UUID, plan_id: UUID, db: AsyncSession = Depends(get_db),
                    _: User = Depends(get_current_user)):
    plan = await db.get(TrainingPlan, plan_id)
    if not plan or plan.team_id != team_id:
        raise HTTPException(404, "Plan no encontrado")
    sessions = await db.execute(select(TrainingSession).where(TrainingSession.plan_id == plan_id)
                                 .order_by(TrainingSession.week_number, TrainingSession.day_of_week))
    weeks: dict = {}
    for s in sessions.scalars().all():
        weeks.setdefault(s.week_number, []).append({
            "day": s.day_of_week, "title": s.title,
            "discipline": s.discipline, "type": s.session_type,
            "target_duration_min": s.target_duration_minutes,
            "target_distance_km": s.target_distance_km})
    return {"id": plan.id, "name": plan.name, "discipline": plan.discipline,
            "duration_weeks": plan.duration_weeks, "goal": plan.goal, "status": plan.status,
            "weeks": [{"week": k, "sessions": v} for k, v in sorted(weeks.items())]}


@router.post("/teams/{team_id}/plans/{plan_id}/assign", status_code=204, tags=["teams"])
async def assign_plan(team_id: UUID, plan_id: UUID, payload: AssignPlanRequest,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_premium)):
    await _require_coach(db, team_id, current_user.id)
    plan = await db.get(TrainingPlan, plan_id)
    if not plan or plan.team_id != team_id:
        raise HTTPException(404, "Plan no encontrado")
    for athlete_id in payload.athlete_ids:
        if not await db.scalar(select(func.count(PlanAssignment.id)).where(
                PlanAssignment.plan_id == plan_id, PlanAssignment.athlete_id == athlete_id)):
            db.add(PlanAssignment(plan_id=plan_id, athlete_id=athlete_id,
                                   assigned_by_id=current_user.id,
                                   starts_on=payload.starts_on, notes=payload.notes))


# ═══════════════════════════════════════════════════════════════════════════════
# AI  (premium)
# ═══════════════════════════════════════════════════════════════════════════════

async def _athlete_context(db: AsyncSession, user: User) -> str:
    acts = await db.execute(select(Activity).where(Activity.user_id == user.id)
                            .order_by(desc(Activity.started_at)).limit(10))
    pbs  = await db.execute(select(PersonalBest).where(PersonalBest.user_id == user.id))

    lines = [f"Atleta: {user.full_name or user.username}",
             f"Disciplinas: {', '.join(user.disciplines or [])}",
             f"Ubicación: {user.location or 'no especificada'}", "", "Últimas actividades:"]
    for a in acts.scalars().all():
        km  = f"{a.distance_meters/1000:.1f}km" if a.distance_meters else ""
        dur = f"{a.duration_seconds//60}min" if a.duration_seconds else ""
        lines.append(f"  - {a.title} ({a.discipline}) {km} {dur}")

    pb_list = pbs.scalars().all()
    if pb_list:
        lines.append("\nMarcas personales:")
        for pb in pb_list:
            m, s = pb.time_seconds // 60, pb.time_seconds % 60
            lines.append(f"  - {pb.distance_label} ({pb.discipline}): {m}:{s:02d}")
    return "\n".join(lines)


@router.post("/ai/chat", tags=["ai"])
async def ai_chat(payload: AIRequest, db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(require_premium)):
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(503, "Servicio de IA no configurado")
    import anthropic
    ctx = await _athlete_context(db, current_user)
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1024,
        system=("Eres un entrenador personal experto en deportes de resistencia. "
                "Responde de forma concisa y motivadora en español.\n\n"
                f"Perfil del atleta:\n{ctx}"),
        messages=[{"role": "user", "content": payload.message}])
    return {"response": resp.content[0].text}


@router.post("/ai/analyze-plan", tags=["ai"])
async def analyze_plan(payload: AIRequest, _: User = Depends(require_premium)):
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(503, "Servicio de IA no configurado")
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1500,
        system=("Eres un entrenador experto en deportes de resistencia. "
                "Analiza planes de entrenamiento e identifica problemas y mejoras. Responde en español."),
        messages=[{"role": "user", "content": f"Analiza este plan:\n\n{payload.message}"}])
    return {"analysis": resp.content[0].text}
