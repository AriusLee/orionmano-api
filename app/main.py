import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base
from app.api.v1.router import v1_router

# Import all models so they register with Base
import app.models  # noqa

# Import skills to register them with the skill registry
import app.services.agent.skills  # noqa


# Idempotent column additions for tables that pre-date the column. Postgres
# 9.6+ supports ADD COLUMN IF NOT EXISTS. We use this in lieu of alembic
# while the project is still pre-production.
_COLUMN_UPGRADES: list[str] = [
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS deck VARCHAR(400)",
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS key_takeaways JSONB",
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS reading_time_minutes INTEGER",
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS hero_image_url TEXT",
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS hero_image_alt VARCHAR(400)",
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS hero_image_credit VARCHAR(200)",
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS hero_image_credit_url TEXT",
    "ALTER TABLE published_articles ADD COLUMN IF NOT EXISTS industry VARCHAR(50)",
    "CREATE INDEX IF NOT EXISTS ix_published_articles_industry ON published_articles (industry)",
    # fact_hash was originally UNIQUE; dedup is now policy-based with a
    # freshness window, so the constraint blocks stale-ancestor + fresh-
    # successor coexistence. Drop it if present, keep an index for lookup.
    "ALTER TABLE published_articles DROP CONSTRAINT IF EXISTS published_articles_fact_hash_key",
    "CREATE INDEX IF NOT EXISTS ix_published_articles_fact_hash ON published_articles (fact_hash)",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _COLUMN_UPGRADES:
            await conn.execute(text(stmt))
    # Create upload dir
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(
    title="Orionmano AI Advisory Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)

# Serve uploaded files (company logos, etc.) at /uploads so the frontend
# can display them without an extra auth round-trip.
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok"}
