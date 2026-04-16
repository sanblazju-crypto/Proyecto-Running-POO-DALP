"""
Seed script: populates the database with realistic sample data for development.
Run with: python scripts/seed.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from slugify import slugify

from app.database import AsyncSessionLocal
from app.models import (
    User, Event, Activity, Post, PostType,
    Discipline, Difficulty, EventStatus, ActivityType,
)
from app.auth.security import hash_password


USERS = [
    {"email": "maria.garcia@example.com", "username": "mariarunner", "full_name": "María García",
     "disciplines": ["running", "trail"], "location": "Madrid"},
    {"email": "carlos.lopez@example.com", "username": "carloscy", "full_name": "Carlos López",
     "disciplines": ["cycling", "triathlon"], "location": "Barcelona"},
    {"email": "ana.fernandez@example.com", "username": "anatrail", "full_name": "Ana Fernández",
     "disciplines": ["trail", "running"], "location": "Pamplona"},
    {"email": "coach.pedro@example.com", "username": "coachpedro", "full_name": "Pedro Martínez",
     "disciplines": ["running", "triathlon", "cycling"], "location": "Valencia", "is_premium": True},
]

EVENTS = [
    {
        "name": "Maratón de Madrid",
        "discipline": Discipline.RUNNING,
        "difficulty": Difficulty.INTERMEDIATE,
        "date": datetime.now(timezone.utc) + timedelta(days=45),
        "city": "Madrid", "country": "Spain",
        "latitude": 40.4168, "longitude": -3.7038,
        "distance_km": 42.195, "elevation_gain_m": 180,
        "organizer_name": "Ayuntamiento de Madrid",
        "registration_fee": 45.0,
        "tags": ["road", "flat", "popular"],
    },
    {
        "name": "Volta a Catalunya",
        "discipline": Discipline.CYCLING,
        "difficulty": Difficulty.ADVANCED,
        "date": datetime.now(timezone.utc) + timedelta(days=90),
        "city": "Barcelona", "country": "Spain",
        "latitude": 41.3851, "longitude": 2.1734,
        "distance_km": 180.0, "elevation_gain_m": 3200,
        "organizer_name": "Federació Catalana Ciclisme",
        "registration_fee": 80.0,
        "tags": ["road", "mountains", "gran-fondo"],
    },
    {
        "name": "Ultra Trail Picos de Europa",
        "discipline": Discipline.TRAIL,
        "difficulty": Difficulty.ELITE,
        "date": datetime.now(timezone.utc) + timedelta(days=120),
        "city": "Cangas de Onís", "country": "Spain",
        "latitude": 43.3503, "longitude": -5.1237,
        "distance_km": 80.0, "elevation_gain_m": 5500,
        "organizer_name": "Montaña Activa",
        "registration_fee": 120.0,
        "tags": ["ultra", "mountains", "technical"],
    },
    {
        "name": "Triatlón de Valencia",
        "discipline": Discipline.TRIATHLON,
        "difficulty": Difficulty.INTERMEDIATE,
        "date": datetime.now(timezone.utc) + timedelta(days=60),
        "city": "Valencia", "country": "Spain",
        "latitude": 39.4699, "longitude": -0.3763,
        "distance_km": 51.5, "elevation_gain_m": 400,
        "organizer_name": "Club Triatlón Valencia",
        "registration_fee": 95.0,
        "tags": ["olimpico", "sea", "flat"],
    },
    {
        "name": "Media Maratón Sevilla",
        "discipline": Discipline.RUNNING,
        "difficulty": Difficulty.BEGINNER,
        "date": datetime.now(timezone.utc) + timedelta(days=25),
        "city": "Sevilla", "country": "Spain",
        "latitude": 37.3891, "longitude": -5.9845,
        "distance_km": 21.097, "elevation_gain_m": 60,
        "organizer_name": "Club Atletismo Sevilla",
        "registration_fee": 25.0,
        "tags": ["road", "flat", "beginner-friendly"],
    },
]

SAMPLE_ACTIVITIES = [
    {"title": "Rodaje matutino Retiro", "discipline": Discipline.RUNNING,
     "duration_seconds": 3600, "distance_meters": 10000, "avg_heart_rate": 142, "perceived_effort": 6},
    {"title": "Tirada larga dominical", "discipline": Discipline.RUNNING,
     "duration_seconds": 7200, "distance_meters": 21000, "avg_heart_rate": 155, "perceived_effort": 8},
    {"title": "Series 1000m pista", "discipline": Discipline.RUNNING,
     "duration_seconds": 2400, "distance_meters": 7000, "avg_heart_rate": 178, "perceived_effort": 9},
    {"title": "Fondo en bici Sierra", "discipline": Discipline.CYCLING,
     "duration_seconds": 14400, "distance_meters": 100000, "avg_heart_rate": 138, "perceived_effort": 7},
    {"title": "Trail Guadarrama", "discipline": Discipline.TRAIL,
     "duration_seconds": 10800, "distance_meters": 25000, "elevation_gain_m": 1200, "avg_heart_rate": 160},
]


async def seed():
    async with AsyncSessionLocal() as session:
        print("🌱 Iniciando seed de la base de datos...")

        # Create users
        created_users = []
        for u in USERS:
            user = User(
                email=u["email"],
                username=u["username"],
                full_name=u["full_name"],
                disciplines=u["disciplines"],
                location=u.get("location"),
                hashed_password=hash_password("password123"),
                is_active=True,
                is_verified=True,
                is_premium=u.get("is_premium", False),
                bio=f"Apasionado/a de los deportes de resistencia. {', '.join(u['disciplines']).title()}.",
            )
            session.add(user)
            created_users.append(user)
        await session.flush()
        print(f"  ✓ {len(created_users)} usuarios creados")

        # Create events
        created_events = []
        admin_user = created_users[0]
        for ev_data in EVENTS:
            slug = slugify(ev_data["name"])
            ev = Event(
                slug=slug,
                created_by_id=admin_user.id,
                **ev_data,
            )
            session.add(ev)
            created_events.append(ev)
        await session.flush()
        print(f"  ✓ {len(created_events)} eventos creados")

        # Create activities for each user
        total_activities = 0
        for i, user in enumerate(created_users):
            for j, act_data in enumerate(SAMPLE_ACTIVITIES[:3]):
                started = datetime.now(timezone.utc) - timedelta(days=(j + 1) * 5 + i)
                duration = act_data["duration_seconds"]
                distance = act_data["distance_meters"]
                pace = duration / (distance / 1000) if distance else None
                speed = (distance / 1000) / (duration / 3600) if distance else None

                activity = Activity(
                    user_id=user.id,
                    title=act_data["title"],
                    discipline=act_data["discipline"],
                    activity_type=ActivityType.TRAINING,
                    started_at=started,
                    finished_at=started + timedelta(seconds=duration),
                    duration_seconds=duration,
                    distance_meters=distance,
                    avg_heart_rate=act_data.get("avg_heart_rate"),
                    perceived_effort=act_data.get("perceived_effort", 6),
                    elevation_gain_m=act_data.get("elevation_gain_m"),
                    avg_pace_sec_per_km=pace,
                    avg_speed_kmh=speed,
                    is_public=True,
                )
                session.add(activity)

                # Auto-post
                session.add(Post(
                    author_id=user.id,
                    post_type=PostType.ACTIVITY,
                    content=f"Completé {act_data['title']} · {distance/1000:.1f} km",
                    is_public=True,
                    likes_count=j * 2,
                    comments_count=j,
                ))
                total_activities += 1

        await session.flush()
        print(f"  ✓ {total_activities} actividades creadas")

        await session.commit()
        print("\n✅ Seed completado correctamente!")
        print("\nUsuarios de prueba:")
        for u in USERS:
            print(f"  - {u['email']} / password123 {'(premium)' if u.get('is_premium') else ''}")
        print("\n🚀 API disponible en http://localhost:8000/docs")


if __name__ == "__main__":
    asyncio.run(seed())
