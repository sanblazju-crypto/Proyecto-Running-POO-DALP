"""Seed: populates DB with sample data.

Usage inside Docker:
    docker compose exec api python seed.py

Usage locally (from project root):
    python seed.py
"""
import asyncio, sys, os

# Ensure the project root is always in sys.path,
# regardless of where the script is invoked from.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from datetime import datetime, timedelta, timezone
from slugify import slugify
from app.database import SessionLocal, init_db          # was: AsyncSessionLocal (wrong name)
from app.models import User, Event, Activity, Post, PostType, Discipline, Difficulty, ActivityType
from app.security import hash_password

USERS = [
    {"email": "maria@example.com",  "username": "mariarunner", "full_name": "María García",
     "disciplines": ["running", "trail"], "location": "Madrid"},
    {"email": "carlos@example.com", "username": "carloscy",    "full_name": "Carlos López",
     "disciplines": ["cycling", "triathlon"], "location": "Barcelona"},
    {"email": "coach@example.com",  "username": "coachpedro",  "full_name": "Pedro Martínez",
     "disciplines": ["running", "triathlon"], "location": "Valencia", "is_premium": True},
]

EVENTS = [
    {"name": "Maratón de Madrid",    "discipline": Discipline.RUNNING,   "difficulty": Difficulty.INTERMEDIATE,
     "date": datetime.now(timezone.utc) + timedelta(days=45),  "city": "Madrid",
     "latitude": 40.4168, "longitude": -3.7038, "distance_km": 42.195, "registration_fee": 45.0},
    {"name": "Volta a Catalunya",    "discipline": Discipline.CYCLING,   "difficulty": Difficulty.ADVANCED,
     "date": datetime.now(timezone.utc) + timedelta(days=90),  "city": "Barcelona",
     "latitude": 41.3851, "longitude":  2.1734, "distance_km": 180.0,  "registration_fee": 80.0},
    {"name": "Ultra Trail Picos",    "discipline": Discipline.TRAIL,     "difficulty": Difficulty.ELITE,
     "date": datetime.now(timezone.utc) + timedelta(days=120), "city": "Cangas de Onís",
     "latitude": 43.3503, "longitude": -5.1237, "distance_km": 80.0,   "registration_fee": 120.0},
    {"name": "Triatlón de Valencia", "discipline": Discipline.TRIATHLON, "difficulty": Difficulty.INTERMEDIATE,
     "date": datetime.now(timezone.utc) + timedelta(days=60),  "city": "Valencia",
     "latitude": 39.4699, "longitude": -0.3763, "distance_km": 51.5,   "registration_fee": 95.0},
]

async def seed():
    await init_db()
    async with SessionLocal() as db:
        users = []
        for u in USERS:
            user = User(
                email=u["email"], username=u["username"], full_name=u["full_name"],
                disciplines=u["disciplines"], location=u.get("location"),
                hashed_password=hash_password("password123"),
                is_active=True, is_verified=True, is_premium=u.get("is_premium", False),
            )
            db.add(user)
            users.append(user)
        await db.flush()

        for ev in EVENTS:
            slug = slugify(ev["name"])
            db.add(Event(slug=slug, created_by_id=users[0].id,
                         country="Spain", currency="EUR", tags=[], **ev))

        for i, user in enumerate(users):
            for j in range(3):
                started = datetime.now(timezone.utc) - timedelta(days=(j + 1) * 5 + i)
                dist = 10000 + j * 2000
                dur  = 3600  + j * 600
                db.add(Activity(
                    user_id=user.id,
                    title=f"Entrenamiento {j + 1}",
                    discipline=user.disciplines[0],
                    activity_type=ActivityType.TRAINING,
                    started_at=started,
                    duration_seconds=dur,
                    distance_meters=dist,
                    avg_pace_sec_per_km=dur / (dist / 1000),
                    avg_speed_kmh=(dist / 1000) / (dur / 3600),
                    is_public=True,
                ))
                db.add(Post(
                    author_id=user.id,
                    post_type=PostType.ACTIVITY,
                    content=f"Completé entrenamiento · {dist / 1000:.1f} km",
                    is_public=True,
                    likes_count=j * 3,
                ))

        await db.commit()
        print("✅ Seed completado.")
        for u in USERS:
            premium = " (premium)" if u.get("is_premium") else ""
            print(f"   {u['email']} / password123{premium}")
        print("\n🚀 Documentación: http://localhost:8000/docs")

if __name__ == "__main__":
    asyncio.run(seed())
