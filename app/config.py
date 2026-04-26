from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://ariuslee@localhost:5432/orionmano"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "orionmano-dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    ANTHROPIC_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    UNSPLASH_ACCESS_KEY: str = ""

    CORS_ORIGINS: str = '["http://localhost:3020"]'
    UPLOAD_DIR: str = "./uploads"

    # Public article site. Every industry-report citation resolves to an
    # article URL on this host. Site itself ships later — for now articles
    # live in the DB and the URL is a stable reservation.
    ARTICLE_SITE_BASE_URL: str = "https://industries.omassurance.com/articles/"

    # Citation dedup freshness window. Articles older than this are treated
    # as stale; new citations on the same topic / fact will trigger a fresh
    # generation rather than reusing the old article. Drives both tier-1
    # (exact fact_hash) and tier-2 (same topic) reuse decisions in
    # services/report/citations.py::resolve_citation.
    ARTICLE_REUSE_DAYS: int = 90

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
