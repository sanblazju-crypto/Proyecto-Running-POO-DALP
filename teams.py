from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from slugify import slugify

from app.database import get_db
from app.models import User, Team, TeamMember, TeamRole, TrainingPlan, TrainingSession, PlanAssignment
from app.schemas import (
    TeamCreate, TeamUpdate, TeamPublic,
    InviteMemberRequest, TrainingPlanCreate, TrainingPlanPublic, AssignPlanRequest,
)
from app.auth.dependencies import get_current_user, get_current_premium_user

router = APIRouter(prefix="/teams", tags=["teams"])


async def _get_team_or_404(db: AsyncSession, team_id: UUID) -> Team:
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return team


async def _require_coach(db: AsyncSession, team_id: UUID, user_id: UUID):
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.role.in_([TeamRole.COACH, TeamRole.ADMIN]),
            TeamMember.is_active == True,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Se requiere rol de entrenador o admin")


# ─── Teams CRUD ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[TeamPublic])
async def list_my_teams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current_user.id, TeamMember.is_active == True)
    )
    teams = result.scalars().all()
    out = []
    for t in teams:
        count = await db.scalar(
            select(func.count(TeamMember.id)).where(
                TeamMember.team_id == t.id, TeamMember.is_active == True
            )
        )
        data = TeamPublic.model_validate(t)
        data.members_count = count or 0
        out.append(data)
    return out


@router.post("", response_model=TeamPublic, status_code=201)
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    slug_base = slugify(payload.name)
    slug = slug_base
    i = 1
    while await db.scalar(select(func.count(Team.id)).where(Team.slug == slug)):
        slug = f"{slug_base}-{i}"
        i += 1

    team = Team(slug=slug, created_by_id=current_user.id, **payload.model_dump())
    db.add(team)
    await db.flush()

    # Creator becomes admin/coach
    db.add(TeamMember(team_id=team.id, user_id=current_user.id, role=TeamRole.COACH))
    await db.commit()
    await db.refresh(team)

    data = TeamPublic.model_validate(team)
    data.members_count = 1
    return data


@router.get("/{team_id}", response_model=TeamPublic)
async def get_team(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team = await _get_team_or_404(db, team_id)
    count = await db.scalar(
        select(func.count(TeamMember.id)).where(
            TeamMember.team_id == team_id, TeamMember.is_active == True
        )
    )
    data = TeamPublic.model_validate(team)
    data.members_count = count or 0
    return data


@router.patch("/{team_id}", response_model=TeamPublic)
async def update_team(
    team_id: UUID,
    payload: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    team = await _get_team_or_404(db, team_id)
    await _require_coach(db, team_id, current_user.id)

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(team, field, value)
    await db.commit()
    await db.refresh(team)
    data = TeamPublic.model_validate(team)
    data.members_count = 0
    return data


@router.post("/{team_id}/members", status_code=204)
async def invite_member(
    team_id: UUID,
    payload: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    await _get_team_or_404(db, team_id)
    await _require_coach(db, team_id, current_user.id)

    user = await db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    existing = await db.scalar(
        select(func.count(TeamMember.id)).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == payload.user_id,
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="El usuario ya es miembro")

    db.add(TeamMember(
        team_id=team_id,
        user_id=payload.user_id,
        role=payload.role,
    ))
    await db.commit()


@router.get("/{team_id}/members")
async def list_members(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id, TeamMember.is_active == True)
    )
    return [
        {
            "user_id": str(m.user_id),
            "username": u.username,
            "full_name": u.full_name,
            "avatar_url": u.avatar_url,
            "role": m.role,
            "joined_at": m.joined_at,
        }
        for m, u in result.fetchall()
    ]


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    await _require_coach(db, team_id, current_user.id)
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    member.is_active = False
    await db.commit()


# ─── Training Plans ───────────────────────────────────────────────────────────

@router.post("/{team_id}/plans", response_model=TrainingPlanPublic, status_code=201)
async def create_plan(
    team_id: UUID,
    payload: TrainingPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    await _get_team_or_404(db, team_id)
    await _require_coach(db, team_id, current_user.id)

    sessions_data = payload.sessions
    plan_data = payload.model_dump(exclude={"sessions", "team_id"})

    plan = TrainingPlan(
        team_id=team_id,
        created_by_id=current_user.id,
        **plan_data,
    )
    db.add(plan)
    await db.flush()

    for i, s in enumerate(sessions_data):
        db.add(TrainingSession(plan_id=plan.id, order=i, **s.model_dump()))

    await db.commit()
    await db.refresh(plan)

    data = TrainingPlanPublic.model_validate(plan)
    data.sessions_count = len(sessions_data)
    return data


@router.get("/{team_id}/plans", response_model=list[TrainingPlanPublic])
async def list_plans(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TrainingPlan).where(TrainingPlan.team_id == team_id)
        .order_by(TrainingPlan.created_at.desc())
    )
    plans = result.scalars().all()
    out = []
    for p in plans:
        count = await db.scalar(
            select(func.count(TrainingSession.id)).where(TrainingSession.plan_id == p.id)
        )
        d = TrainingPlanPublic.model_validate(p)
        d.sessions_count = count or 0
        out.append(d)
    return out


@router.get("/{team_id}/plans/{plan_id}")
async def get_plan_detail(
    team_id: UUID,
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = await db.get(TrainingPlan, plan_id)
    if not plan or plan.team_id != team_id:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    sessions_result = await db.execute(
        select(TrainingSession).where(TrainingSession.plan_id == plan_id)
        .order_by(TrainingSession.week_number, TrainingSession.day_of_week, TrainingSession.order)
    )
    sessions = sessions_result.scalars().all()

    # Group by week
    weeks: dict = {}
    for s in sessions:
        wk = weeks.setdefault(s.week_number, [])
        wk.append({
            "day": s.day_of_week,
            "title": s.title,
            "description": s.description,
            "discipline": s.discipline,
            "type": s.session_type,
            "target_duration_min": s.target_duration_minutes,
            "target_distance_km": s.target_distance_km,
            "target_hr_zone": s.target_heart_rate_zone,
        })

    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "discipline": plan.discipline,
        "duration_weeks": plan.duration_weeks,
        "goal": plan.goal,
        "status": plan.status,
        "weeks": [{"week": k, "sessions": v} for k, v in sorted(weeks.items())],
    }


@router.post("/{team_id}/plans/{plan_id}/assign", status_code=204)
async def assign_plan(
    team_id: UUID,
    plan_id: UUID,
    payload: AssignPlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    await _require_coach(db, team_id, current_user.id)
    plan = await db.get(TrainingPlan, plan_id)
    if not plan or plan.team_id != team_id:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    for athlete_id in payload.athlete_ids:
        existing = await db.scalar(
            select(func.count(PlanAssignment.id)).where(
                PlanAssignment.plan_id == plan_id,
                PlanAssignment.athlete_id == athlete_id,
            )
        )
        if not existing:
            db.add(PlanAssignment(
                plan_id=plan_id,
                athlete_id=athlete_id,
                assigned_by_id=current_user.id,
                starts_on=payload.starts_on,
                notes=payload.notes,
            ))
    await db.commit()
