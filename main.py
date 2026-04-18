from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import init_db
from app.routers.core import router as core_router
from app.routers.social import router as social_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()   # create_all — no Alembic needed
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Red social para deportistas de resistencia — running, ciclismo, trail, triatlón.",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=settings.ALLOWED_ORIGINS,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    return JSONResponse(status.HTTP_409_CONFLICT,
                        {"detail": "Conflicto de datos: el recurso ya existe"})


PREFIX = settings.API_PREFIX
app.include_router(core_router,   prefix=PREFIX)
app.include_router(social_router, prefix=PREFIX)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["system"])
async def root():
    return {"name": settings.APP_NAME, "docs": "/docs"}
