# 🏃 Endurance Platform — Backend API

API REST para la red social de deportistas de resistencia (running, ciclismo, trail, triatlón).
Construida con **FastAPI + PostgreSQL + Redis + Celery**.

---

## 📐 Arquitectura

```
endurance_platform/
├── app/
│   ├── main.py              # Entrada FastAPI, middlewares, routers
│   ├── config.py            # Settings (Pydantic BaseSettings + .env)
│   ├── database.py          # Engine asyncpg, sesión, Base ORM
│   ├── models.py            # Todos los modelos SQLAlchemy
│   ├── schemas.py           # Schemas Pydantic (request/response)
│   ├── celery_app.py        # Configuración Celery + beat schedule
│   ├── auth/
│   │   ├── security.py      # JWT, bcrypt, tokens
│   │   └── dependencies.py  # get_current_user, premium, superuser
│   ├── routers/
│   │   ├── auth.py          # /auth — registro, login, refresh
│   │   ├── users.py         # /users — perfil, seguir, buscar
│   │   ├── events.py        # /events — CRUD, filtros geo, inscripción
│   │   ├── activities.py    # /activities — CRUD, GPX, marcas personales
│   │   ├── feed.py          # /feed — posts, likes, comentarios
│   │   ├── stats.py         # /stats — estadísticas y evolución
│   │   ├── teams.py         # /teams — equipos, planes (premium)
│   │   └── ai.py            # /ai — recomendaciones Claude (premium)
│   └── tasks/
│       ├── notifications.py # Celery: push/email, limpieza tokens
│       ├── activities.py    # Celery: streaks, S3, Strava webhooks
│       ├── reports.py       # Celery: PDF/CSV exportación
│       └── _db.py           # Sesión síncrona para workers
├── alembic/
│   ├── env.py               # Config Alembic async
│   └── versions/
│       └── 0001_initial.py  # Migración inicial
├── tests/
│   ├── conftest.py          # Fixtures pytest-asyncio
│   ├── test_auth.py
│   ├── test_events_activities.py
│   └── test_social_stats.py
├── scripts/
│   └── seed.py              # Datos de ejemplo
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── requirements.txt
└── .env.example
```

---

## 🚀 Inicio rápido

### 1. Requisitos
- Python 3.12+
- Docker + Docker Compose
- PostgreSQL 15+ con extensión PostGIS (incluido en docker-compose)

### 2. Configuración
```bash
cp .env.example .env
# Edita .env con tus valores (SECRET_KEY, claves S3, etc.)
```

### 3. Levantar servicios
```bash
make up           # PostgreSQL + Redis en Docker
make migrate      # Aplica migraciones
make seed         # Carga datos de ejemplo (opcional)
make dev          # Servidor en http://localhost:8000
```

### 4. Documentación interactiva
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🔑 Autenticación

JWT Bearer token con rotación de refresh tokens.

```bash
# Registro
POST /api/v1/auth/register
{"email": "...", "username": "...", "password": "..."}

# Login
POST /api/v1/auth/login
{"email": "...", "password": "..."}

# Usar en headers:
Authorization: Bearer <access_token>

# Refrescar
POST /api/v1/auth/refresh
{"refresh_token": "..."}
```

---

## 📡 Endpoints principales

| Módulo | Base | Descripción |
|--------|------|-------------|
| Auth | `/api/v1/auth` | Registro, login, refresh, cambio de contraseña |
| Usuarios | `/api/v1/users` | Perfil, búsqueda, seguir/dejar de seguir |
| Eventos | `/api/v1/events` | Búsqueda con filtros geo, inscripción, resultados |
| Actividades | `/api/v1/activities` | CRUD, subida GPX, marcas personales automáticas |
| Feed | `/api/v1/feed` | Posts, likes, comentarios, feed cronológico/relevancia |
| Estadísticas | `/api/v1/stats` | KPIs, evolución semanal/mensual, marcas personales |
| Equipos | `/api/v1/teams` | Gestión de equipos y planes (premium) |
| IA | `/api/v1/ai` | Recomendaciones y coaching con Claude (premium) |

---

## 🧪 Tests

```bash
make test           # Ejecutar tests
make test-cov       # Tests con cobertura HTML
```

Requiere una base de datos PostgreSQL de test (`endurance_test`).

---

## 🐳 Servicios Docker

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| `api` | 8000 | FastAPI app |
| `db` | 5432 | PostgreSQL + PostGIS |
| `redis` | 6379 | Cache + broker Celery |
| `worker` | — | Celery worker |
| `beat` | — | Celery beat (tareas programadas) |
| `flower` | 5555 | Monitorización Celery |

---

## 🔧 Variables de entorno clave

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL asyncpg URL |
| `SECRET_KEY` | Clave para firmar JWTs (mín. 32 chars) |
| `REDIS_URL` | Redis URL |
| `ANTHROPIC_API_KEY` | Clave API de Anthropic (funciones IA) |
| `AWS_ACCESS_KEY_ID` | Credenciales S3 para archivos |
| `STRAVA_CLIENT_ID` | OAuth Strava |

---

## 🗺️ Roadmap

- [ ] WebSockets para feed en tiempo real
- [ ] Integración OAuth Google y Strava
- [ ] Parser GPX completo con splits por km
- [ ] Notificaciones push FCM/APNs
- [ ] Webhook Strava para sincronización automática
- [ ] Módulo de análisis de potencia (ciclismo/running power)
- [ ] Sistema de retos y gamificación
- [ ] App móvil (React Native)
