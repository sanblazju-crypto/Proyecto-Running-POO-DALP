from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import anthropic

from app.database import get_db
from app.models import User, Activity, PersonalBest, Event, EventStatus
from app.schemas import AIRecommendationRequest, AIRecommendationResponse, EventPublic
from app.auth.dependencies import get_current_premium_user
from app.config import settings

router = APIRouter(prefix="/ai", tags=["ai"])


async def _build_athlete_context(db: AsyncSession, user: User) -> str:
    """Build a rich text summary of the athlete for the LLM context."""
    # Recent activities
    acts_result = await db.execute(
        select(Activity)
        .where(Activity.user_id == user.id)
        .order_by(desc(Activity.started_at))
        .limit(10)
    )
    activities = acts_result.scalars().all()

    # Personal bests
    pbs_result = await db.execute(
        select(PersonalBest).where(PersonalBest.user_id == user.id)
    )
    pbs = pbs_result.scalars().all()

    lines = [
        f"Atleta: {user.full_name or user.username}",
        f"Disciplinas: {', '.join(user.disciplines or [])}",
        f"Ubicación: {user.location or 'no especificada'}",
        "",
        "Últimas actividades:",
    ]
    for a in activities:
        km = f"{a.distance_meters/1000:.1f}km" if a.distance_meters else ""
        dur = f"{a.duration_seconds//60}min" if a.duration_seconds else ""
        lines.append(f"  - {a.title} ({a.discipline}) {km} {dur} — {a.started_at.strftime('%d/%m/%Y')}")

    if pbs:
        lines.append("\nMarcas personales:")
        for pb in pbs:
            mins = pb.time_seconds // 60
            secs = pb.time_seconds % 60
            lines.append(f"  - {pb.distance_label} ({pb.discipline}): {mins}:{secs:02d}")

    return "\n".join(lines)


@router.post("/recommend", response_model=AIRecommendationResponse)
async def get_ai_recommendation(
    payload: AIRecommendationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    """Get personalized training and race recommendations powered by Claude."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Servicio de IA no configurado")

    athlete_ctx = await _build_athlete_context(db, current_user)

    user_message = athlete_ctx
    if payload.context:
        user_message += f"\n\nConsulta del atleta: {payload.context}"
    if payload.discipline:
        user_message += f"\nDisciplina de interés: {payload.discipline}"
    if payload.target_event_date:
        user_message += f"\nFecha objetivo: {payload.target_event_date.strftime('%d/%m/%Y')}"

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "Eres un entrenador deportivo experto especializado en deportes de resistencia "
            "(running, ciclismo, trail, triatlón). Analizas los datos del atleta y ofreces "
            "recomendaciones personalizadas, prácticas y motivadoras. Responde siempre en español."
        ),
        messages=[{"role": "user", "content": user_message}],
    )

    recommendation_text = message.content[0].text

    # Fetch relevant upcoming events
    events_result = await db.execute(
        select(Event)
        .where(
            Event.status == EventStatus.UPCOMING,
            Event.discipline.in_(current_user.disciplines or []) if current_user.disciplines else True,
        )
        .order_by(Event.date.asc())
        .limit(3)
    )
    upcoming = events_result.scalars().all()
    suggested = []
    for ev in upcoming:
        d = EventPublic.model_validate(ev)
        d.participants_count = 0
        d.is_registered = False
        suggested.append(d)

    # Extract tips (simple heuristic: lines starting with - or •)
    tips = [
        line.lstrip("-•· ").strip()
        for line in recommendation_text.split("\n")
        if line.strip().startswith(("-", "•", "·"))
    ][:5]

    return AIRecommendationResponse(
        recommendation=recommendation_text,
        suggested_events=suggested,
        training_tips=tips,
    )


@router.post("/chat")
async def ai_chat(
    message: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_premium_user),
):
    """Free-form coaching chat with Claude."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Servicio de IA no configurado")

    athlete_ctx = await _build_athlete_context(db, current_user)

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "Eres un entrenador personal experto en deportes de resistencia. "
            "Tienes acceso al perfil y actividades del atleta. "
            "Responde de forma concisa, motivadora y técnicamente precisa. "
            "Responde siempre en español.\n\n"
            f"Perfil del atleta:\n{athlete_ctx}"
        ),
        messages=[{"role": "user", "content": message}],
    )

    return {"response": response.content[0].text}


@router.post("/analyze-plan")
async def analyze_training_plan(
    plan_description: str,
    current_user: User = Depends(get_current_premium_user),
):
    """Analyze a training plan and provide feedback."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Servicio de IA no configurado")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=(
            "Eres un entrenador experto en deportes de resistencia. "
            "Analiza planes de entrenamiento e identifica: "
            "carga excesiva, falta de recuperación, desequilibrios de volumen/intensidad, "
            "y proporciona sugerencias concretas de mejora. Responde en español."
        ),
        messages=[
            {
                "role": "user",
                "content": f"Analiza este plan de entrenamiento:\n\n{plan_description}",
            }
        ],
    )
    return {"analysis": response.content[0].text}
